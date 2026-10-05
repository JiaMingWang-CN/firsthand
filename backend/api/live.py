"""Watching a simulation while it runs.

While phase 4 is running each persona's directory already holds what a watcher wants: session.json (the Steel
session, written when the browser opens), screenshots (written step by step) and pNN.log (Browser Use's own step log:
evaluation, memory, next goal, action). experience.json and phase4_result.json only appear at the end, so the
run-reading endpoints cannot serve this; this module reads the raw files directly and only exposes
what a watcher needs: never the task prompt (it carries the full persona dossier), raw CDP events or the Steel
session beyond its viewer link.
"""

import re

from api.jobs import read_json
from api.runs import NotFound
from core.runtime import redact

PERSONA = re.compile(r"p\d{2,3}")
SHOT = re.compile(r"s\d{3,4}_(before|after)\.png")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
STEP = re.compile(r"📍 Step (\d+):")
LINE = re.compile(r"^(?:INFO|WARNING)\s+\[Agent\]\s+(?:[^\w\s]\S*\s+)?(Eval|Memory|Next goal):\s*(.*)$")
ACTION = re.compile(r"^INFO\s+\[Agent\]\s+▶️\s+(\w+):\s*(.*)$")
RESULT = re.compile(r"^INFO\s+\[tools\]\s+(.*)$")
TAIL_BYTES = 400_000
LIMIT = {"eval": 300, "memory": 400, "goal": 300, "action": 200, "result": 160}


def clip(text, limit):
    text = redact(text.strip())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def steps_from_log(path, shots):
    """Parse the Browser Use step log. Only the last TAIL_BYTES are read, so a long log stays cheap to poll."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    steps, current = [], None
    for raw in ANSI.sub("", text).splitlines():
        found = STEP.search(raw)
        if found:
            current = {"n": int(found.group(1)), "eval": "", "memory": "", "goal": "", "actions": [], "results": []}
            steps.append(current)
            continue
        if current is None:
            continue
        line = LINE.match(raw)
        if line:
            key = {"Eval": "eval", "Memory": "memory", "Next goal": "goal"}[line.group(1)]
            current[key] = clip(line.group(2), LIMIT[key])
            continue
        action = ACTION.match(raw)
        if action:
            current["actions"].append(clip(f"{action.group(1)} {action.group(2)}", LIMIT["action"]))
            continue
        result = RESULT.match(raw)
        if result and len(current["results"]) < 3:
            current["results"].append(clip(result.group(1), LIMIT["result"]))
    for step in steps:
        shot = f"s{step['n']:03d}_after.png" if f"s{step['n']:03d}_after.png" in shots else f"s{step['n']:03d}_before.png"
        step["screenshot"] = shot if shot in shots else None
    return steps


def persona_view(run, persona_id, job_state):
    folder = run / persona_id
    persona = read_json(folder / "persona.json", {}) or {}
    session = read_json(folder / "session.json", {}) or {}
    shots = sorted(item.name for item in (folder / "screenshots").glob("*.png")) if (folder / "screenshots").is_dir() else []
    return {"id": persona_id, "name": persona.get("realname"), "profession": persona.get("profession"), "age": persona.get("age"),
            "city": persona.get("city"), "state": job_state.get("state", "pending"), "local_time": job_state.get("local_time"),
            "started_at": job_state.get("started_at"), "finished_at": job_state.get("finished_at"),
            "viewer_url": session.get("viewer_url") if job_state.get("state") == "running" else None,
            "shots": shots}


def live(root, job, persona_id=None):
    """Per-persona state plus the step-by-step view of one persona (default: the one running now, else the last)."""
    run = root / job["simulation"]
    if not run.is_dir():
        return {"personas": [], "selected": None}
    timeline = read_json(run / "timeline.json", {}) or {}
    states = timeline.get("jobs", {})
    ids = sorted(states, key=lambda item: states[item].get("started_at") or "")
    personas = [persona_view(run, pid, states[pid]) for pid in ids if PERSONA.fullmatch(pid) and (run / pid).is_dir()]
    if persona_id is not None and persona_id not in {item["id"] for item in personas}:
        raise NotFound(f"Unknown persona in this job: {persona_id}")
    chosen = persona_id or next((item["id"] for item in personas if item["state"] == "running"), personas[-1]["id"] if personas else None)
    selected = None
    if chosen:
        view = next(item for item in personas if item["id"] == chosen)
        steps = steps_from_log(run / f"{chosen}.log", set(view["shots"]))
        selected = {**view, "steps": steps}
    return {"personas": [{key: value for key, value in item.items() if key != "shots"} for item in personas], "selected": selected}


def screenshot(root, job, persona_id, name):
    path = root / job["simulation"] / persona_id / "screenshots" / name
    if not PERSONA.fullmatch(persona_id) or not SHOT.fullmatch(name) or not path.is_file():
        raise NotFound(f"No such screenshot: {persona_id}/{name}")
    resolved, base = path.resolve(), (root / job["simulation"]).resolve()
    if not resolved.is_relative_to(base):
        raise NotFound(f"No such screenshot: {persona_id}/{name}")
    return resolved
