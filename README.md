# 轻量级多跳推理 GraphRAG 校园知识问答系统

Vue 网页 → FastAPI → Neo4j 多跳路径 / FAISS 原文检索 → 远程模型 API → 断言与引用校验 → 可追溯回答。答案生成、向量嵌入和可选关系抽取均使用 OpenAI 兼容 API，不下载本地大模型或 PyTorch。

本阶段按用户要求优先跑通 API 流程，调整了原设计中的 Ollama 本地部署要求。历史检索模块交接见 [RAG_HANDOFF.md](docs/RAG_HANDOFF.md)，当前完整系统以本文件和 [实现说明](docs/SYSTEM_IMPLEMENTATION.md) 为准。

2026-11-10 本机已完成 DeepSeek 生成与 Qwen 嵌入联调、848条向量重建及13题真实API评测，当前服务入口为 http://localhost:8081 。10道正例全部由API生成，路径、答案要点和引用覆盖均通过开发集自动检查。逐题结果见 [真实API评测报告](docs/logs/API_EVALUATION_20261110.md)，范围与部署限制见 [验证记录](docs/VALIDATION_20261110.md)。

## 数据与能力

- 5 份 PDF、507 页、897 块原文；848 块具备可迁移的 1024 维向量。25 块待复核 OCR、24 块目录不参与检索。
- 已核验图谱为 **2024级计算机科学与技术普通本科**子集：17 个实体、15 条关系，可返回真实 2/3 跳路径。核验来源如实记录为 AI 对照原文审核。
- 其他年级、专业、考试与学位制度走原文检索，回答显示“原文检索”，不会生成虚构路径或推断制度适用性。
- 页面支持专业/年级/培养类型、逐跳记录、引用抽屉、原始 PDF 页码、反馈和评测中心。
- 冻结开发题集含 10 道多跳题（2跳、3跳各5道），另含3道边界负例。报告含逐题路径、答案、来源、失败归因、核心指标和耗时。

## 首次配置

普通 Git 克隆不含原始 PDF。当前工作目录已从 `rag-ready-20261110.zip` 导入5份原件；迁移到其他电脑时还需拷贝 `data/raw/`。初始化会校验文件哈希。

在项目根目录复制 `.env.example` 为 `.env`，填写以下字段。当前本机 `.env` 已创建，请直接编辑，不要覆盖：

| 字段 | 含义 |
|---|---|
| `LLM_BASE_URL` | 兼容 API 根路径，例如供应商提供的含 `/v1` 地址 |
| `LLM_MODEL` | 答案生成模型名称 |
| `LLM_API_KEY` | 生成 API 密钥 |
| `LLM_JSON_MODE` | 默认 true；供应商不支持 JSON response_format 时设 false |
| `LLM_THINKING` | 支持该参数的供应商可填 enabled/disabled；其他供应商留空。DeepSeek先用disabled |
| `EMBEDDING_BASE_URL / MODEL / API_KEY / DIMENSIONS` | 嵌入 API 地址、模型、密钥、维度 |
| `NEO4J_PASSWORD` | 至少8位的本机 Neo4j 密码 |

压缩包原有848条向量的模型、端点与维度记录在 `data/corpus/all-documents-v3/embeddings.json`。嵌入地址须填写自己工作空间的兼容Base URL；只有与向量元数据完全相同的模型、端点、维度才能直接复用原包。更换任一项须显式重建，不能仅换配置继续查旧索引。本机已用新工作空间的 `qwen3.7-text-embedding-flash` 重建1024维索引，之后正常启动会复用该本机索引。供应商的模型名与配额以账户实际可用配置为准。

密钥留在本机 `.env`，不会发给前端或写入评测报告。`EMBEDDING_TOKEN_LIMIT` 是本项目请求预估额度，不代表供应商账户实际剩余额度。当前演示绑定本机回环地址；`DEMO_MODE=true` 允许在网页启动评测。需要管理员限制时设 false、填写 `ADMIN_TOKEN`。

DeepSeek官方生成API的当前配置示例（2026-11-10，[官方文档](https://api-docs.deepseek.com/)）：

```dotenv
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=在本机填写你的DeepSeek密钥
LLM_JSON_MODE=true
LLM_THINKING=disabled
```

DeepSeek密钥只用于上述生成接口，不能用作当前Qwen端点的`EMBEDDING_API_KEY`。后者需填写对应嵌入服务的密钥；更换嵌入服务须显式重建向量。

## Windows 启动

推荐 Docker Desktop，运行：

```powershell
.\start.ps1 -CheckOnly
.\start.ps1
```

脚本构建 web/api 镜像，启动独立 Neo4j，校验原文和审核链，构建实体索引并复用全文向量，随后启动问答服务。访问 **http://localhost:8081**。首次构建需要能访问 Docker 镜像仓库和依赖源，整个应用无需 GPU。建议为 Docker 预留4 GB以上内存和足够的镜像空间，实际资源占用需在验收机器测量。

查看状态与日志：

```powershell
docker compose ps -a
docker compose logs --tail 60 initialize api
docker compose down
```

本项目 Compose 名为 `campus-graphrag2`，与旧目录端口8080的系统分开。配置改变后重新运行启动脚本；数据库密码持久化在卷中，已初始化后改密码需要按 Neo4j 密码变更流程处理。

如果 Docker 镜像仓库暂时不可达，可使用 **Python3.11 + Node22 + Docker中的Neo4j**：

```powershell
.\start-local.ps1
```

本机入口同样使用8081，API为8001，Neo4j Bolt为7688，日志在 `.cache/`。`.\start-local.ps1 -SkipInitialize` 仅供查看未初始化页面。正常使用应先填好配置并完成初始化。

本机服务运行中修改 `.env` 后，执行 `.\stop-local.ps1` 再运行 `.\start-local.ps1`，以重新加载配置和初始化。`stop-local.ps1` 校验进程编号、启动时间与命令后停止本项目后台服务，保留Neo4j数据。

更换嵌入模型后，明确确认需要重新调用嵌入 API 时运行：

```powershell
.\start.ps1 -RebuildEmbeddings
# 或
.\start-local.ps1 -RebuildEmbeddings
```

## 验证完整流程

首页选择计算机科学与技术、2024级、普通本科，尝试：

1. `2024级培养方案中，通识教育课程必修和最低选修学分分别是多少？`（2跳）
2. `计算机科学与技术专业2024级学生的专业课程最多可选修本院其他专业模块课程或本专业研究生课程多少学分？`（3跳）
3. `申请期末考试缓考需要什么手续？`（原文检索）

点击引用读回原文，并打开原 PDF 核对页码。API不可用或输出未通过引用/数值校验时，页面明确显示降级和摘录；这不等于 API 联调成功。

到“评测中心”运行冻结题集，将通过同一问答 pipeline 调用真实 API，保存13题结果。报告的路径命中率只统计10道正例；答案要点命中率含负例终态；引用覆盖率会独立读回本批次证据；另有2/3跳分项、API生成占比、平均/P95时延。要点自动初判和开发题集不能替代人工盲测。

命令行正式评测（结果同步到网页列表）：

```powershell
docker compose exec api python -m scripts.run_eval
```

## 开发检查

```powershell
.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock
cd backend
..\.venv\Scripts\python.exe -m pytest -m "not integration"
..\.venv\Scripts\ruff.exe check .
..\.venv\Scripts\ruff.exe format --check .
cd ../frontend
npm.cmd ci
npm.cmd run build
npm.cmd run lint
npm.cmd run format:check
```

集成测试使用真实 Neo4j 和独立临时 SQLite；模型 API 被桩替换，不产生 API 费用。Linux/CI可运行 `make test-int`。当前验收证据与环境限制记录在 [验证记录](docs/VALIDATION_20261110.md)。

## 数据扩展

`backend/scripts/prepare_all_documents.py` 和 `prepare_rag.py` 保留离线解析、分块及规则候选抽取。可选 `extract_candidates.py` 通过远程 API 在已知实体之间抽取候选：

```powershell
docker compose exec api python -m scripts.extract_candidates /app/data/kb/cs2024-reviewed --output /app/data/candidates/new-review.jsonl
```

候选必须满足关系白名单、实体端点和逐字原文证据检查，始终标记 `unverified`。对照原文审核并更新审核链后，使用 `scripts.build_batch ... --publish` 构建新批次。未核验候选不会直接成为线上结论。原始PDF及OCR需按数据使用权限单独管理。
