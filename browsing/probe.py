"""One Browser Use task on Steel; the collector shares Browser Use's own CDP connection."""

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from browser_use import Agent, BrowserSession
from steel import AsyncSteel

from core.runtime import chat_completions_fallback, chat_json_schema_supported, error_summary, require, require_capabilities, settings, write_json
from browsing.model import ProviderChatOpenAI

# Browser Use degrades silently to a minimal page state when CDP DOM requests fail;
# count these so the probe fails instead of passing on a page the agent cannot operate.
DOM_FAILURE_MARKERS = ("timed out", "DOM build failed")


class LogCounter(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.dom_failures = 0
        self.duplicate_responses = 0

    def emit(self, record):
        message = record.getMessage()
        self.dom_failures += any(marker in message for marker in DOM_FAILURE_MARKERS)
        self.duplicate_responses += "duplicate response" in message


async def probe_browser(config, run_dir, profile):
    require(config, "steel_api_key")
    run_dir = Path(run_dir)
    screenshots = run_dir / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    host = urlsplit(config["url"]).hostname
    result = {"passed": False, "url": config["url"], "timezone": config["timezone"],
              **chat_completions_fallback(config, "Browser Use")}
    started = time.monotonic()
    log_counter = LogCounter()
    for name in ["browser_use", "cdp_use", "bubus"]:
        logging.getLogger(name).addHandler(log_counter)
    session = None
    browser_session = None
    async with AsyncSteel(steel_api_key=config["steel_api_key"], timeout=60, max_retries=0) as steel:
        try:
            session = await steel.sessions.create(
                dimensions={"width": 1440, "height": 900}, solve_captcha=False,
                api_timeout=600000,
            )
            result["session_id"] = session.id
            result["session_timeout_ms"] = session.timeout
            result["session_viewer_url"] = session.session_viewer_url
            cdp_url = session.websocket_url + ("&" if "?" in session.websocket_url else "?") + urlencode({"apiKey": config["steel_api_key"]})
            # Browser Use's built-in HAR recorder is not used: it fetches every response body
            # over the CDP socket, which made Steel drop the connection (keepalive timeout).
            browser_session = BrowserSession(cdp_url=cdp_url, allowed_domains=[host])
            await browser_session.start()
            cdp = browser_session.cdp_client
            counts = {}
            documents = {}
            prepared_sessions = set()
            with (run_dir / "raw_trace.jsonl").open("w", encoding="utf-8") as trace:

                def record(event, payload):
                    counts[event] = counts.get(event, 0) + 1
                    if event == "Network.requestWillBeSent" and payload.get("type") == "Document":
                        documents[payload["requestId"]] = {"url": payload["request"]["url"]}
                    if event == "Network.responseReceivedExtraInfo" and payload["requestId"] in documents:
                        documents[payload["requestId"]]["status"] = payload.get("statusCode")
                    trace.write(json.dumps({"elapsed_seconds": round(time.monotonic() - started, 3),
                                            "event": event, "data": payload}, ensure_ascii=False) + "\n")
                    trace.flush()

                # cdp_use keeps one handler per event method, so registering an event Browser Use
                # already handles would silently replace its handler (it owns Network.responseReceived
                # for downloads). Claim only unused events and fail loudly if that ever changes.
                # The registry has no public lookup; _event_registry is cdp_use's own attribute.
                events = ["Runtime.consoleAPICalled", "Runtime.exceptionThrown", "Network.requestWillBeSent",
                          "Network.responseReceivedExtraInfo", "Network.loadingFinished", "Network.loadingFailed"]
                claimed = set(cdp._event_registry.get_registered_methods()) & set(events)
                if claimed:
                    raise RuntimeError("Browser Use already handles: " + ", ".join(sorted(claimed)))
                for event in events:
                    domain, method = event.split(".")
                    getattr(getattr(cdp.register, domain), method)(
                        lambda payload, session_id=None, name=event: record(name, payload))

                async def prepare(cdp_session):
                    # Overrides are per CDP session, so apply them to every page the agent focuses.
                    if cdp_session.session_id in prepared_sessions:
                        return
                    prepared_sessions.add(cdp_session.session_id)
                    await cdp.send.Emulation.setTimezoneOverride(
                        params={"timezoneId": config["timezone"]}, session_id=cdp_session.session_id)
                    for domain in ["Runtime", "Network", "Performance"]:
                        await getattr(cdp.send, domain).enable(session_id=cdp_session.session_id)

                capture_index = 0

                async def capture(agent=None):
                    nonlocal capture_index
                    capture_index += 1
                    cdp_session = await browser_session.get_or_create_cdp_session()
                    await prepare(cdp_session)
                    screenshot = screenshots / f"step_{capture_index:03d}.png"
                    await browser_session.take_screenshot(path=str(screenshot))
                    metrics = await cdp.send.Performance.getMetrics(session_id=cdp_session.session_id)
                    record("snapshot", {"url": await browser_session.get_current_page_url(),
                                        "screenshot": str(screenshot.relative_to(run_dir)),
                                        "performance": metrics["metrics"]})

                # Prepare before navigating so the first document request is captured.
                cdp_session = await browser_session.get_or_create_cdp_session()
                await prepare(cdp_session)
                await browser_session.navigate_to(config["url"])
                observed = await cdp.send.Runtime.evaluate(
                    params={"expression": "console.info('muchhuman phase0 collector attached');"
                                          "Intl.DateTimeFormat().resolvedOptions().timeZone", "returnByValue": True},
                    session_id=cdp_session.session_id)
                result["observed_timezone"] = observed["result"].get("value")
                start_url = await browser_session.get_current_page_url()
                await capture()
                llm = ProviderChatOpenAI(
                    model=config["model"], base_url=config["base_url"], api_key=config["api_key"],
                    thinking_type=config.get("thinking_type"),
                    timeout=60, max_retries=0, dont_force_structured_output=not chat_json_schema_supported(profile),
                    add_schema_to_system_prompt=not chat_json_schema_supported(profile),
                )
                # A real DOM interaction: the agent must use an indexed element, which only
                # works when Browser Use built the page's DOM tree.
                agent = Agent(
                    task=f"The page {config['url']} is already open. Click one link that leads to a different page on "
                         f"{host}, then finish with done and report the new page's title and URL. Use the click action "
                         "on an element from the page; do not navigate by typing a URL, do not use evaluate. "
                         "Only browse: do not submit forms, log in or change any data.",
                    llm=llm, browser_session=browser_session, use_vision=True,
                    max_actions_per_step=1, use_judge=False, enable_planning=False,
                    directly_open_url=False,
                )
                # Browser Use turns vision off for any model named "deepseek"; capabilities come from
                # our measured vision probes (required for a ready profile), not from model names.
                agent.settings.use_vision = True
                result["use_vision"] = agent.settings.use_vision
                history = await asyncio.wait_for(agent.run(max_steps=6, on_step_end=capture), timeout=360)
                # Agent.run resets the browser session when it finishes, so read the URL from history.
                final_url = next((url for url in reversed(history.urls()) if url), None)
                result["agent_success"] = history.is_successful()
                result["agent_result"] = history.final_result()
                result["actions"] = history.action_names()
                result["steps"] = len(history.history)
                result["seconds_per_step"] = round(history.total_duration_seconds() / max(len(history.history), 1), 1)
                result["start_url"] = start_url
                result["final_url"] = final_url
                result["collector_counts"] = counts
                result["model_requests"] = llm.requests_sent
                result["model_requests_with_screenshots"] = llm.requests_with_images
        except Exception as error:
            result["error"] = error_summary(error, run_dir)
        finally:
            if browser_session:
                try:
                    await browser_session.kill()
                except Exception as error:
                    result["browser_cleanup_error"] = error_summary(error, run_dir)
            if session:
                try:
                    await steel.sessions.release(session.id)
                    result["released"] = True
                except Exception as error:
                    result["release_error"] = error_summary(error, run_dir)
            for name in ["browser_use", "cdp_use", "bubus"]:
                logging.getLogger(name).removeHandler(log_counter)
            result["dom_failures"] = log_counter.dom_failures
            result["duplicate_responses"] = log_counter.duplicate_responses
            document = next((doc for doc in documents.values() if doc["url"].rstrip("/") == config["url"].rstrip("/")), None)
            result["http_status"] = document.get("status") if document else None
            result["passed"] = "error" not in result and result.get("released", False) and all([
                result.get("agent_success"),
                "click" in result.get("actions", []),
                result.get("final_url") and result["final_url"] != result["start_url"]
                and urlsplit(result["final_url"]).hostname == host,
                result["dom_failures"] == 0,
                # Every agent step must have sent its screenshot to the model, not only enabled vision.
                result.get("model_requests_with_screenshots", 0) >= result.get("steps", 0) > 0,
                result.get("observed_timezone") == config["timezone"],
                result["http_status"] is not None and result["http_status"] < 400,
                # The console count proves the capture pipeline (the collector logs one line itself),
                # not that the site emitted console output.
                result.get("collector_counts", {}).get("Runtime.consoleAPICalled", 0) > 0,
                result.get("collector_counts", {}).get("snapshot", 0) > 0,
            ])
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            write_json(run_dir / "browser_result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    config = settings()
    try:
        profile = require_capabilities(args.run_dir, config)
        result = asyncio.run(probe_browser(config, args.run_dir, profile))
    except Exception as error:
        result = {"passed": False, "error": error_summary(error, args.run_dir)}
        write_json(args.run_dir / "browser_result.json", result)
    print("Steel + Browser Use: " + ("PASS" if result["passed"] else "FAIL"))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
