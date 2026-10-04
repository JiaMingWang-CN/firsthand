import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.media import by_step, media_position, segments, summarize

PLAYLIST = """#EXTM3U
#EXT-X-VERSION:6
#EXT-X-TARGETDURATION:4
#EXT-X-PROGRAM-DATE-TIME:2026-10-03T07:16:42.805871731Z
#EXTINF:4.000,
https://storage.example/segment_1.m4s?X-Amz-Signature=a
#EXT-X-PROGRAM-DATE-TIME:2026-10-03T07:16:46.805871731Z
#EXTINF:4.000,
https://storage.example/segment_2.m4s?X-Amz-Signature=b
#EXT-X-PROGRAM-DATE-TIME:2026-10-03T07:17:00.805871731Z
#EXTINF:4.000,
https://storage.example/segment_3.m4s?X-Amz-Signature=c
#EXT-X-ENDLIST
"""


def at(second):
    return datetime(2026, 10, 3, 7, 16, 42, 805871, tzinfo=timezone.utc) + timedelta(seconds=second)


def event(event_id, name, data, seconds=1.0):
    return {"event_id": event_id, "video_seconds": seconds, "event": name, "data": data}


TRACE = [
    event("t1", "Network.requestWillBeSent", {"requestId": "r1", "request": {"url": "https://example.com/app.js?token=SECRET-QUERY", "method": "GET",
                                                                              "headers": {"Cookie": "sid=SECRET-COOKIE"}}}),
    event("t2", "Network.responseReceivedExtraInfo", {"requestId": "r1", "statusCode": 503, "headers": {"set-cookie": "sid=SECRET-COOKIE"}}),
    event("t3", "Network.responseReceivedExtraInfo", {"requestId": "r1", "statusCode": 503, "headers": {}}),
    event("t4", "Network.loadingFailed", {"requestId": "r1", "errorText": "net::ERR_ABORTED", "canceled": True}, 1.5),
    event("t5", "Runtime.consoleAPICalled", {"type": "warning", "args": [{"type": "string", "value": "slow chunk"}]}, 2.5),
    event("t6", "Runtime.consoleAPICalled", {"type": "log", "args": [{"type": "string", "value": "Removing 0 browser-use highlight elements"}]}, 2.6),
    event("t7", "Network.requestWillBeSent", {"requestId": "r2", "request": {"url": "https://example.com/ok", "method": "GET"}}, 2.7),
    event("t8", "Runtime.exceptionThrown", {"exceptionDetails": {"text": "Uncaught", "exception": {"description": "TypeError: x is undefined"}}}, 3.0),
]


def test_trace_summary_keeps_errors_and_drops_headers_queries_and_agent_logs():
    lines = summarize(TRACE)
    assert [(line["event_id"], line["type"], line["level"], line["text"]) for line in lines] == [
        ("t2", "network", "error", "GET https://example.com/app.js 503"),
        ("t4", "network", "info", "GET https://example.com/app.js net::ERR_ABORTED"),
        ("t5", "console", "warn", "slow chunk"),
        ("t8", "console", "error", "TypeError: x is undefined")]
    assert "SECRET" not in json.dumps(lines)


def test_trace_lines_belong_to_the_step_that_was_on_screen():
    steps = [{"step": 1, "before": "a"}, {"step": 2, "before": "b"}]
    snapshots = {"a": {"video_seconds": 2.0}, "b": {"video_seconds": 3.0}}
    owned = by_step(steps, snapshots, summarize(TRACE))
    assert [line["event_id"] for line in owned[1]] == ["t2", "t4", "t5"]  # before the first snapshot counts as step 1
    assert [line["event_id"] for line in owned[2]] == ["t8"]


def test_media_position_follows_the_playlist_clock_across_gaps():
    parts = segments(PLAYLIST)
    assert [(start, duration) for _, start, duration in parts] == [(0, 4), (4, 4), (8, 4)]
    assert media_position(parts, at(1.5)) == 1.5
    assert media_position(parts, at(5)) == 5
    assert media_position(parts, at(10)) == 8  # not recorded: snap to the end of the segment before the gap
    assert media_position(parts, at(19)) == 9
    assert media_position(parts, at(-1)) is None and media_position(parts, at(30)) is None


class FakeRecordings:
    def __init__(self):
        self.calls = []

    def playlist(self, session_id):
        self.calls.append(session_id)
        return PLAYLIST


def with_session(run):
    session = {"id": "session-1", "viewer_url": None, "created_at": "2026-10-03T07:16:42.805871+00:00"}
    memory = json.loads((run / "p01" / "experience.json").read_text(encoding="utf-8"))
    memory["session"] = session
    (run / "p01" / "experience.json").write_text(json.dumps(memory, ensure_ascii=False), encoding="utf-8")
    with sqlite3.connect(run / "run.db") as db:
        db.execute("UPDATE experiences SET memory_json=? WHERE persona_id='p01'", (json.dumps(memory),))


@pytest.fixture
def traced(runs_root):
    run = runs_root / "phase4-x"
    (run / "p01" / "raw_trace.jsonl").write_text("\n".join(json.dumps(item) for item in TRACE) + "\n", encoding="utf-8")
    return runs_root


def test_experience_steps_carry_trace_summaries(traced):
    body = TestClient(create_app(traced)).get("/api/runs/phase4-x/personas/p01/experience").json()
    assert [line["event_id"] for line in body["steps"][0]["trace"]] == ["t2", "t4", "t5", "t8"]
    assert "SECRET" not in json.dumps(body)


def test_trace_evidence_is_served_as_a_summary_only(traced):
    client = TestClient(create_app(traced))
    response = client.get("/api/runs/phase4-x/evidence/p01:trace:t2")
    assert response.status_code == 200 and response.json()["data"]["text"].endswith("503")
    for ref in ["p01:trace:t1", "p01:trace:t2"]:
        assert "SECRET" not in client.get(f"/api/runs/phase4-x/evidence/{ref}").text


def test_recording_maps_every_snapshot_into_the_played_video(runs_root):
    with_session(runs_root / "phase4-x")
    recordings = FakeRecordings()
    client = TestClient(create_app(runs_root, recordings=recordings))
    body = client.get("/api/runs/phase4-x/personas/p01/recording").json()
    assert body["seek"] == {"before": 1, "after": 2}
    assert body["playlist_url"] == "/api/runs/phase4-x/personas/p01/recording.m3u8"
    playlist = client.get(body["playlist_url"])
    assert playlist.status_code == 200 and playlist.text == PLAYLIST
    assert playlist.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    assert recordings.calls == ["session-1", "session-1"]


def test_recording_errors(runs_root):
    assert TestClient(create_app(runs_root, recordings=FakeRecordings())).get("/api/runs/phase4-x/personas/p01/recording").status_code == 404
    with_session(runs_root / "phase4-x")
    assert TestClient(create_app(runs_root)).get("/api/runs/phase4-x/personas/p01/recording").status_code == 503
