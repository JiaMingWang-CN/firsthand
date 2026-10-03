"""Private exit questionnaires, independent of the OASIS process lifecycle."""

import json

from core.community import ExitAnswer, consistency_flags, finding_map, validate_exit
from orchestrator.personas import request_json


def published_findings(store, pid):
    published = set()
    with store.connect() as db:
        for row in db.execute("SELECT d.shared_json,a.result_json FROM disclosures d JOIN actions a "
            "ON d.persona_id=a.persona_id AND d.slice_index=a.slice_index AND d.public_body=a.public_body "
            "WHERE d.persona_id=? AND a.action IN ('create_post','create_comment')", (pid,)):
            if json.loads(row["result_json"]).get("success"):
                published.update(json.loads(row["shared_json"]))
    return published


async def answer_exit(client, config, capability, persona, store):
    pid = persona.persona_id
    with store.connect() as db:
        if db.execute("SELECT 1 FROM surveys WHERE persona_id=?", (pid,)).fetchone():
            return
        hidden = [json.loads(row[0]) for row in db.execute("SELECT withheld_json FROM disclosures WHERE persona_id=?", (pid,))]
    memory = store.experience(pid)
    posts = store.read_posts(pid)
    if memory is None:
        result = ExitAnswer(has_experience=False, nps=None, continue_using="unsure", would_pay="unsure",
            biggest_issue=None, favorite=None, unsaid=[], opinion_changed=False, influencing_post_ids=[],
            explanation="尚无已校验的亲身体验，无法评价产品或给出 NPS；此为系统缺失标记，不是模型作答。")
    else:
        prompt = ("这是匿名且不公开的离场问卷。无论发帖、潜水或隐瞒，都完整回答真实私下体验；不要伪装成已体验。"
                  "NPS 为 0–10，未体验必须为 null。最大问题、最喜欢点、未说出口内容只引用自己的 finding_id；没有就为 null/空列表。"
                  "讨论影响只引用实际读过的帖子编号，不把其他人的话当自己的体验。\n"
                  + json.dumps({"persona": persona.model_dump(), "memory": memory.model_dump(exclude={"session"}),
                     "findings": {key: value.model_dump() for key, value in finding_map(memory).items()},
                     "withheld_turns": hidden, "read_posts": list(posts.values())}, ensure_ascii=False))
        result = await request_json(client, config, capability, ExitAnswer, prompt,
            validate=lambda item: validate_exit(item, memory, set(posts)), label=f"问卷 {pid}")
    validate_exit(result, memory, set(posts))
    store.survey(pid, result, consistency_flags(result, memory, published_findings(store, pid)))
