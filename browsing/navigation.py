"""Block document requests before transmission on Browser Use's shared CDP connection."""

import asyncio
from urllib.parse import urlsplit


def allowed_url(url, domains):
    try:
        parsed = urlsplit(url)
        return parsed.scheme in {"http", "https"} and parsed.hostname in domains and not parsed.username and not parsed.password
    except ValueError:
        return False


class NavigationGuard:
    def __init__(self, browser, domains, record):
        self.browser, self.cdp, self.domains, self.record = browser, browser.cdp_client, set(domains), record
        self.enabled, self.locks, self.tasks = set(), {}, set()
        self.error, self.original_send, self.original_reconnect = None, None, None

    def check(self):
        if self.error is not None:
            raise RuntimeError("Navigation request interception failed; browsing must stop") from self.error

    async def attach(self):
        if "Fetch.requestPaused" in self.cdp._event_registry.get_registered_methods():
            raise RuntimeError("Fetch.requestPaused already owned; cannot safely install navigation interception")
        self.original_send = self.cdp.send_raw
        self.original_reconnect = self.browser.reconnect
        # Reconnect creates a different CDP client, dropping all request interception hooks.
        object.__setattr__(self.browser, "reconnect", self.refuse_reconnect)
        self.cdp.register.Fetch.requestPaused(self.request_paused)
        self.cdp.send_raw = self.send
        # New pages must be paused before their first document request, including script-created popups.
        await self.cdp.send.Target.setAutoAttach(params={"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True})
        for session in list(self.browser.session_manager._sessions.values()):
            if self.browser.session_manager.get_target(session.target_id).target_type in {"page", "iframe"}:
                # Root auto-attach does not update existing sessions' child-target settings.
                await self.cdp.send.Target.setAutoAttach(params={
                    "autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True}, session_id=session.session_id)
                await self.prepare(session.session_id)

    async def refuse_reconnect(self):
        self.error = ConnectionError("CDP connection lost; restart the guarded browsing session")
        self.check()

    async def prepare(self, session_id):
        async with self.locks.setdefault(session_id, asyncio.Lock()):
            if session_id not in self.enabled:
                await self.original_send("Fetch.enable", {"patterns": [
                    {"urlPattern": "*", "resourceType": "Document", "requestStage": "Request"}]}, session_id)
                self.enabled.add(session_id)

    async def send(self, method, params=None, session_id=None):
        if method == "Target.setAutoAttach" and params and params.get("autoAttach"):
            params = dict(params, waitForDebuggerOnStart=True)
        if method == "Runtime.runIfWaitingForDebugger" and session_id:
            self.check()
            session = self.browser.session_manager._sessions.get(session_id)
            target = self.browser.session_manager.get_target(session.target_id) if session else None
            if target is None:
                self.error = RuntimeError("Cannot verify navigation interception for an unknown target")
                self.check()
            if target.target_type in {"page", "iframe"}:
                try:
                    await self.prepare(session_id)
                except Exception as error:
                    self.error = error
                    raise
        return await self.original_send(method, params, session_id)

    def request_paused(self, event, session_id=None):
        # cdp_use awaits async handlers on its receive loop; sending CDP here would deadlock it.
        task = asyncio.create_task(self.resolve_request(event, session_id))
        self.tasks.add(task)
        task.add_done_callback(self.completed)

    def completed(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            self.error = task.exception()
            self.record("navigation_guard_failed", {"error_type": type(self.error).__name__})

    async def resolve_request(self, event, session_id):
        request_id, url = event["requestId"], event["request"]["url"]
        if event["resourceType"] == "Document" and not allowed_url(url, self.domains):
            self.record("navigation_blocked", {"url": url, "request_id": request_id, "frame_id": event["frameId"]})
            await self.cdp.send.Fetch.failRequest(params={"requestId": request_id, "errorReason": "BlockedByClient"}, session_id=session_id)
        else:
            await self.cdp.send.Fetch.continueRequest(params={"requestId": request_id}, session_id=session_id)

    async def close(self):
        """Release the hook after the browser has stopped; never disable it on a live session."""
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.original_send is not None:
            self.cdp._event_registry.unregister("Fetch.requestPaused")
            self.cdp.send_raw = self.original_send
            object.__setattr__(self.browser, "reconnect", self.original_reconnect)
