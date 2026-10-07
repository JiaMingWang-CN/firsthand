# 阶段 8：纯文本模型

不能识图的模型也可以跑完整个流程，但结果参考性有限，并在各处明确标注。

## 探测

- 能力文件新增 `vision`：`vision_0`、`vision_1` 都通过才是 `true`；首选 Responses 时还要求 `chat_completions_vision_0/1` 通过。
- `ready` 只要求基础对话和单工具调用（Responses 时还有对应的 Chat 两项）；不支持工具调用仍然中止。
- 没有 `vision` 字段的旧能力文件，当时必须通过识图才能就绪，按支持识图处理（`core.runtime.sees_images`）。

## 确认后才继续

- 新建运行时重新探测：发现不支持识图，`orchestrator.phase1 analyze` 写出 `phase1_result.json` 的 `stage: "text_only"` 后停止，不读首页、不再调用模型。
- 审核页显示提示，用户点“接受并继续分析”并在弹窗中确认后，接口 `POST /api/drafts/{id}/analysis`（`{"confirm": true}`）启动 `orchestrator.phase1 resume <运行目录>`，复用该目录的能力文件继续分析。
- 复用已有的纯文本能力文件时，新建运行页标出“不支持图像识别”，开始分析前的确认弹窗写明参考性有限。
- 命令行：`analyze` / `prepare` 停下时打印提示与 `resume` 命令。

## 运行

- Browser Use 以 `use_vision=False` 运行：不发截图，自动去掉 `screenshot` 动作，只按页面的 DOM 与可访问性树操作。
- 旁路采集的截图和 Steel 录像照常保存，供回放核对；“每步截图都发给模型”的验收条件只对识图模型生效。
- 其他模块（讨论、问卷、报告、采访）本来就不发图片，不受影响。

## 标注

| 位置 | 标注 |
|---|---|
| 运行列表 | 进行中的草稿与已完成的运行都显示“参考性有限 · 纯文本模型” |
| 审核页 | 页头标签；分析后一直显示提示 |
| 报告 | 页头标签与提示；`report.json` 的覆盖说明写入同一句话 |
| `review.md` | 写入同一句话 |

接口字段：`/api/capabilities` 的 `vision`，`/api/drafts`、`/api/drafts/{id}`、`/api/runs`、`/api/runs/{id}` 的 `text_only`。

## 验证

- 后端：`tests/test_text_only.py`（分析暂停与继续、确认前不再请求模型、接口状态、列表与报告标注），以及探测测试改为“不支持识图仍就绪、`vision` 为 false”。
- 前端：`test/pipeline.spec.js`（复用纯文本能力文件需确认、暂停后确认才继续、运行列表标注）、`test/ui.spec.js`（报告标注）。
- 未用真实的纯文本模型跑过完整运行。
