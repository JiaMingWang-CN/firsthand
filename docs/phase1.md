# 阶段 1：说明书、Persona 与 CLI 审核

阶段 1 生成产品模型、10 个完整 Persona、作息和模拟配置，并停在人工审核。不会启动产品浏览或 OASIS 讨论。

## 阶段 0 的问题如何处理

已查阅阶段 0 修订说明和实际结果：模型、OASIS 已通过；浏览仍出现连接断开与 DOM 超时。当前只通过 Browser Use 操作和采集，复用它的 CDP 连接，不使用 Playwright 或内置 HAR。

按本次要求，浏览验证没有通过不阻断阶段 1。`scout.json` 明确记录 `pending`，不会把说明书、角色背景或阶段 0 基础设施问题写成真实产品发现。模型的基础对话、工具调用和识图仍需通过；同一模型的 JSON Schema 或提示词 JSON 至少一种必须经过验证。本次模型只能使用 JSON Schema，不能降级到未通过的提示词 JSON 路径。

## 安装与输入

使用已有 `.venv-browsing`：

```powershell
uv pip sync --python .venv-browsing/Scripts/python.exe browsing/requirements.lock.txt
```

新增 PyYAML 用于安全解析 front matter，tzdata 用于 Windows 上的 IANA 时区校验；其余沿用现有模型、Pydantic 和配置环境。

输入格式见 `product_manual_template.md`，验证样本见 `examples/wjm_product_manual.md`。样本基于已有个人网站截图和项目页观察日志，访客构成与作息是明确的假设，仍待站点所有者核对。

```powershell
.venv-browsing/Scripts/python.exe -m orchestrator.phase1 validate docs/examples/wjm_product_manual.md
.venv-browsing/Scripts/python.exe -m orchestrator.phase1 prepare docs/examples/wjm_product_manual.md
```

说明书在创建运行目录及调用 API 之前校验：必填元数据和章节、空内容、流程必填项、重复字段、域名、账号角色、账号中误填的密码等不合法时会拒绝并指出原因。`新访客` 对应无需注入账号凭据的 `new_visitor`；其他流程角色必须在 front matter 声明。

默认重新执行模型能力探测。开发诊断时可以显式复用同模型、同思考模式的能力文件：

```powershell
.venv-browsing/Scripts/python.exe -m orchestrator.phase1 prepare docs/examples/wjm_product_manual.md --capability-run runs/已有能力文件的目录
```

## 生成规则

- 先固定维度矩阵：2 名开发者、4 名手机用户、3 名低耐心用户；发帖/评论/点赞/潜水分布为 3/3/2/2，2 人有高隐瞒倾向，3 人自由探索。7 个指定任务的槽位循环分配关键流程，每个流程至少 2 人。
- 每人只指定一个流程，所以 10 人、3 人探索、每流程至少 2 人的组合最多支持 3 个关键流程。更多流程会在输入校验时明确拒绝，不会静默漏测；可合并流程或调整后续规模方案。
- 模型按说明书补全全部身份、经历、性格、大五人格、MBTI、动机、作息、活跃概率和隐瞒原因，后生成的人避免重复已有姓名、用户名和背景。人物尚未真实体验产品。
- 浏览限制由代码生成：低/中/高耐心的步数上限为 15/40/80，停滞上限为 4/8/12；只有开发者获得 Console/Network 查询工具。
- 本地校验包括必填字段、时区、跨午夜作息、活跃概率、身份唯一性、角色与流程匹配、权限和整个人群的分布。模型输出不合法时最多修正 3 次，不保存成成功草稿。
- 当前作息模型只表示一个连续睡眠窗口；为避免合成人设出现明显失衡的时间表，样本校验假设其长度为 4–12 小时，不支持分段睡眠。这个假设用于生成一致性，不是现实用户的作息统计。
- 默认逻辑时间线为 UTC 当日零点起 1 天，每片 60 分钟，并发 1。体验时刻按各人时区换算到该窗口内，`schedule.json` 保存本地日期、UTC 日期与时间片编号。这里只生成配置，不推进真实网站时间。
- 人设语义是否自洽、样本是否贴合目标人群仍是人工审核内容；结构校验不能证明这些合成角色代表真实用户。

## 审核与修改

生成目录包含：

| 文件 | 用途 |
|---|---|
| `manual.md` | 本轮说明书副本 |
| `capability_profile.json` | 同模型、同思考模式的能力探测 |
| `product_model.json` | 产品摘要、元数据、流程与原始章节 |
| `draft.json` | 可编辑的完整 Persona 和运行配置 |
| `review.md` | 完整人设与作息的阅读副本 |
| `schedule.json` | 按 UTC 排序的体验时间表 |
| `scout.json` | 未完成侦察的明确记录 |
| `phase1_result.json` | 生成验证结果与待审核状态 |
| `approval.json` | 人工操作之后才产生的批准或拒绝记录 |

```powershell
.venv-browsing/Scripts/python.exe -m orchestrator.phase1 review runs/生成的运行目录
```

CLI 支持 `show`、`reload`、`approve`、`reject`、`quit`。用编辑器修改 `draft.json`，输入 `reload` 重新校验和生成阅读副本。修改耐心时，步数与停滞限制也必须符合该等级；非开发者不能增加技术工具。

生成时严格满足方案的分布约束。人工修改如果改变分布，普通 `approve` 不接受；CLI 列明差异，用户明确输入 `approve overrides` 后才保存这些调整。字段合法性、观察权限、账号与流程匹配始终校验，不能通过这个命令绕过。

批准记录绑定说明书与草稿的 SHA-256。修改其中任意一个文件后，`require_approved()` 会拒绝沿用原审批。审核过程也会检查版本变化。阶段 1 的批准只确认计划，不触发执行；后续执行阶段须调用这个审批检查。

## 验证

```powershell
.venv-browsing/Scripts/python.exe -m pytest tests/test_phase0.py tests/test_thinking.py tests/test_phase1.py -q
.venv-oasis/Scripts/python.exe -m pytest tests/test_discussion_thinking.py -q
```

阶段 1 测试覆盖输入拒绝、生成分布、时区换算、观察权限、睡眠时段、未批准执行、编辑使审批失效、显式分布调整，以及 JSON 校验失败后的修正。真实生成样本停在待审核状态，Scout 和实际浏览仍未验证。

2026-10-02 实测：使用 `examples/wjm_product_manual.md` 和当前自定义模型完成 10 人生成，产物在 `runs/phase1-wjm/`。身份、背景、性格、作息、设备、参与方式、表达意愿和任务字段均完整；分布与两个关键流程的覆盖校验通过。凌晨角色曾出现过短的睡眠窗口，已由模型修正叙述与作息，并重新验证整个草稿。

34 项测试通过，浏览环境依赖检查通过。真实模型的基础对话、工具调用、识图与 JSON Schema 通过；提示词 JSON 和本次 8K 字符上下文样本未通过，结果保存在能力文件中，没有据此声称模型或阶段 0 的全部验证都通过。未创建样本的人工批准记录。
