"""Parse the fixed Markdown manual before making any model requests."""

import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from core.persona import DEFAULT_FORBIDDEN, Flow, ManualMetadata

# Only url and allowed_domains are required; every section is optional, and what is missing lowers the
# reference value of the result (material()).
SECTIONS = ["产品定位", "目标用户", "核心功能", "关键流程", "竞品与替代方案", "已知问题", "本次关注点"]
FLOW_FIELDS = {"适用账号": "account_role", "入口": "entry", "主要步骤": "steps",
               "期望结果": "expected_result", "成功标准": "success_criteria"}


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(keys) != len(set(keys)):
            raise ValueError("YAML contains duplicate fields")
        return super().construct_mapping(node, deep=deep)

def read_manual(path):
    source = Path(path).read_text(encoding="utf-8-sig")
    text = re.sub(r"<!--.*?-->", "", source, flags=re.S)
    match = re.match(r"\A---\s*\n(.*?)\n---[ \t]*(?:\n(.*))?\Z", text, flags=re.S)
    if not match:
        raise ValueError("说明书缺少 YAML front matter（开头和结尾的 ---）")
    try:
        metadata = ManualMetadata.model_validate(yaml.load(match[1], Loader=UniqueLoader))
    except yaml.YAMLError as error:
        raise ValueError("YAML 格式不合法：" + str(getattr(error, "problem", "请检查 front matter"))) from error
    url = urlsplit(metadata.url)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
        raise ValueError("url 必须是无账号密码的 HTTP(S) 地址")
    if any(urlsplit("https://" + host).hostname != host or "/" in host or "*" in host
           for host in metadata.allowed_domains):
        raise ValueError("allowed_domains 只接受完整主机名，不含协议、路径或通配符")
    if url.hostname not in metadata.allowed_domains:
        raise ValueError("url 的主机名必须包含在 allowed_domains 中")
    roles = [account.role for account in metadata.test_accounts]
    if len(roles) != len(set(roles)):
        raise ValueError("test_accounts 的 role 不能重复")
    body = match[2] or ""
    headings = list(re.finditer(r"^# ([^\n]+)\s*$", body, flags=re.M))
    sections = {}
    for index, heading in enumerate(headings):
        name = heading[1].strip()
        if name in sections:
            raise ValueError(f"章节重复：{name}")
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        sections[name] = body[heading.end():end].strip()
    unknown = set(sections) - set(SECTIONS)
    if unknown:
        raise ValueError("未知章节：" + "、".join(sorted(unknown)))
    # An empty section (such as the template's comment-only placeholder) counts as not provided.
    sections = {name: content for name, content in sections.items() if content}
    feature_lines = [line.strip() for line in sections.get("核心功能", "").splitlines() if line.strip()]
    if feature_lines and all(re.fullmatch(r"[-*]\s*[^：:]+[：:]\s*", line) for line in feature_lines):
        raise ValueError("核心功能只有占位名称，缺少功能描述；不写可以删掉这一节")
    flow_text = sections.get("关键流程", "")
    flow_headings = list(re.finditer(r"^## 流程：([^\n]+)\s*$", flow_text, flags=re.M))
    if flow_text and not flow_headings:
        raise ValueError("关键流程需要用 '## 流程：名称' 标题写每条流程；不写可以删掉这一节")
    flows = []
    for index, heading in enumerate(flow_headings):
        end = flow_headings[index + 1].start() if index + 1 < len(flow_headings) else len(flow_text)
        block = flow_text[heading.end():end]
        fields = {}
        for label, value in re.findall(r"^- ([^：\n]+)：([^\n]*)$", block, flags=re.M):
            if label in FLOW_FIELDS:
                if label in fields:
                    raise ValueError(f"流程 {heading[1]} 字段重复：{label}")
                fields[label] = value.strip()
        missing = [label for label in FLOW_FIELDS if not fields.get(label)]
        if missing:
            raise ValueError(f"流程 {heading[1]} 缺少：" + "、".join(missing))
        values = {key: fields[label] for label, key in FLOW_FIELDS.items()}
        if values["account_role"] == "新访客":
            values["account_role"] = "new_visitor"
        if values["account_role"] not in set(roles) | {"new_visitor"}:
            raise ValueError(f"流程 {heading[1]} 引用了未知账号角色")
        flows.append(Flow(name=heading[1].strip(), **values))
    if len({flow.name for flow in flows}) != len(flows):
        raise ValueError("关键流程名称不能重复")
    # Generation prompts never see the calibration set: persona text later enters the browsing prompt.
    # The front matter is re-serialized so defaults (name, forbidden actions) are what the model sees.
    generation_source = "---\n" + yaml.safe_dump(metadata.model_dump(), allow_unicode=True, sort_keys=False) + "---\n\n" + "\n\n".join(
        f"# {name}\n\n{content}" for name, content in sections.items() if name != "已知问题")
    defaults = [key for key in ("name", "test_accounts", "forbidden_actions") if key not in (yaml.safe_load(match[1]) or {})]
    return {"source": source, "generation_source": generation_source, "metadata": metadata, "sections": sections, "flows": flows,
            "defaults": defaults}


# What a missing part of the manual costs the result; shown before generation, on review and in the report.
GAPS = [
    ("产品定位", lambda m: "产品定位" in m["sections"], "产品定位由 AI 根据首页内容推断"),
    ("目标用户", lambda m: "目标用户" in m["sections"], "人群分布（年龄、设备、技术水平、时段）是 AI 的假设，未必像真实用户"),
    ("核心功能", lambda m: "核心功能" in m["sections"], "功能清单由 AI 根据首页内容推断"),
    ("关键流程", lambda m: bool(m["flows"]), "没有指定任务，所有人自由探索；重要流程可能没人走到"),
    ("test_accounts", lambda m: bool(m["metadata"].test_accounts), "只能以未登录的新访客身份体验，登录后的功能不会被覆盖"),
    ("forbidden_actions", lambda m: "forbidden_actions" not in m["defaults"], "使用默认禁止操作：" + "、".join(DEFAULT_FORBIDDEN)),
]


def material(manual):
    """How much the result can be relied on, judged only from what the manual supplies."""
    gaps = [{"item": item, "effect": effect} for item, present, effect in GAPS if not present(manual)]
    described = sum(name in manual["sections"] for name in ("产品定位", "目标用户", "核心功能"))
    level = "limited" if described == 0 else "partial" if gaps else "complete"
    summary = {"complete": "资料完整", "partial": "资料不全，部分结果依赖 AI 的假设",
               "limited": "资料很少，本次结果参考性有限：产品理解和人群分布主要来自 AI 推断"}[level]
    return {"level": level, "summary": summary, "gaps": gaps}
