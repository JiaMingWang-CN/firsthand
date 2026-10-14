"""Private disclosure and questionnaire contracts; public text is an explicit projection."""

from typing import Literal
from pydantic import Field

from core.persona import Data, Text

READ_ONLY = {"refresh", "do_nothing"}
ROLE_ACTIONS = {
    "poster": READ_ONLY | {"create_post", "create_comment", "like_post", "dislike_post"},
    "commenter": READ_ONLY | {"create_comment", "like_post", "dislike_post"},
    "reactor": READ_ONLY | {"like_post", "dislike_post"},
    "lurker": READ_ONLY,
}


class Withheld(Data):
    finding_id: Text
    reason: Text


class Disclosure(Data):
    shared: list[Text]
    withheld: list[Withheld]
    tone: Literal["direct", "soft", "brief"]


class ExitAnswer(Data):
    has_experience: bool
    nps: int | None = Field(ge=0, le=10)
    continue_using: Literal["yes", "no", "unsure"]
    would_pay: Literal["yes", "no", "unsure"]
    biggest_issue: str | None
    favorite: str | None
    unsaid: list[Withheld]
    opinion_changed: bool
    influencing_post_ids: list[int]
    explanation: Text


def finding_map(memory):
    if memory is None or memory.assessment is None:
        return {}
    return {f"{memory.persona_id}:f{index + 1:03d}": item for index, item in enumerate(memory.assessment.findings)}


def validate_disclosure(plan, memory, participation):
    ids = set(finding_map(memory))
    shared, hidden = set(plan.shared), {item.finding_id for item in plan.withheld}
    if len(shared) != len(plan.shared) or len(hidden) != len(plan.withheld):
        raise ValueError("Disclosure ids must be unique")
    if shared & hidden or shared | hidden != ids:
        raise ValueError("shared and withheld must partition this persona's finding ids exactly")
    if participation in {"lurker", "reactor"} and shared:
        raise ValueError("This participation mode cannot publish textual experiences")


def public_projection(plan, memory):
    facts = finding_map(memory)
    introductions = {"direct": "我这次用下来：", "soft": "对我来说，这次的感受是：", "brief": "使用感受："}
    if not plan.shared:
        return ""
    parts = [introductions[plan.tone]]
    for key in plan.shared:
        finding = facts[key]
        parts.append(f"{finding.title}。我看到的页面文字是“{finding.observed_quote}”。")
    return "\n".join(parts)


def allowed_actions(participation, experienced, public_body=""):
    allowed = set(ROLE_ACTIONS[participation]) if experienced else set(READ_ONLY)
    if not public_body:
        allowed -= {"create_post", "create_comment"}
    return allowed


def validate_exit(answer, memory, read_post_ids):
    experienced = memory is not None
    if answer.has_experience != experienced or ((answer.nps is not None) != experienced):
        raise ValueError("Survey must match actual experience availability; no fabricated NPS without experience")
    facts = finding_map(memory)
    referenced = [(field, key) for field, key in (("biggest_issue", answer.biggest_issue), ("favorite", answer.favorite)) if key]
    referenced += [(f"unsaid[{index}].finding_id", item.finding_id) for index, item in enumerate(answer.unsaid)]
    # Name the wrong values and the valid ids, so a retry can correct them instead of guessing again.
    unknown = [f"{field}={key!r}" for field, key in referenced if key not in facts]
    if unknown:
        raise ValueError("Survey references a finding this persona did not experience: " + ", ".join(unknown)
                         + f"; use only these finding_id values: {sorted(facts)}, or null/empty list")
    unread = [pid for pid in answer.influencing_post_ids if pid not in read_post_ids]
    if unread:
        raise ValueError(f"Opinion change must cite posts actually read by this persona: {unread} were not read; "
                         f"read post ids are {sorted(read_post_ids)}")
    if answer.opinion_changed != bool(answer.influencing_post_ids):
        raise ValueError("Opinion change flag must agree with cited influencing posts")


def consistency_flags(answer, memory, published_ids=()):
    facts, flags = finding_map(memory), []
    if answer.biggest_issue and facts[answer.biggest_issue].kind != "pain":
        flags.append("biggest_issue_cites_highlight")
    if answer.favorite and facts[answer.favorite].kind != "highlight":
        flags.append("favorite_cites_pain")
    if memory and memory.outcome != "success" and answer.nps is not None and answer.nps >= 9:
        flags.append("high_nps_after_unsuccessful_task_requires_review")
    if any(item.finding_id in published_ids for item in answer.unsaid):
        flags.append("unsaid_item_was_publicly_expressed_requires_review")
    return flags
