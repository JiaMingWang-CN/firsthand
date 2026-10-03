"""Evidence-backed private experience, before any disclosure filter."""

import hashlib
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from core.persona import Data, Text


class Completion(Data):
    outcome: Literal["success", "failed", "abandoned"]
    reason: Text


class Snapshot(Data):
    evidence_id: Text
    url: Text
    title: str
    text: str
    screenshot: Text
    screenshot_sha256: Text
    scroll_x: int
    scroll_y: int
    video_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def local_screenshot(self):
        path = PurePosixPath(self.screenshot)
        if path.is_absolute() or ".." in path.parts or "\\" in self.screenshot or ":" in self.screenshot:
            raise ValueError("Screenshot must be a relative artifact path")
        return self


class ExperienceStep(Data):
    step: int = Field(ge=1)
    before: Text
    after: Text
    seconds: float = Field(ge=0)
    actions: list[dict]
    results: list[dict]
    agent_observation: str
    stalled: bool


class Emotion(Data):
    step: int = Field(ge=1)
    satisfaction: int = Field(ge=1, le=5)
    confusion: int = Field(ge=1, le=5)
    reason: Text


class Finding(Data):
    kind: Literal["pain", "highlight"]
    title: Text
    description: Text
    evidence_ids: list[Text] = Field(min_length=1)
    technical_event_ids: list[Text]
    observed_quote: Text


class Assessment(Data):
    emotions: list[Emotion]
    findings: list[Finding]
    summary: Text


class ExperienceMemory(Data):
    persona_id: Text
    state_at_browse: Text
    assignment: dict
    expectations: list[str]
    outcome: Literal["success", "failed", "abandoned"]
    reason: Text
    outcome_source: Literal["agent_self_report", "runtime_limit", "infrastructure"]
    session: dict
    snapshots: list[Snapshot]
    steps: list[ExperienceStep]
    observed_technical_events: list[dict]
    assessment: Assessment | None
    infrastructure_errors: list[dict]

    @model_validator(mode="after")
    def resolve_evidence(self):
        snapshots = {item.evidence_id: item for item in self.snapshots}
        if len(snapshots) != len(self.snapshots):
            raise ValueError("Duplicate evidence id")
        if [step.step for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("Experience steps must be consecutive")
        for step in self.steps:
            if step.before not in snapshots or step.after not in snapshots:
                raise ValueError("Step references missing screenshot evidence")
            if snapshots[step.before].video_seconds > snapshots[step.after].video_seconds:
                raise ValueError("Step evidence has reversed timing")
        if self.assessment:
            technical = {item["event_id"]: item for item in self.observed_technical_events}
            if sorted(item.step for item in self.assessment.emotions) != [item.step for item in self.steps]:
                raise ValueError("Emotion curve must cover every step exactly once")
            for finding in self.assessment.findings:
                if any(eid not in snapshots for eid in finding.evidence_ids):
                    raise ValueError("Finding references missing evidence")
                observed = "\n".join(snapshots[eid].text for eid in finding.evidence_ids)
                if any(eid not in technical for eid in finding.technical_event_ids):
                    raise ValueError("Finding cites technical evidence this persona did not observe")
                observed += "\n".join(str(technical[eid]["data"]) for eid in finding.technical_event_ids)
                # A quote anchors even a subjective interpretation to captured page text.
                if finding.observed_quote not in observed:
                    raise ValueError("Finding quote is not present in its cited evidence")
        return self


def load_experience(run_dir):
    """Validate saved references and the actual screenshot bytes before consuming a memory."""
    run_dir = Path(run_dir)
    memory = ExperienceMemory.model_validate_json((run_dir / "experience.json").read_text(encoding="utf-8"))
    for snapshot in memory.snapshots:
        path = run_dir / snapshot.screenshot
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != snapshot.screenshot_sha256:
            raise ValueError("Screenshot missing or changed: " + snapshot.screenshot)
    return memory
