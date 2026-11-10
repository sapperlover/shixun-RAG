# 架构决策记录（ADR）

依据：`docs/design/` 下的《系统架构设计 V1.2 整改完善版》（下称 V1.2）。以下保留原完整系统决策，RAG独立交付的实际约定见文末新增记录及 `docs/RAG_HANDOFF.md`。
规则：契约文件（标 ★）冻结后，任何修改须经架构师同意，并在本文件追加一条记录。

| 编号 | 决策 | 理由 |
|---|---|---|
| ADR-001 | **以 V1.2 为唯一设计依据**：4 容器（web/api/neo4j/ollama）、FAISS + bge-small-zh-v1.5、Qwen2.5:1.5b + 模板降级、节点/关系命名（Professional/ProgramPlan/RuleClause/CITES…）、四种终态、P0 用关系 CSV 预核验 + 批次发布 | V1.2 是整改完善版，附录 A–D 给出了可执行的工程契约；早期的其他架构稿已废弃，不再参考 |
| ADR-002 | V1.2 未细化的部分由本项目约定：后端模块分包（ingest/graph/retrieval/answer/eval/api）、四类角色（游客/学生/知识管理员/系统管理员）、`users/qa_logs/feedback/eval_*` 表 | 联调分工、权限检查（V1.2 §4.4）、按 request_id 追溯反馈与评测需要；不与 V1.2 冲突 |
| ADR-003 | 开发环境 = 容器（Dev Containers / `make dev`），不建 conda；conda 可选且不进入验收流程 | 交付标准就是 `docker compose up`；节省磁盘；组员只需装 Docker |
| ADR-004 | 前端基础镜像用 `node:22-alpine`（V1.2 写的是 node:20） | 与开发机 Node 22 一致 |
| ADR-005 | GPU 为可选叠加（`docker-compose.gpu.yml`），基线必须纯 CPU 可运行 | V1.2 附录 D.2 |
| ADR-006 | 后端路由不带 `/api` 前缀，由 nginx 把 `/api/*` 转发并剥离；FastAPI 以 `--root-path /api` 运行 | 与 V1.2 §4.4 列出的端点保持一致；浏览器统一走 `/api`，便于 nginx 区分静态页面与接口 |
| ADR-007 | `paths[].nodes[].node_id` 使用业务实体 ID（entity_id），不含 batch 前缀；批次由顶层 `knowledge_batch` 表达 | 评测金标准可跨批次比对 |
| ADR-008 | 评测题增加可选字段 `key_points`（答案要点），用于答案正确率自动初判，最终仍需人工复核 | V1.2 只有 gold_answer，无法自动判分 |
| ADR-009 | `/qa/ask` 的任何错误（含 422）都返回完整 QAResponse 结构；其他接口错误返回 `{request_id, status:"error", error}` | 前端问答页只需处理一种形状 |
| ADR-010 | `ANCHOR_NOT_FOUND` 的 `failed_hop` 为 null；`PATH_INCOMPLETE`/`EVIDENCE_UNVERIFIED` 的 `failed_hop` 为 1–3 | V1.2 未定义锚点阶段的跳次 |
| ADR-011 | 生成校验不过时：重试 1 次 → 模板生成（degraded）→ 仍不过返回 insufficient；不保留部分通过的模型断言 | 部分删除后答案正文会与断言不一致；V1.2 §4.3 允许模板回退 |
| ADR-012 | 断言数值校验：数值必须出现在所引原文摘录或所引事实的实体名称中（按完整数字比较） | V1.2 §4.3“发现额外未授权数值…回退模板或返回 insufficient”；实体名称来自已核验图谱 |
| ADR-013 | 版本冲突用 `status=insufficient` + `error.code=VERSION_CONFLICT`，可附带 citations 展示冲突来源 | V1.2 §4.2、附录 B.2：同范围可信条款冲突返回 insufficient 并呈现冲突来源 |
| ADR-014 | ~~骨架阶段用 `stub_modules` 标记返回模拟数据的模块~~ **已废止（2026-11-06）**：主干全部真实实现，stub 机制删除；`contracts/mocks` 只用于 dev 联调与契约测试 | 主干已用演示知识包端到端验证 |
| ADR-015 | Embedding 用 sentence-transformers + **CPU 版 torch**（从 `https://download.pytorch.org/whl/cpu` 安装，约 200 MB），禁止装默认的 CUDA 版 torch | 默认 torch 带 CUDA 运行库，超过 3 GB；V1.2 要求 CPU 可运行；bge-small-zh 在 CPU 上足够快 |

| ADR-016 | **知识包（knowledge bundle）是 ingest 与建图之间的唯一接口**：`documents.csv / chunks.jsonl / entities.jsonl / relations.csv`，契约见 `backend/app/ingest/bundle.py`；`relations.csv` 不含 relation_id（依赖 batch，构建时生成） | ingest 可以并行开发、可以换实现；建图只认契约，构建前做全部静态校验 |
| ADR-017 | `citation_id = "cit-" + sha256(batch_id\|relation_id\|chunk_id)[:12]`，构建时写入 `relation_evidence`（迁移 002）；`GET /evidence/{citation_id}?knowledge_batch=` 直接读回 | V1.2 的读回接口只带 citation_id 与批次，编号必须全局可解析，不能是某次回答内的序号 |
| ADR-018 | 答案正文由通过校验的断言拼成（`template.compose`），模型只输出 claims | 防止正文出现未经断言-引用校验的内容 |
| ADR-019 | 问题语义约束：路径至少包含一个问题提及的实体；问题提及某类实体时，路径上同类节点必须是被提及的那个；被更靠前路径完全包含的子路径不再单独给出 | V1.2 §1.2“符合问题语义约束的完整路径”；防止用“专业选修课”路径回答“通识选修课”的问题 |
| ADR-020 | 锚点三种来源：问题字面命中（名称/别名，去掉【…】标注，最长匹配）、scope 推出的培养方案、无字面命中时的 FAISS 向量召回；T3 先修链从锚点双向尝试 | “X 之前要先修什么”需要逆存储方向走链 |
| ADR-021 | PyTorch CPU 包从阿里云镜像（`--find-links https://mirrors.aliyun.com/pytorch-wheels/cpu/`）获取，锁定 `torch==2.9.1+cpu` | 官方 download.pytorch.org 国内直连不可用；锁文件已核对不含 nvidia/CUDA 包 |

## 待决问题（D1 签核时确认）

1. **课程归类关系重复**：白名单同时有 `Course -BELONGS_TO-> CourseCategory` 和 `CourseCategory -CONTAINS-> Course`，表达同一事实。建议只保留一个，避免重复路径和双倍核验工作量。
2. **T3 先修链是否随年级变化**：决定 `path_patterns.yaml` 中 T3 的 `required_scope`。
3. **P0 是否需要登录**：当前 prod 环境所有请求视为游客（安全默认），反馈、文档、评测接口会返回 403。
4. **D1 输入资产**：样例文档清单（来源/授权/哈希/专业/年级/版本）、预核验关系 CSV、≥10 道金标准题。
5. **基线实测**：镜像 digest、模型 SHA、在目标机器上实测内存与时延（`make baseline`）。

## RAG独立交付补充（用户确认，2026-11-10）

- ADR-022：用户负责检索模块，Python `retrieve()` 返回证据与路径，不接管生成模型或新建HTTP服务；原 `/qa/ask` 与 `answer_question` 不变。
- ADR-023：用户指定API向量模型 `qwen3.7-text-embedding-flash`，实测1024维；仅RAG所需依赖锁在 `requirements-rag.lock`。原本地模型约定仍可用于原完整系统，不强制套用到此模块。
- ADR-024：首版仅2024级计算机科学与技术已核验条款。用户明确委托AI对照原文确认，核验来源如实记录为 `ai_source_review`，不冒充人工核验。
- ADR-025：迁移包由代码和核验知识包重建Neo4j、SQLite及FAISS；只在打包副本中将原件地址改为项目相对路径，同步记录变换和哈希，不改变本机运行批次。
