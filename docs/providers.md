# 提供商适配器与并发

统一入口为 `config/.env`，两个 Python 环境都读取此文件。支持 `deepseek`、`mimo`、`bailian`（阿里云百炼）和 `openai_compatible` 通用适配器；当前配置使用 `LLM_PROVIDER=mimo`。模型、地址和密钥分别为 `LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`。

`LLM_API` 选择 `responses` 或 `chat_completions`。能力探测和人设生成直接使用所选格式；Browser Use 0.13.10 与 OASIS/CAMEL 仅支持 Chat，只降级这些模块。模块结果保存有效协议、原协议、降级原因、提供商、模型、地址、思考设置和两个并发上限，不保存密钥。不会因请求失败而切换模型或提供商。

`LLM_THINKING_TYPE` 为 `enabled`、`disabled` 或空。厂商参数只由 `core/providers.py` 转换：

| 适配器 | Chat | Responses |
|---|---|---|
| DeepSeek | `thinking.type=enabled/disabled` | `reasoning.effort=high/none` |
| MiMo | `thinking.type=enabled/disabled` | `reasoning.effort=high/none` |
| 百炼 | `enable_thinking=true/false` | `enable_thinking=true/false` |
| OpenAI 兼容 | `reasoning_effort=high/none` | `reasoning.effort=high/none` |

留空不发送思考参数。通用适配器需要接口支持相应 OpenAI 参数；特殊厂商行为应放在专用适配器中。

DeepSeek Chat **不支持严格 JSON Schema 输出**。使用 JSON Object，仅保证 JSON 格式，不保证字段、类型或业务约束。提示词包含 schema，每次结果必须经本地 Pydantic 和业务校验，错误时最多尝试 3 次并返回校验原因。Browser Use 同样使用 JSON Object、schema 提示词、本地校验和修正重试；OASIS 当前调用工具，不请求 JSON Schema 输出。能力文件分别记录首选协议与降级 Chat 的 JSON Schema、JSON Object 能力，不能把 JSON Object 成功记为 JSON Schema 成功。Responses 的 JSON Schema 仍需能力探测和本地校验。

MiMo 通过 OpenAI SDK 的 Bearer 认证接入，支持 Chat Completions 和 Responses。当前配置为 `mimo-v2.6-pro`、`https://token-plan-cn.xiaomimimo.com/v1`、Responses、thinking disabled；按量 API 地址为 `https://api.xiaomimimo.com/v1`，套餐端点与密钥由用户配置。MiMo 的文档未提供严格 JSON Schema 保证，两个协议均使用 JSON Object，并复用 schema 提示词、本地校验和最多 3 次尝试；能力文件将 JSON Schema 标为 unsupported，单独实测 JSON Object。Browser Use 和 OASIS 的协议降级保留 MiMo 模型及端点。MiMo 文档说明 `tool_choice` 的非 auto 值会被忽略，所以探测中指定工具成功只能证明该样本调用成功，不能证明服务端强制工具选择。Token 用量沿用 OpenAI 格式。由于 MiMo 不强制非 auto 的 `tool_choice`，OASIS 规划器对 MiMo 不再发送 `tool_choice=required`，无效回复走最多 3 次修正，仍失败时选择不行动；`social_audit.json` 统计修正尝试与退回不行动次数，避免发言被静默压低。MiMo 上下文窗口按用户确认的 256K–1M tokens 记录到能力文件的 `stated_context_window`；探测里的 2K/8K/32K 字符回显只是抽样，单次回显失败不作为上下文上限依据。

阿里云百炼（`LLM_PROVIDER=bailian`）走 OpenAI 兼容模式，Bearer 认证。北京地域 `https://dashscope.aliyuncs.com/compatible-mode/v1`，新加坡 `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`；控制台也提供业务空间专属域名 `https://{WorkspaceId}.<地域>.maas.aliyuncs.com/compatible-mode/v1`，旧域名仍可用。API Key 按地域签发，不能跨地域使用。推荐 `qwen3.7-plus`（支持图片输入、工具调用和 JSON Schema），`LLM_API=chat_completions`，`LLM_THINKING_TYPE=disabled`：

- 思考开关在两种接口上都以 `enable_thinking` 发送（Responses 中 `reasoning.effort` 优先级更高，本项目不发送它）。qwen3.7-plus 默认开启思考，而思考模式下结构化输出“可能失效”，所以应显式关闭；留空则不发送，采用模型默认。
- Chat 的 `json_schema` 只对文档列出的模型生效（Qwen3.7-Plus/Flash/Max、Qwen3.8-Flash/Max 系列），其他模型、以及含图片输入的请求会被服务端静默降级为 `json_object`，不报错。因此能力探测通过不代表浏览请求得到了严格结构保证，所有结果仍经本地校验与最多 3 次修正。严格模式不支持的关键字（如 `multipleOf`、`uniqueItems`、`patternProperties`）会返回 400。
- Responses 接口的文档未写明结构化输出，适配器在 Responses 上改用 JSON Object（是否可用由探测决定，不可用时退回提示词 JSON）。
- Qwen 能强制调用指定函数，但不支持 `tool_choice="required"`；OASIS 规划器因此不发送 `required`，无效回复走修正重试，与 MiMo 相同。能力探测中的“指定工具”仍视为可强制。
- 用量沿用 OpenAI 字段，缓存命中读取 `prompt_tokens_details.cached_tokens` / `input_tokens_details.cached_tokens`。

接口依据：[OpenAI 兼容 Responses](https://help.aliyun.com/zh/model-studio/compatibility-with-openai-responses-api)、[深度思考](https://help.aliyun.com/zh/model-studio/deep-thinking)、[结构化输出](https://help.aliyun.com/zh/model-studio/json-mode)、[Function Calling](https://help.aliyun.com/zh/model-studio/qwen-function-calling)、[qwen3.7-plus](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)。文档核对日期：2026-10-12（America/Los_Angeles）。尚未用真实密钥实测。

`LLM_MAX_CONCURRENCY` 限制所有模型请求，包括探测、人设生成、Browser Use 与 OASIS 的调用和重试。`BROWSER_MAX_CONCURRENCY` 限制实际浏览会话；浏览 Agent 并发为 `min(模型上限, 浏览器上限)`。人设生成与讨论只占模型额度，不占浏览额度。请求排队不消耗公共请求层的供应商响应时限。

两套进程通过项目内 `.runtime/concurrency/` 的操作系统文件锁共享额度；请求结束、异常、取消或进程退出均释放锁。浏览额度从创建 Steel 会话前持有到清理结束。所有运行共用本项目的额度；运行期间更改上限，应先停止已有进程，使两套环境使用一致配置。探测建议并发不会超过配置上限；若上限低于 10，10 个排队探测通过不表示测出了 10 并发能力。

增加提供商时，在 `core/providers.py` 增加适配器并注册到 `ADAPTERS`，实现思考参数、输出格式和 JSON Schema 能力。业务模块只使用公共请求入口或框架桥接模型，不读取厂商参数。更换提供商、地址、模型、思考或协议后需要重新探测；旧能力文件缺少提供商时按通用适配器处理，不能复用于 DeepSeek 或 MiMo。

接口依据：[DeepSeek 思考模式](https://api-docs.deepseek.com/guides/thinking_mode)、[Responses](https://api-docs.deepseek.com/api/create-response)、[JSON Output](https://api-docs.deepseek.com/guides/json_mode)。框架桥接按仓库锁定版本的实际源码验证。

MiMo 接口依据：[Chat Completions](https://mimo.mi.com/docs/en-US/api/chat/openai-api)、[Responses](https://mimo.mi.com/docs/en-US/api/chat/responses)、[JSON Object 与本地校验](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/text-generation/structured-output)。文档核对日期：2026-10-03（America/Los_Angeles）。

项目不显示价格：适配器只转换 token 用量，不提供价目，验收也不依赖费用完整性。JSON Object 限制提示每个进程只打印一次。
