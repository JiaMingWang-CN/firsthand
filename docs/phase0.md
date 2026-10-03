# 阶段 0：技术验证与运行方式

## 安装与配置

浏览与模型探测使用 Python 3.12，OASIS 使用 Python 3.11。camel-oasis 0.2.5 的 Python 声明为 `>=3.10,<3.12`，不能与浏览环境直接共用。

在项目根目录执行：

```powershell
uv venv --python 3.12 .venv-browsing
uv venv --python 3.11 .venv-oasis
uv pip sync --python .venv-browsing/Scripts/python.exe browsing/requirements.lock.txt
uv pip sync --python .venv-oasis/Scripts/python.exe discussion/requirements.lock.txt
Copy-Item config/.env.example config/.env
```

最后一条仅用于首次配置；已有配置时不要覆盖。填入 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、`STEEL_API_KEY`，并设置允许测试的 `PROBE_URL`。

模型思考开关配置在 `config/.env`：

```dotenv
LLM_THINKING_TYPE=disabled
```

`enabled` 开启，`disabled` 关闭，留空不发送该参数并采用服务端默认。当前厂商使用请求体 `{"thinking":{"type":"enabled"}}` / `{"thinking":{"type":"disabled"}}`；这不是跨厂商通用协议。换用不支持 `thinking.type` 的厂商时应先留空，不会自动转换为其他厂商的开关。

模型探测、Browser Use 和 OASIS 都发送同一配置。Browser Use 0.13.10 没有暴露 `extra_body`，由项目的 `ProviderChatOpenAI` 在新建的 SDK 客户端上绑定参数，保留原有消息序列化和结构化响应校验；配置此参数时也关闭按模型名称自动添加 OpenAI `reasoning_effort`。此开关控制模型服务端思考，不改变 Browser Use 的 Agent 提示词思考字段。

接口类型同样配置在 `config/.env`：

```dotenv
LLM_API=chat_completions
```

可选值有两个：`chat_completions`（默认，留空也是它）和 `responses`。能力探测和阶段 1 生成（`core/llm.py`）会按这个设置调用对应接口：图片、工具、`tool_choice`、JSON Schema（Responses 下改用 `text.format`）都会转换为 Responses 的请求格式，返回结果统一整理成同一种消息结构。

Browser Use 0.13.10 的 `ChatOpenAI` 和 OASIS 依赖的 CAMEL 0.2.78 只支持 Chat Completions，因此选 `responses` 时这两部分降级为 Chat Completions，终端会打印降级提示，`browser_result.json`、`oasis_result.json` 会记录 `llm_api` 和 `fallback_from`。能力文件记录 `api`，切换接口后必须重新探测。

Responses 下的思考开关不发送 `thinking.type`。`LLM_THINKING_TYPE=disabled` 时发送 `"reasoning": {"effort": "none"}`；`enabled` 或留空时不发送，采用服务端默认（实测默认开启思考）。

2026-10-02 用 `deepseek-flash` 测试 Responses：

- 最初仍发送 `thinking.type`，`forced_tool` 不通过，服务端报"Thinking mode does not support this tool_choice"。
- 改为 `reasoning.effort=none` 后，全部检查通过，包括 `forced_tool`、识图和 JSON Schema（Chat Completions 下 JSON Schema 不通过）。

能力文件记录 `thinking_type`。切换模式后，应重新运行模型能力探测；浏览和讨论会拒绝使用另一模式的能力文件。当前厂商的最小真实调用已验证：关闭时未返回 `reasoning_content`，开启时返回该字段，两个模式均正确回答；三处请求传参和模式切换校验已通过测试。

当前 Windows 环境的完整依赖版本保存在两个 `requirements.lock.txt`；直接依赖列在 `requirements.txt`。OASIS 环境固定 MCP 1.29.0，避免 MCP 2.x 移除 `mcp.server.FastMCP` 的导入冲突，并固定 NumPy 1.26.4 配合 OASIS 的 Pandas 2.2.2。

`.env`、虚拟环境和 `runs/` 不进入 Git。运行日志可能包含浏览器连接地址，属于私有运行产物。

## 执行

```powershell
.venv-browsing/Scripts/python.exe -m orchestrator.phase0
```

每次创建新的 `runs/phase0-<UTC时间>/` 目录。先探测模型，再通过两个独立子进程运行浏览和讨论验证。模型基础对话、单工具调用或任意识图样本失败，会中止后续执行。完整验证通过返回退出码 0，否则返回非零退出码。

需要诊断单项时，可使用同一运行目录的能力文件：

```powershell
.venv-browsing/Scripts/python.exe -m probe.model --run-dir runs/my-probe
.venv-browsing/Scripts/python.exe -m browsing.probe --run-dir runs/my-probe
.venv-oasis/Scripts/python.exe -m discussion.probe --run-dir runs/my-probe
.venv-browsing/Scripts/python.exe -m pytest tests -q
```

OASIS 不覆盖已有数据库；重试讨论验证应使用新运行目录和对应模型能力文件。

## 验证内容与产物

| 项目 | 判定依据 | 产物 |
|---|---|---|
| 基础对话 | 正确返回随机字符串 | `capability_profile.json` |
| 工具调用 | 单工具、强制工具、并行工具的名称和参数正确 | 同上 |
| JSON | JSON Schema 与提示词约束分别验证 | 同上 |
| 识图 | 两张随机数字图片均识别正确，答案不出现在请求文本中 | 同上及 `vision_challenge_*.png` |
| 上下文与并发 | 2K/8K/32K 字符样本、10 个同时发出的请求 | 同上，含延迟和服务端 token 用量 |
| Steel 与 Browser Use | Agent 通过点击页面元素跳转到同域名下的另一页面；DOM 构建无超时；首页文档返回成功状态；浏览器时区正确 | `browser_result.json`、会话查看链接 |
| 旁路采集 | 复用 Browser Use 的 CDP 连接，接收到 Console 与 Network 事件，保存每步截图和性能指标 | `raw_trace.jsonl`、`screenshots/` |
| OASIS | 外部驱动两步：手动发帖，再让两个 Agent 执行模型动作；核对动作工具集合与数据库记录 | `oasis.db`、`oasis_result.json` |
| 总体结果 | 三项子进程均成功 | `phase0_result.json` |

讨论验证中，发帖者拥有发帖、评论、看帖和不行动能力；潜水者仅有看帖和不行动能力。OASIS 会在模型调用前自动刷新信息流，因此验证排除这次自动刷新，防止将模型失败误判为成功。

## 实测与边界

当前状态：2026-10-02 三项全部通过（见文末“2026-10-02 复测”一节）。此前浏览验证受本机到 Steel 的链路带宽限制未通过（见“修订”一节）。

实测网站为 `https://wjm.dpdns.org`，模型为用户配置的 `mimo-v2.6-flash`。基础对话、工具调用、JSON Schema、两张随机图片、三个上下文样本及十并发请求均通过；提示词约束 JSON 未通过，因此该模型只能使用 JSON Schema 路径。OASIS 完成了手动发帖、模型评论和潜水者的不行动。5 项回归测试通过，两个虚拟环境均通过 `uv pip check`。运行产物含私有连接信息，不纳入提交。

> 历史记录：`runs/phase0-20261002T144412094316Z` 曾经三项全部通过，但当时使用 Playwright 采集，且浏览任务只用脚本读取标题、绕开了 DOM，不能证明 Agent 能操作页面。该结果已作废，以修订后的验证标准为准。

Steel 会话寿命显式设为 10 分钟（服务端返回 `timeout=600000`），浏览任务有 6 分钟上限，结束时主动释放会话。

出错时，结果 JSON 只记录错误类型和状态码；脱敏后的完整调用栈写入运行目录的 `errors.log`（替换已配置的密钥以及 `apiKey=`、`token=`、`Bearer` 后的内容）。

- 32K 是测试输入的字符数，不是声明的 token 上限；并发通过也不代表长期限流或吞吐保证。
- 视频未探测，保留截图序列回放方案；没有音频产品用例，因此音频未探测。
- 时区覆盖只改变浏览器时区，不改变 UTC 时钟，也不设置语言区域；模拟时间片不能据此改变真实网站的服务端时间。
- 旁路采集对 Agent 当前聚焦的每个页面会话设置时区并开启 Runtime、Network、Performance；跨 target iframe 和浏览器级全量采集尚未验证。
- 当前保存的是 Steel 会话查看链接，独立录像文件的导出和时间点跳转尚未验证。
- OASIS 的 `available_actions` 限制模型可调用的工具；空列表会开放全部动作，外部 `ManualAction` 也不会自动受这份列表约束。后续权限网关必须在编排层校验，不能只依赖 SDK 参数。
- OASIS 默认 Reddit 时钟仍按现实耗时放大，外部 `env.step` 可控制执行哪些 Agent，但没有自动实现方案中的逻辑时钟；阶段 4 需要显式对齐模拟时间。
- 本阶段只浏览网页（点击链接跳转），不提交表单、不登录；Persona、产品说明校验、体验记忆、真实体验与讨论交织、观察权限网关均属于后续阶段。

## 修订：只使用 Browser Use（2026-10-02）

项目约定只通过 Browser Use 操作和采集浏览器，已移除 Playwright（包括 `greenlet`、`pyee`），锁文件已同步更新。

- 原先的方案是 Playwright 和 Browser Use 各开一条 CDP 连接，连接同一个 Steel 会话。实测出现 23 次重复响应，并且每一步构建 DOM 都超时。改为共用一条连接后，重复响应降为 0。
- 浏览验证从"用脚本读取标题"升级为"点击页面元素跳转"。之前的任务绕开了 DOM，不能证明 Agent 能真正操作页面。
- Browser Use 内置的 HAR 记录不能用：它会对每个请求都拉取响应正文，导致 Steel 连接因心跳超时而断开（`keepalive ping timeout`）。改为由采集器自行注册 Browser Use 没有占用的 Network 事件，不拉取响应正文。
- cdp_use 对每个事件只保留一个处理函数。采集器注册事件前会先检查，如果事件已被 Browser Use 占用就直接报错，避免悄悄覆盖它的处理逻辑。
- Agent 运行结束时会重置浏览器会话，所以最终 URL 要从运行历史中读取。

### 当前阻塞：本机到 Steel 的链路太慢

| 测量项 | 结果 |
|---|---|
| CDP 往返延迟 | 约 0.35 秒 |
| DOM 快照（287KB） | 3.3 秒 |
| 无障碍树（229KB） | 2.2 秒 |
| PNG 截图（347KB） | 4.6 秒 |
| Browser Use 获取一次完整页面状态 | 19 秒 |
| 实际每步耗时 | 约 50 秒 |

从数据看，有效带宽大约只有 90KB/s。Browser Use 的 DOM 构建和截图有 15 秒的内部超时，所以仍然会偶发超时。这是基础设施问题，不是代码问题：

- 手动指定 Steel 区域（`ap-northeast`、`ap-southeast`、`us-west`）都返回 503，当前套餐可能不支持选择区域。
- 浏览验证的通过标准仍然要求 DOM 构建没有超时。在这个链路问题解决之前，阶段 0 的浏览验证不算通过。

## 2026-10-02 复测

使用模型 `deepseek-flash`，配置为 `LLM_API=responses`、`LLM_THINKING_TYPE=disabled`。运行 `python -m orchestrator.phase0`，三项全部通过，产物在 `runs/phase0-20261002T173330407512Z/`。

- **模型**：用 Responses 时，全部检查通过，包括 JSON Schema。另外在 Chat Completions 上单独测了一次 JSON Schema（`chat_completions_json_schema`），不通过。
- **浏览**：Browser Use 降级为 Chat Completions。因为 Chat Completions 不支持 JSON Schema，所以把输出 schema 写进系统提示词，不再强制 `response_format`。Agent 在 2 步内点击"项目"导航，进入 `https://wjm.dpdns.org/projects`，平均每步 12.2 秒，总耗时 62 秒。DOM 失败为 0，重复响应为 0，会话已释放，观测时区为 Asia/Shanghai。本次链路带宽足以在 Browser Use 的内部超时内完成 DOM 构建和截图。
- **OASIS**：降级为 Chat Completions。动作集符合预期，潜水者只读，LLM 动作验证通过。

复测前修复了两个问题：

1. 首次复测时 6 步都失败，报错为 `response_format type is unavailable`。原因是浏览代码按 Responses 上测出的 JSON Schema 结果判断，而 Browser Use 实际走的是 Chat Completions。现在改为按 `chat_completions_json_schema` 判断（`core.runtime.chat_json_schema_supported`）。
2. Browser Use 0.13.10 只要模型名包含 "deepseek"，就强制把 `use_vision` 设为 False。方案要求模型能力以实测为准，而能力文件就绪的前提是两项识图探测都通过。因此创建 Agent 后把 `use_vision` 恢复为 True，并在 `browser_result.json` 中记录 `use_vision`。日志里 Browser Use 的那条警告仍会出现，属于正常现象。

开启 `use_vision` 只是改了一个设置，不能证明截图真的发给了模型。因此在 `ProviderChatOpenAI` 发出 SDK 请求时，统计请求总数和其中带 `image_url` 的请求数，结果记为 `browser_result.json` 中的 `model_requests` 和 `model_requests_with_screenshots`。浏览验证通过的条件新增一条：带截图的请求数不少于 Agent 步数。Browser Use 自带的 `save_conversation_path` 只保存文字、会丢掉图片，不能用来做这项证明。

复测（`runs/phase0-20261002T173330407512Z-vision/`，沿用同一份能力文件）：通过。共 2 步、2 次模型请求，2 次都带截图；到达 `/projects`，耗时 58 秒。


## 2026-10-02：提供商适配器与共享并发复测

本次补齐阶段 0 的模型接入层：保留通用 OpenAI 兼容适配器，增加 DeepSeek 适配器，统一环境配置，并在公共请求层、Browser Use 与 CAMEL 模型入口使用跨进程模型额度。Steel 会话另受 min(模型上限, 浏览器上限) 限制。模块级 Responses → Chat 降级保存原因及原提供商、模型、思考与并发设置；厂商参数集中转换。

真实运行目录：`runs/phase0-provider-adapters-20261002/`。使用已有环境：DeepSeek / deepseek-flash / Responses / thinking disabled / 模型并发 10 / 浏览器并发 1。

- 能力探测通过；Responses 的 JSON Schema 与 JSON Object 均通过。Chat 的 JSON Schema 明确记为 unsupported，Chat JSON Object 通过，不能将其视为严格结构化输出。
- Browser Use 单独降级为 Chat，使用 JSON Object、schema 提示词、本地 Pydantic 校验与最多 3 次修正尝试。实际 2 步、2 次模型请求，均带截图；DOM 失败和重复响应均为 0，56.3 秒，会话已释放。
- OASIS/CAMEL 单独降级为 Chat，讨论动作和潜水者只读约束通过，正常关闭。
- 回归验证：浏览环境 73 项通过（包含阶段 1 的既有兼容性检查）；OASIS 环境验证两种适配器的 enabled、disabled 和默认思考参数。共享限流测试覆盖混合模型入口、浏览额度独立、跨进程争用、取消和进程退出释放。

新增配置见 `config/.env.example`。修改提供商后需重新探测，旧能力文件缺少 provider 时不作为 DeepSeek 能力依据。阶段 1 的人设调度与 JSON Object 能力选择随后按阶段提交补齐。

## 2026-10-03：MiMo 适配与阶段 0 复测

新增 `MiMoAdapter` 并注册 `LLM_PROVIDER=mimo`，复用公共请求层、Browser Use 和 CAMEL 桥接。Chat 发送 `thinking.type`，Responses 发送 `reasoning.effort=high/none`，留空采用服务端默认。两个协议均使用 JSON Object、schema 提示词与本地校验；不把格式正确记为严格 JSON Schema 支持。已有 `config/.env` 未修改。

真实运行目录：`runs/phase0-mimo-adapter-20261003/`。使用配置：MiMo / mimo-v2.6-pro / Token Plan CN 端点 / Responses / thinking disabled / 模型上限 30 / 浏览器上限 5。阶段 0 总结果通过：

- 模型：基础对话、单工具、指定工具样本、并行工具、两张随机识图、Responses 和 Chat JSON Object、10 请求并发样本均通过；建议并发仍为实测的 10，不代表已测出上限 30。JSON Schema 标为 unsupported。
- 上下文：2K 和 32K 字符回显样本通过，8K 样本一次未返回预期答案；这不是接口报错，也不能据此宣称完整上下文可靠性或模型最大长度。原能力文件保留该失败。
- Browser Use：降级为 Chat，2 步点击进入 `/projects` 并完成；2 次模型请求均带截图，时区及旁路采集通过，DOM 失败和重复响应均为 0；耗时 86.515 秒，Steel 会话已释放。
- OASIS/CAMEL：降级为 Chat，外部逐步驱动、动作集合和潜水者只读约束通过，正常关闭。
- 回归：浏览环境阶段 0–3 的 147 项通过、1 项因无 CAMEL 跳过；OASIS 环境三个适配器的思考参数测试 9 项通过。覆盖 MiMo 两协议的 enabled / disabled / 默认参数、JSON Schema 到 JSON Object 转换、Browser Use 校验修正、主 Agent JSON 校验、配置识别、协议降级和旧能力文件拒绝。首次广泛回归出现两处既有时序断言失败，单独与完整复测均通过，未修改相关代码。

MiMo 官方文档说明非 auto 的 `tool_choice` 会被忽略，因此指定工具探测通过只说明样本中的工具调用成功，不证明强制指定生效。费用沿用通用适配器的未知价格结果，不套用 DeepSeek 单价。接口依据与配置说明见 `providers.md`。

## 2026-10-03 更正：迟到的 CDP 响应

此前记录中的“重复响应为 0”不成立：cdp_use 在 `cdp_use.client` 日志器上告警，而 Browser Use 让该日志器不向上传递，计数器挂在 `cdp_use` 上始终收不到，计数恒为 0。cdp_use 的“duplicate response”实际含义是调用方已超时或取消等待后，浏览器才返回响应，并非多个 CDP 客户端干扰。阶段 3 MiMo 运行中 8 名完成者有 7 人出现，共 54 条。

现计数器显式挂到 `cdp_use.client`，指标改名 `late_cdp_responses`；取证复用的 CDP 连接记录每个被放弃请求的方法名与等待秒数（`raw_trace.jsonl` 的 `cdp_request_cancelled`，汇总到 `result.json` 的 `cancelled_cdp_requests`）。它只记录、不单独判失败；真实影响仍由 DOM 构建失败、每步截图送达模型和取证截图错误三项检查拦截。已有运行的结果文件不重算。
