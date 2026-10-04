# 阶段 6：接口层、采访与 Web UI

目录结构见 `plan.md` 第 5 节：`backend/` 为 Python 项目根，`frontend/` 为 Vue + Vite。前端只通过 HTTP 访问 `backend/api/`。

## 进度

- [x] 6.1 只读接口层（本文档）
- [ ] 6.2 采访接口
- [ ] 6.3 前端接入接口，替换 mock 数据

## 6.1 只读接口层

接口层读取已完成的阶段 4 运行目录（含对应的阶段 5 报告），**不写入任何运行目录**。读取一律经 `report/evidence.py` 的 `EvidenceStore`，所以证据校验（截图哈希、表达记录的分区与投影、问卷与体验一致性）与报告生成时同样严格：运行目录不完整或被破坏时返回 422 并说明原因，而不是展示残缺数据。

### 启动

```powershell
.venv-browsing/Scripts/python.exe -m api --runs runs --port 8000
```

默认只监听 `127.0.0.1`。运行产物含私有会话与连接信息，不要对外网开放。交互式文档在 `/api/docs`。依赖 `fastapi`、`uvicorn`、`httpx`（测试用 `TestClient`）已写入 `browsing/requirements.txt` 与锁文件。

### 接口

| 路径 | 内容 |
|---|---|
| `GET /api/runs` | 所有阶段 4 运行：状态、产品名、模型、人数、起止时间、已有报告。不构建证据库，中断的运行也能列出 |
| `GET /api/runs/{id}` | 总览：验收结果与限制、产品模型、运行配置、模型配置（不含地址和密钥）、按模型的用量、审计、覆盖说明、报告列表 |
| `GET /api/runs/{id}/personas` | 每个人物：完整设定、计划时间、任务结果、结论数量、问卷摘要与复核标记 |
| `GET /api/runs/{id}/personas/{pid}/experience` | 体验记录：步骤、截图（含访问地址）、情绪曲线、结论、技术事件、回放链接；证据编号与报告一致 |
| `GET /api/runs/{id}/community` | 公开帖子与评论（含评论归属）、看帖记录、表达过滤中被隐瞒的内容、私下问卷。不含点赞数 |
| `GET /api/runs/{id}/report?report_id=` | 阶段 5 报告；不指定时取最新一份 |
| `GET /api/runs/{id}/evidence/{ref}` | 单条证据的定位信息与文件地址，用于从报告结论跳转 |
| `GET /api/runs/{id}/files/{path}` | 只提供 `pNN/screenshots/*.png` |

### 安全约束

- `run_id` 只接受 `[A-Za-z0-9._-]`，且目录必须含 `phase4_result.json` 与 `run.db`。
- 文件接口用白名单正则限定为截图，并再核对解析后的真实路径仍在运行目录内。`session.json`、`raw_trace.jsonl`、数据库等不会外送。
- 响应不含 `base_url`、密钥；体验记录里的 `session` 不原样返回，只提取回放链接和时间偏移依据。

### 历史运行目录里的绝对路径

`run_context.json`、`phase5_result.json` 等记录的 `source_run` 是写入时的**绝对路径**。根目录整理（`runs/` 移入 `backend/runs/`）后，历史目录里的这些路径已不存在。这些文件受哈希约束，不改写；接口层按路径的**目录名**到 `runs/` 下解析（`api/runs.py: sibling`），因此历史运行仍可读取。新运行写入的是正确路径。

仍受影响的只有直接读取该路径的旧逻辑：阶段 5 对历史目录生成报告时，`product_model.json` 读不到，产品名会退回“产品”。

## 回归

```powershell
.venv-browsing/Scripts/python.exe -m pytest tests/test_api.py -q
```

覆盖：运行列表与产品名解析（含失效的绝对路径）；总览不含凭据；人物摘要；截图可取而会话文件不可取；路径穿越与编码绕过（`../`、`%2F`、反斜杠、非白名单文件）；公开与私密记录分开且不含点赞；报告与证据解析；未知运行、非阶段 4 目录、无报告；损坏数据返回 422。在真实样本 `phase4-20261003T071619710132Z` 上手工核对：10 人、4 份报告，首次加载约 0.9 秒；中断的样本 `phase4-20261003T070353556759Z`（缺 `social_audit.json`）在列表中可见，详情返回 422。

## 已知限制

- 只读：不能从接口新建运行、审批人设或查看实时进度。
- 证据库按运行缓存，缓存键是 `run.db` 与 `run_context.json` 的修改时间。已完成的运行不会变化，正在写入的运行不应通过此接口读取。
- 用量只给每个模型的请求数与输入、缓存命中、输出 token（由各目录的 `model_usage.jsonl` 汇总，不含人设生成），**不提供任何价格**；`cost.json` 里的金额字段不会出现在响应中。前端 mock 里的人民币费用需在 6.3 去掉。
