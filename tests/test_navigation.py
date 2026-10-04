import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from cdp_use import CDPClient

from browsing.navigation import NavigationGuard


def fake_browser(sender):
    client = CDPClient("ws://fixture.invalid")
    client.send_raw = sender
    sessions = {"page": SimpleNamespace(session_id="page", target_id="page")}
    targets = {"page": SimpleNamespace(target_type="page")}
    async def reconnect():
        pytest.fail("A guarded connection must not silently reconnect without its interception hooks")
    return SimpleNamespace(cdp_client=client, reconnect=reconnect, session_manager=SimpleNamespace(
        _sessions=sessions, get_target=lambda tid: targets.get(tid))), sessions, targets


def test_new_targets_are_guarded_before_resume_without_replacing_framework_handlers():
    calls = []
    async def send(method, params=None, session_id=None):
        calls.append((method, params, session_id))
        return {}
    browser, sessions, targets = fake_browser(send)
    framework = lambda *args: None
    browser.cdp_client.register.Target.attachedToTarget(framework)
    guard = NavigationGuard(browser, ["example.com"], lambda *args: None)
    async def run():
        await guard.attach()
        sessions["new"] = SimpleNamespace(session_id="new", target_id="new")
        targets["new"] = SimpleNamespace(target_type="page")
        await browser.cdp_client.send.Target.setAutoAttach(
            params={"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}, session_id="new")
        await asyncio.gather(*(browser.cdp_client.send.Runtime.runIfWaitingForDebugger(session_id="new") for _ in range(2)))
        await guard.close()
    asyncio.run(run())
    new = [c for c in calls if c[2] == "new"]
    assert new[0][1]["waitForDebuggerOnStart"] is True
    assert [c[0] for c in new] == ["Target.setAutoAttach", "Fetch.enable", "Runtime.runIfWaitingForDebugger", "Runtime.runIfWaitingForDebugger"]
    assert browser.cdp_client.send_raw is send
    assert "Target.attachedToTarget" in browser.cdp_client._event_registry.get_registered_methods()
    assert "Fetch.requestPaused" not in browser.cdp_client._event_registry.get_registered_methods()


@pytest.mark.parametrize("url,allowed", [("https://example.com/projects", True),
    ("https://www.example.com/", False), ("https://example.com.attacker.invalid/", False),
    ("https://outside.invalid/", False), ("https://user:password@example.com/", False), ("http://[", False)])
def test_document_requests_are_resolved_at_request_stage(url, allowed):
    calls, records = [], []
    async def send(method, params=None, session_id=None):
        calls.append((method, params, session_id))
        return {}
    browser, _, _ = fake_browser(send)
    guard = NavigationGuard(browser, ["example.com"], lambda event, data: records.append((event, data)))
    async def run():
        await guard.attach()
        await browser.cdp_client._event_registry.handle_event("Fetch.requestPaused",
            {"requestId": "request", "request": {"url": url}, "resourceType": "Document", "frameId": "frame"}, "page")
        await asyncio.gather(*guard.tasks)
        guard.check()
        await guard.close()
    asyncio.run(run())
    assert calls[-1][0] == ("Fetch.continueRequest" if allowed else "Fetch.failRequest")
    assert calls[-1][2] == "page"
    assert bool(records) is (not allowed)


def test_interception_failure_stops_browsing_and_does_not_continue_request():
    calls = []
    async def send(method, params=None, session_id=None):
        calls.append(method)
        if method == "Fetch.failRequest":
            raise ConnectionError("fixture disconnect")
        return {}
    browser, _, _ = fake_browser(send)
    guard = NavigationGuard(browser, ["example.com"], lambda *args: None)
    async def run():
        await guard.attach()
        guard.request_paused({"requestId": "request", "request": {"url": "https://outside.invalid"},
                              "resourceType": "Document", "frameId": "frame"}, "page")
        await asyncio.gather(*guard.tasks, return_exceptions=True)
        with pytest.raises(RuntimeError, match="interception failed"):
            guard.check()
        with pytest.raises(RuntimeError):
            await browser.cdp_client.send.Runtime.runIfWaitingForDebugger(session_id="page")
        await guard.close()
    asyncio.run(run())
    assert "Fetch.continueRequest" not in calls and "Runtime.runIfWaitingForDebugger" not in calls


def test_existing_fetch_handler_is_preserved():
    async def send(*args, **kwargs):
        pytest.fail("Conflicting handlers must be rejected before CDP mutation")
    browser, _, _ = fake_browser(send)
    browser.cdp_client.register.Fetch.requestPaused(lambda *args: None)
    guard = NavigationGuard(browser, ["example.com"], lambda *args: None)
    with pytest.raises(RuntimeError, match="already owned"):
        asyncio.run(guard.attach())
    assert browser.cdp_client.send_raw is send


def test_connection_replacement_is_refused_until_guard_is_closed():
    async def send(*args, **kwargs):
        return {}
    browser, _, _ = fake_browser(send)
    original = browser.reconnect
    guard = NavigationGuard(browser, ["example.com"], lambda *args: None)
    async def run():
        await guard.attach()
        with pytest.raises(RuntimeError, match="interception failed"):
            await browser.reconnect()
        with pytest.raises(RuntimeError):
            guard.check()
        await guard.close()
    asyncio.run(run())
    assert browser.reconnect is original


def test_failed_target_initialization_never_resumes_unguarded_page():
    calls = []
    async def send(method, params=None, session_id=None):
        calls.append((method, session_id))
        if method == "Fetch.enable" and session_id == "new":
            raise ConnectionError("fixture setup failure")
        return {}
    browser, sessions, targets = fake_browser(send)
    guard = NavigationGuard(browser, ["example.com"], lambda *args: None)
    async def run():
        await guard.attach()
        sessions["new"] = SimpleNamespace(session_id="new", target_id="new")
        targets["new"] = SimpleNamespace(target_type="page")
        with pytest.raises(ConnectionError):
            await browser.cdp_client.send.Runtime.runIfWaitingForDebugger(session_id="new")
        with pytest.raises(RuntimeError):
            guard.check()
        await guard.close()
    asyncio.run(run())
    assert ("Runtime.runIfWaitingForDebugger", "new") not in calls


def test_local_chrome_blocks_redirects_scripts_iframes_and_popups_before_server_receives_them(tmp_path, monkeypatch):
    from browser_use import BrowserSession

    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe") if os.name == "nt" else Path("/usr/bin/chromium")
    if not chrome.is_file():
        pytest.skip("Local Chrome/Chromium required for the navigation integration test")
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "false")
    received, records = [], []
    class Handler(BaseHTTPRequestHandler):
        def handle(self):
            try:
                super().handle()
            except ConnectionResetError:
                pass  # Chrome closes idle HTTP connections when a tab is discarded.

        def do_GET(self):
            received.append((self.headers["Host"].split(":")[0], self.path))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", forbidden + "/redirected")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!doctype html><html><body>navigation fixture</body></html>")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    allowed, forbidden = f"http://localhost:{server.server_port}", f"http://127.0.0.1:{server.server_port}"

    async def wait_blocked(path):
        async with asyncio.timeout(10):
            while not any(event == "navigation_blocked" and data["url"] == forbidden + path for event, data in records):
                await asyncio.sleep(0.02)

    async def run():
        browser = BrowserSession(executable_path=str(chrome), headless=True, allowed_domains=["localhost"],
                                 user_data_dir=str(tmp_path / "chrome"), enable_default_extensions=False)
        guard = None
        try:
            await browser.start()
            guard = NavigationGuard(browser, ["localhost"], lambda event, data: records.append((event, data)))
            await guard.attach()
            for path, script in [("/script", "location.href=URL"),
                                 ("/iframe", "const f=document.createElement('iframe');f.src=URL;document.body.append(f)"),
                                 ("/popup", "window.open(URL)")]:
                await browser.navigate_to(allowed + "/")
                session = await browser.get_or_create_cdp_session()
                await browser.cdp_client.send.Runtime.evaluate(params={"expression": script.replace("URL", repr(forbidden + path))},
                                                               session_id=session.session_id)
                await wait_blocked(path)
            with pytest.raises(RuntimeError, match="ERR_BLOCKED_BY_CLIENT"):
                await browser.navigate_to(allowed + "/redirect")
            await wait_blocked("/redirected")
            await browser.navigate_to(allowed + "/ok")
            # Allowed popups must still load; rejection must not merely disable all new tabs.
            session = await browser.get_or_create_cdp_session()
            await browser.cdp_client.send.Runtime.evaluate(params={"expression": f"window.open({allowed + '/popup-ok'!r})"},
                                                           session_id=session.session_id)
            async with asyncio.timeout(10):
                while ("localhost", "/popup-ok") not in received:
                    await asyncio.sleep(0.02)
            guard.check()
        finally:
            await asyncio.wait_for(browser.kill(), 20)
            if guard:
                await guard.close()
    try:
        asyncio.run(asyncio.wait_for(run(), 60))
        assert ("localhost", "/ok") in received
        assert not any(host == "127.0.0.1" for host, _ in received)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_allowed_cross_site_iframe_cannot_navigate_outside_domains(tmp_path, monkeypatch):
    from browser_use import BrowserSession

    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe") if os.name == "nt" else Path("/usr/bin/chromium")
    if not chrome.is_file():
        pytest.skip("Local Chrome/Chromium required for the navigation integration test")
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "false")
    received, records = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.headers["Host"].split(":")[0], self.path))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!doctype html><html><body>iframe fixture</body></html>")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    outside = ThreadingHTTPServer(("127.0.0.2", 0), Handler)
    threads = [threading.Thread(target=item.serve_forever, daemon=True) for item in (server, outside)]
    for thread in threads:
        thread.start()

    async def run():
        browser = BrowserSession(executable_path=str(chrome), headless=True, allowed_domains=["localhost", "127.0.0.1"],
                                 user_data_dir=str(tmp_path / "chrome"), enable_default_extensions=False)
        guard = None
        try:
            await browser.start()
            guard = NavigationGuard(browser, ["localhost", "127.0.0.1"], lambda event, data: records.append((event, data)))
            await guard.attach()
            await browser.navigate_to(f"http://localhost:{server.server_port}/")
            session = await browser.get_or_create_cdp_session()
            await browser.cdp_client.send.Runtime.evaluate(params={"expression":
                f"const f=document.createElement('iframe');f.src='http://127.0.0.1:{server.server_port}/frame';document.body.append(f)"},
                session_id=session.session_id)
            async with asyncio.timeout(10):
                while True:
                    frames = [s for s in browser.session_manager._sessions.values()
                              if browser.session_manager.get_target(s.target_id).target_type == "iframe"]
                    if frames and ("127.0.0.1", "/frame") in received:
                        break
                    await asyncio.sleep(0.02)
            forbidden = f"http://127.0.0.2:{outside.server_port}/forbidden"
            await browser.cdp_client.send.Runtime.evaluate(params={"expression": f"location.href={forbidden!r}"},
                                                           session_id=frames[0].session_id)
            async with asyncio.timeout(10):
                while not any(event == "navigation_blocked" and data["url"] == forbidden for event, data in records):
                    assert ("127.0.0.2", "/forbidden") not in received
                    await asyncio.sleep(0.02)
            assert ("127.0.0.2", "/forbidden") not in received
            guard.check()
        finally:
            await asyncio.wait_for(browser.kill(), 20)
            if guard:
                await guard.close()

    try:
        asyncio.run(asyncio.wait_for(run(), 60))
    finally:
        for item in (server, outside):
            item.shutdown()
            item.server_close()
        for thread in threads:
            thread.join(timeout=5)
