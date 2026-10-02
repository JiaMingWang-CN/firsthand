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

当前状态：模型探测和 OASIS 验证已通过；浏览验证受本机到 Steel 的链路带宽限制，暂缓到网络环境改善后重测（见文末“修订”一节）。

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
