"""Parse the fixed Markdown manual before making any model requests."""

import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from core.persona import Flow, ManualMetadata

REQUIRED = ["产品定位", "目标用户", "核心功能", "关键流程"]
OPTIONAL = ["竞品与替代方案", "已知问题", "本次关注点"]
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
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, flags=re.S)
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
    headings = list(re.finditer(r"^# ([^\n]+)\s*$", match[2], flags=re.M))
    sections = {}
    for index, heading in enumerate(headings):
        name = heading[1].strip()
        if name in sections:
            raise ValueError(f"章节重复：{name}")
        end = headings[index + 1].start() if index + 1 < len(headings) else len(match[2])
        sections[name] = match[2][heading.end():end].strip()
    unknown = set(sections) - set(REQUIRED + OPTIONAL)
    if unknown:
        raise ValueError("未知章节：" + "、".join(sorted(unknown)))
    missing = [name for name in REQUIRED if not sections.get(name)]
    if missing:
        raise ValueError("缺少必填章节或内容为空：" + "、".join(missing))
    feature_lines = [line.strip() for line in sections["核心功能"].splitlines() if line.strip()]
    if all(re.fullmatch(r"[-*]\s*[^：:]+[：:]\s*", line) for line in feature_lines):
        raise ValueError("核心功能只有占位名称，缺少功能描述")
    flow_headings = list(re.finditer(r"^## 流程：([^\n]+)\s*$", sections["关键流程"], flags=re.M))
    if not flow_headings:
        raise ValueError("关键流程至少需要一个 '## 流程：名称' 标题")
    flows = []
    for index, heading in enumerate(flow_headings):
        end = flow_headings[index + 1].start() if index + 1 < len(flow_headings) else len(sections["关键流程"])
        block = sections["关键流程"][heading.end():end]
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
    # Ten users, three exploring, and one assigned flow per remaining user.
    if len(flows) > 3:
        raise ValueError("10 人中 3 人自由探索，其余每人一个流程；每流程至少 2 人，因此最多 3 个关键流程")
    # Generation prompts never see the calibration set: persona text later enters the browsing prompt.
    generation_source = "---\n" + match[1] + "\n---\n\n" + "\n\n".join(
        f"# {name}\n\n{body}" for name, body in sections.items() if name != "已知问题")
    return {"source": source, "generation_source": generation_source, "metadata": metadata, "sections": sections, "flows": flows}
