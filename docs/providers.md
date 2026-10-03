# 提供商适配器与并发

统一入口为 `config/.env`，两个 Python 环境都读取此文件。当前使用 `LLM_PROVIDER=deepseek`，保留 `openai_compatible` 通用适配器。模型、地址和密钥分别为 `LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`。

`LLM_API` 选择 `responses` 或 `chat_completions`。能力探测和人设生成直接使用所选格式；Browser Use 0.13.10 与 OASIS/CAMEL 仅支持 Chat，只降级这些模块。模块结果保存有效协议、原协议、降级原因、提供商、模型、地址、思考设置和两个并发上限，不保存密钥。不会因请求失败而切换模型或提供商。

`LLM_THINKING_TYPE` 为 `enabled`、`disabled` 或空。厂商参数只由 `core/providers.py` 转换：

| 适配器 | Chat | Responses |
|---|---|---|
| DeepSeek | `thinking.type=enabled/disabled` | `reasoning.effort=high/none` |
| OpenAI 兼容 | `reasoning_effort=high/none` | `reasoning.effort=high/none` |

留空不发送思考参数。通用适配器需要接口支持相应 OpenAI 参数；特殊厂商行为应放在专用适配器中。

DeepSeek Chat **不支持严格 JSON Schema 输出**。使用 JSON Object，仅保证 JSON 格式，不保证字段、类型或业务约束。提示词包含 schema，每次结果必须经本地 Pydantic 和业务校验，错误时最多尝试 3 次并返回校验原因。Browser Use 同样使用 JSON Object、schema 提示词、本地校验和修正重试；OASIS 当前调用工具，不请求 JSON Schema 输出。能力文件分别记录首选协议与降级 Chat 的 JSON Schema、JSON Object 能力，不能把 JSON Object 成功记为 JSON Schema 成功。Responses 的 JSON Schema 仍需能力探测和本地校验。

`LLM_MAX_CONCURRENCY` 限制所有模型请求，包括探测、人设生成、Browser Use 与 OASIS 的调用和重试。`BROWSER_MAX_CONCURRENCY` 限制实际浏览会话；浏览 Agent 并发为 `min(模型上限, 浏览器上限)`。人设生成与讨论只占模型额度，不占浏览额度。请求排队不消耗公共请求层的供应商响应时限。

两套进程通过项目内 `.runtime/concurrency/` 的操作系统文件锁共享额度；请求结束、异常、取消或进程退出均释放锁。浏览额度从创建 Steel 会话前持有到清理结束。所有运行共用本项目的额度；运行期间更改上限，应先停止已有进程，使两套环境使用一致配置。探测建议并发不会超过配置上限；若上限低于 10，10 个排队探测通过不表示测出了 10 并发能力。

增加提供商时，在 `core/providers.py` 增加适配器并注册到 `ADAPTERS`，实现思考参数、输出格式和 JSON Schema 能力。业务模块只使用公共请求入口或框架桥接模型，不读取厂商参数。更换提供商、地址、模型、思考或协议后需要重新探测；旧能力文件缺少提供商时按通用适配器处理，不能复用于 DeepSeek。

接口依据：[DeepSeek 思考模式](https://api-docs.deepseek.com/guides/thinking_mode)、[Responses](https://api-docs.deepseek.com/api/create-response)、[JSON Output](https://api-docs.deepseek.com/guides/json_mode)。框架桥接按仓库锁定版本的实际源码验证。
