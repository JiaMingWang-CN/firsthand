"""Side-channel media for the UI: per-step Console/Network summaries and the Steel recording timeline.

Raw CDP events carry full request/response headers (cookies included), so only a summary leaves the server.
"""

import re
import time
from bisect import bisect_right
from datetime import datetime
from urllib.parse import urlsplit

import httpx

CONSOLE_LEVEL = {"warning": "warn", "assert": "error"}
# Browser Use logs from scripts it injects into the page; those lines are the agent's, not the product's.
AGENT_LOG = re.compile(r"browser-use", re.IGNORECASE)


def short_url(url):
    """Origin and path only: query strings may carry tokens."""
    parts = urlsplit(url or "")
    return f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.netloc else (url or "")[:200]


def console_text(data):
    values = [str(arg.get("value", arg.get("description", arg.get("type", "")))) for arg in data.get("args", [])]
    return " ".join(values)[:300]


def summarize(events):
    """Console messages, failed requests and HTTP errors, as {event_id, type, level, text, video_seconds}."""
    requests, lines, seen = {}, [], set()
    for event in events:
        name, data = event.get("event"), event.get("data") or {}
        line = None
        if name == "Network.requestWillBeSent":
            requests[data.get("requestId")] = (data.get("request", {}).get("method", "GET"), short_url(data.get("request", {}).get("url")))
        elif name == "Network.responseReceivedExtraInfo" and (data.get("statusCode") or 0) >= 400:
            method, url = requests.get(data.get("requestId"), ("", ""))
            line = ("network", "error", f"{method} {url} {data['statusCode']}".strip())
        elif name == "Network.loadingFailed":
            method, url = requests.get(data.get("requestId"), ("", ""))
            line = ("network", "info" if data.get("canceled") else "error", f"{method} {url} {data.get('errorText', '')}".strip())
        elif name == "Runtime.consoleAPICalled" and not AGENT_LOG.search(console_text(data)):
            line = ("console", CONSOLE_LEVEL.get(data.get("type"), data.get("type", "log")), console_text(data))
        elif name == "Runtime.exceptionThrown":
            details = data.get("exceptionDetails", {})
            line = ("console", "error", str(details.get("exception", {}).get("description") or details.get("text", ""))[:300])
        if line and name.startswith("Network."):  # CDP may repeat an event for the same request
            if (name, data.get("requestId")) in seen:
                continue
            seen.add((name, data.get("requestId")))
        if line:
            lines.append({"event_id": event["event_id"], "type": line[0], "level": line[1], "text": line[2],
                          "video_seconds": event.get("video_seconds")})
    return lines


def by_step(steps, snapshots, lines):
    """A step owns the events from its 'before' snapshot until the next step's; earlier ones go to step 1."""
    starts = [snapshots[step["before"]]["video_seconds"] for step in steps]
    owned = {step["step"]: [] for step in steps}
    for line in lines:
        if steps:
            index = max(0, bisect_right(starts, line["video_seconds"] or 0) - 1)
            owned[steps[index]["step"]].append(line)
    return owned


# —— Steel recording ——

def parse_time(value):
    # Steel writes nanoseconds; datetime takes microseconds.
    value = re.sub(r"(\.\d{6})\d+", r"\1", value.strip()).replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def segments(playlist):
    """[(program_date_time, media_start, duration)] for each media segment of an HLS playlist."""
    out, pending, start = [], None, 0.0
    for line in playlist.splitlines():
        if line.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            pending = parse_time(line.split(":", 1)[1])
        elif line.startswith("#EXTINF:"):
            duration = float(line.split(":", 1)[1].split(",")[0])
            if pending is not None:
                out.append((pending, start, duration))
            start += duration
            pending = None
    return out


def media_position(parts, wall):
    """Position in the played video of a wall-clock moment; None when it falls outside the recording."""
    if not parts or wall < parts[0][0]:
        return None
    index = max(i for i, part in enumerate(parts) if part[0] <= wall)
    pdt, start, duration = parts[index]
    offset = (wall - pdt).total_seconds()
    if offset > duration and index == len(parts) - 1:
        return None
    return round(start + min(offset, duration), 3)  # inside a recording gap: snap to the segment end


class RecordingUnavailable(RuntimeError):
    """The Steel key is not configured or Steel did not return the recording."""


class SteelRecordings:
    """Fetches HLS playlists with the server's Steel key; segment links in them are pre-signed for hours."""

    TTL = 600

    def __init__(self, api_key, base="https://api.steel.dev"):
        self.api_key, self.base, self._cache = api_key, base, {}

    def playlist(self, session_id):
        if not self.api_key:
            raise RecordingUnavailable("STEEL_API_KEY is not configured on the API server")
        cached = self._cache.get(session_id)
        if cached and time.monotonic() - cached[0] < self.TTL:
            return cached[1]
        try:
            response = httpx.get(f"{self.base}/v1/sessions/{session_id}/hls", headers={"steel-api-key": self.api_key}, timeout=30)
        except httpx.HTTPError as error:
            raise RecordingUnavailable(f"Steel recording request failed: {type(error).__name__}") from error
        if response.status_code != 200 or not response.text.startswith("#EXTM3U"):
            raise RecordingUnavailable(f"Steel returned no recording for this session (HTTP {response.status_code})")
        self._cache[session_id] = (time.monotonic(), response.text)
        return response.text
