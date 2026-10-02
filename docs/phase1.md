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
- 模型按说明书补全全部身份、经历、性格、大五人格、MBTI、动机、作息、活跃概率和隐瞒原因。人物尚未真实体验产品。
- 10 个槽位并行生成（并发上限 30，目前 10 人即同时 10 个请求）。之后按编号检查姓名和用户名，与已接受角色重复的槽位串行重新生成，重新生成时会看到所有已接受角色；性别或年代分散不足时重生成最后一个槽位。
- 每次请求都会打印"第 N 次通过/不合法"、耗时和具体校验原因，重新生成的原因也会打印。
- 浏览限制由代码生成：低/中/高耐心的步数上限为 15/40/80，停滞上限为 4/8/12；只有开发者获得 Console/Network 查询工具。
- 本地校验包括必填字段、时区、跨午夜作息、活跃概率、身份唯一性、角色与流程匹配、权限和整个人群的分布。模型输出不合法时最多修正 3 次，不保存成成功草稿。
- 当前作息模型只表示一个连续睡眠窗口；为避免合成人设出现明显失衡的时间表，样本校验假设其长度为 4–12 小时，不支持分段睡眠。这个假设用于生成一致性，不是现实用户的作息统计。
- 作息是社区活跃的上限：整小时都在睡眠窗口内的 `activity_by_hour` 必须为 0。生成时代码直接清零，人工编辑时校验拒绝；睡眠起止所在的半醒小时仍可有概率。
- 逻辑时间线不区分日期和星期，`state_at_browse` 不能写星期几、周末、工作日或具体日期，否则换一天生成就会与时间线矛盾。
- 产品模型从说明书提取目标年龄范围（`target_age_min/max`，未写明则为 null）。年龄须落在该范围内，并至少覆盖 3 个年代；目标范围本身不足 3 个年代时按范围内的年代数要求。
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

批准记录绑定说明书、草稿与能力文件的 SHA-256。修改其中任意一个文件后，`require_approved()` 会拒绝沿用原审批。审核过程也会检查版本变化。阶段 1 的批准只确认计划，不触发执行；后续执行阶段须调用这个审批检查。

## 验证

```powershell
.venv-browsing/Scripts/python.exe -m pytest tests/test_phase0.py tests/test_thinking.py tests/test_phase1.py -q
.venv-oasis/Scripts/python.exe -m pytest tests/test_discussion_thinking.py -q
```

阶段 1 测试覆盖输入拒绝、生成分布、年龄范围与年代分散、跨时区与夏令时换算（洛杉矶、伦敦、加尔各答）、观察权限、睡眠时段及睡眠中的活跃概率、体验状态不绑定日期、能力文件变化使审批失效、未批准执行、编辑使审批失效、显式分布调整，以及 JSON 校验失败后的修正。真实生成样本停在待审核状态，Scout 和实际浏览仍未验证。

2026-10-02 实测（复核后重跑）：`runs/phase1-wjm/` 是首轮产物，其中 p10 在 `prepare` 之外另行修正，且按现行规则仍有睡眠中活跃、体验状态写死星期等问题，不再作为验收依据。现行代码一次完整执行 `prepare`（重新探测能力，未复用能力文件），产物在 `runs/phase1-wjm-r2/`：能力探测全部通过（本次提示词 JSON 和 8K 上下文也通过）；产品模型提取出目标年龄 20–55；10 人并行生成约 1.5 分钟，4 人首次不合法（3 次时区不是 IANA 名称，1 次体验时段落在睡眠中），第 2 次全部通过，无重名修复。分布、年龄范围、年代分散、睡眠活跃和日期绑定校验全部通过。

人工复核观察：年龄为 23–41 岁，没有 42–55 岁的角色；性别 7 女 3 男；多人动机都是"替公司评估外包"，背景同质化比串行生成时明显。p03 的体验状态句子不完整，部分用户名与姓名拼音不一致。这些都属于语义层面的问题，结构校验不能拦截，需要在人工审核中调整，或在维度矩阵中按槽位分配年龄段与动机类型。

浏览环境依赖检查通过；Scout 和实际浏览仍未验证。未创建样本的人工批准记录。
