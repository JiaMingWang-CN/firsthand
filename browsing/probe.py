"""One read-only Browser Use task on Steel, with an independent CDP collector."""

import argparse
import asyncio
import json
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from browser_use import Agent, BrowserSession, ChatOpenAI
from playwright.async_api import async_playwright
from steel import AsyncSteel

from core.runtime import error_summary, require, require_capabilities, settings, write_json


async def probe_browser(config, run_dir, profile):
    require(config, "steel_api_key")
    run_dir = Path(run_dir)
    screenshots = run_dir / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    result = {"passed": False, "url": config["url"], "timezone": config["timezone"]}
    started = time.monotonic()
    session = None
    remote_browser = None
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
            async with async_playwright() as playwright:
                remote_browser = await playwright.chromium.connect_over_cdp(cdp_url)
                context = remote_browser.contexts[0]
                page = context.pages[0] if context.pages else await context.new_page()
                await page.set_viewport_size({"width": 1440, "height": 900})
                collector = await context.new_cdp_session(page)
                await collector.send("Emulation.setTimezoneOverride", {"timezoneId": config["timezone"]})
                await collector.send("Network.enable")
                await collector.send("Runtime.enable")
                await collector.send("Performance.enable")
                with (run_dir / "raw_trace.jsonl").open("w", encoding="utf-8") as trace:
                    counts = {}

                    def record(event, payload):
                        counts[event] = counts.get(event, 0) + 1
                        trace.write(json.dumps({"elapsed_seconds": round(time.monotonic() - started, 3),
                                                "event": event, "data": payload}, ensure_ascii=False) + "\n")
                        trace.flush()

                    for event in ["Runtime.consoleAPICalled", "Runtime.exceptionThrown", "Network.requestWillBeSent",
                                  "Network.responseReceived", "Network.loadingFailed", "Network.loadingFinished"]:
                        collector.on(event, lambda payload, name=event: record(name, payload))
                    response = await page.goto(config["url"], wait_until="domcontentloaded", timeout=60000)
                    title = await page.title()
                    result["page_title"] = title
                    result["http_status"] = response.status if response else None
                    result["observed_timezone"] = await page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
                    await collector.send("Runtime.evaluate", {"expression": "console.info('muchhuman phase0 collector attached')"})
                    capture_index = 0

                    async def capture(agent=None):
                        nonlocal capture_index
                        capture_index += 1
                        screenshot = screenshots / f"step_{capture_index:03d}.png"
                        await page.screenshot(path=str(screenshot))
                        metrics = await collector.send("Performance.getMetrics")
                        record("snapshot", {"url": page.url, "screenshot": str(screenshot.relative_to(run_dir)),
                                            "performance": metrics["metrics"]})

                    await capture()
                    browser_session = BrowserSession(cdp_url=cdp_url, allowed_domains=[urlsplit(config["url"]).hostname])
                    llm = ChatOpenAI(
                        model=config["model"], base_url=config["base_url"], api_key=config["api_key"],
                        timeout=60, max_retries=0, dont_force_structured_output=not profile["checks"]["json_schema"]["supported"],
                        add_schema_to_system_prompt=not profile["checks"]["json_schema"]["supported"],
                    )
                    agent = Agent(
                        task=f"Read the already open page at {config['url']}. Use the read-only evaluate tool to read "
                             "document.title and document.querySelector('h1')?.innerText. Confirm the heading against the screenshot, "
                             "then finish with done and report the exact title and heading. Do not use extract or find_elements "
                             "to search for the title. Only read: do not click links, submit forms, log in or change any data.",
                        llm=llm, browser_session=browser_session, use_vision=True,
                        max_actions_per_step=1, use_judge=False, enable_planning=False,
                        directly_open_url=False,
                    )
                    history = await asyncio.wait_for(agent.run(max_steps=5, on_step_end=capture), timeout=360)
                    await capture()
                    result["agent_success"] = history.is_successful()
                    result["agent_result"] = history.final_result()
                    result["title_verified"] = bool(title) and title.casefold() in (history.final_result() or "").casefold()
                    result["collector_counts"] = counts
                    result["passed"] = all([
                        result["agent_success"], result["title_verified"],
                        result["observed_timezone"] == config["timezone"],
                        response is not None and response.status < 400,
                        counts.get("Runtime.consoleAPICalled", 0) > 0,
                        counts.get("Network.responseReceived", 0) > 0,
                        counts.get("snapshot", 0) > 0,
                    ])
        except Exception as error:
            result["error"] = error_summary(error)
        finally:
            if browser_session:
                try:
                    await browser_session.kill()
                except Exception as error:
                    result["browser_cleanup_error"] = error_summary(error)
            if session:
                try:
                    await steel.sessions.release(session.id)
                    result["released"] = True
                except Exception as error:
                    result["release_error"] = error_summary(error)
                    result["passed"] = False
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
        result = {"passed": False, "error": error_summary(error)}
        write_json(args.run_dir / "browser_result.json", result)
    print("Steel + Browser Use: " + ("PASS" if result["passed"] else "FAIL"))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
