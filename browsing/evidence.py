"""Reuse Browser Use's CDP client without taking over its event handlers."""

import hashlib
import json
import re
import time
from urllib.parse import quote

from core.experience import Snapshot


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {key: "REDACTED" if re.search(r"authorization|cookie|password|api.?key|token|headersText|postData", key, re.I)
                else redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "REDACTED").replace(quote(secret, safe=""), "REDACTED")
        return re.sub(r"(?i)(apiKey=|token=|password=|Bearer )[^&\s'\"]+", r"\1REDACTED", value)
    return value


class EvidenceCollector:
    EVENTS = ("Runtime.consoleAPICalled", "Runtime.exceptionThrown", "Network.requestWillBeSent",
              "Network.responseReceivedExtraInfo", "Network.loadingFinished", "Network.loadingFailed")

    def __init__(self, browser, run_dir, started, secrets=()):
        self.browser, self.run_dir, self.started = browser, run_dir, started
        self.secrets = secrets
        self.events, self.snapshots, self.requests = [], [], {}
        self.prepared = set()
        (run_dir / "screenshots").mkdir(parents=True)
        self.trace = (run_dir / "raw_trace.jsonl").open("w", encoding="utf-8")

    def record(self, event, data):
        item = {"event_id": f"t{len(self.events) + 1:05d}", "video_seconds": round(time.monotonic() - self.started, 3),
                "event": event, "data": redact(data, self.secrets)}
        self.events.append(item)
        self.trace.write(json.dumps(item, ensure_ascii=False) + "\n")
        self.trace.flush()
        if event == "Network.requestWillBeSent":
            self.requests[data["requestId"]] = item["data"]["request"].get("url", "")
        return item

    async def attach(self):
        cdp = self.browser.cdp_client
        claimed = set(cdp._event_registry.get_registered_methods()) & set(self.EVENTS)
        if claimed:
            raise RuntimeError("CDP event already owned by Browser Use: " + ", ".join(sorted(claimed)))
        for event in self.EVENTS:
            domain, method = event.split(".")
            getattr(getattr(cdp.register, domain), method)(
                lambda payload, session_id=None, name=event: self.record(name, payload))

    async def prepare(self, persona):
        session = await self.browser.get_or_create_cdp_session()
        if session.session_id not in self.prepared:
            cdp = self.browser.cdp_client
            width, height = (390, 844) if persona.browsing_profile.device == "mobile" else (1440, 900)
            await cdp.send.Emulation.setTimezoneOverride(params={"timezoneId": persona.timezone}, session_id=session.session_id)
            await cdp.send.Emulation.setLocaleOverride(params={"locale": "zh-CN"}, session_id=session.session_id)
            await cdp.send.Emulation.setDeviceMetricsOverride(params={"width": width, "height": height,
                "deviceScaleFactor": 1, "mobile": persona.browsing_profile.device == "mobile"}, session_id=session.session_id)
            for domain in ("Runtime", "Network", "Performance"):
                await getattr(cdp.send, domain).enable(session_id=session.session_id)
            self.prepared.add(session.session_id)
        return session

    async def snapshot(self, persona, evidence_id):
        session = await self.prepare(persona)
        result = await self.browser.cdp_client.send.Runtime.evaluate(params={"expression":
            "(()=>{const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT),parts=[];let node;"
            "while(node=walker.nextNode()){const text=node.textContent.trim();if(!text)continue;"
            "const style=getComputedStyle(node.parentElement);if(style.visibility==='hidden'||style.display==='none')continue;"
            "const range=document.createRange();range.selectNodeContents(node);const r=range.getBoundingClientRect();"
            "if(r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth)parts.push(text);}"
            "return JSON.stringify({title:document.title,text:parts.join('\\n').slice(0,24000),url:location.href,x:scrollX,y:scrollY});})()",
            "returnByValue": True}, session_id=session.session_id)
        page = json.loads(result["result"]["value"])
        screenshot = self.run_dir / "screenshots" / f"{evidence_id}.png"
        await self.browser.take_screenshot(path=str(screenshot))
        item = Snapshot(evidence_id=evidence_id, url=redact(page["url"], self.secrets), title=redact(page["title"], self.secrets),
                        text=redact(page["text"], self.secrets), screenshot=screenshot.relative_to(self.run_dir).as_posix(),
                        screenshot_sha256=hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                        scroll_x=round(page["x"]), scroll_y=round(page["y"]),
                        video_seconds=round(time.monotonic() - self.started, 3))
        self.snapshots.append(item)
        self.record("snapshot", item.model_dump())
        return item

    def console(self):
        return [item for item in self.events if item["event"] in {"Runtime.consoleAPICalled", "Runtime.exceptionThrown"}][-30:]

    def failed_requests(self):
        failures = []
        for item in self.events:
            data = item["data"]
            if item["event"] == "Network.loadingFailed" or (item["event"] == "Network.responseReceivedExtraInfo" and data.get("statusCode", 0) >= 400):
                failures.append({**item, "url": self.requests.get(data.get("requestId"), "")})
        return failures[-30:]

    def close(self):
        self.trace.close()
