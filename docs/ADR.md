# 架构决策记录（ADR）

依据：`docs/architecture/` 下的《系统架构设计 V1.2 整改完善版》（下称 V1.2）与《架构设计文档-2》（V1.0，下称文档-2）。
规则：契约文件（标 ★）冻结后，任何修改须经架构师同意，并在本文件追加一条记录。

| 编号 | 决策 | 理由 |
|---|---|---|
| ADR-001 | 两份文档冲突处，**一律以 V1.2 为准**：4 容器（web/api/neo4j/ollama）、FAISS + bge-small-zh-v1.5、Qwen2.5:1.5b + 模板降级、节点/关系命名（Professional/ProgramPlan/RuleClause/CITES…）、四种终态、P0 用关系 CSV 预核验 + 批次发布 | V1.2 是后出的整改版，附录 A–D 给出了可执行的工程契约 |
| ADR-002 | 沿用文档-2 的模块分包（ingest/retrieval/answer/eval/api）、角色模型、`users/qa_logs/feedback` 表 | 与 V1.2 不冲突，补足 V1.2 未细化的部分 |
| ADR-003 | 开发环境 = 容器（Dev Containers / `make dev`），不建 conda；conda 可选且不进入验收流程 | 交付标准就是 `docker compose up`；节省磁盘；组员只需装 Docker |
| ADR-004 | 前端基础镜像用 `node:22-alpine`（V1.2 写的是 node:20） | 与开发机 Node 22 一致 |
| ADR-005 | GPU 为可选叠加（`docker-compose.gpu.yml`），基线必须纯 CPU 可运行 | V1.2 附录 D.2 |
| ADR-006 | 后端路由不带 `/api` 前缀，由 nginx 把 `/api/*` 转发并剥离；FastAPI 以 `--root-path /api` 运行 | V1.2 列出的端点无前缀，文档-2 有前缀，两者都满足 |
| ADR-007 | `paths[].nodes[].node_id` 使用业务实体 ID（entity_id），不含 batch 前缀；批次由顶层 `knowledge_batch` 表达 | 评测金标准可跨批次比对 |
| ADR-008 | 评测题增加可选字段 `key_points`（答案要点），用于答案正确率自动初判，最终仍需人工复核 | V1.2 只有 gold_answer，无法自动判分 |
| ADR-009 | `/qa/ask` 的任何错误（含 422）都返回完整 QAResponse 结构；其他接口错误返回 `{request_id, status:"error", error}` | 前端问答页只需处理一种形状 |
| ADR-010 | `ANCHOR_NOT_FOUND` 的 `failed_hop` 为 null；`PATH_INCOMPLETE`/`EVIDENCE_UNVERIFIED` 的 `failed_hop` 为 1–3 | V1.2 未定义锚点阶段的跳次 |
| ADR-011 | 生成校验不过时：重试 1 次 → 模板生成（degraded）→ 仍不过返回 insufficient；不保留部分通过的模型断言 | 部分删除后答案正文会与断言不一致；V1.2 §4.3 允许模板回退 |
| ADR-012 | 断言数值校验：数值必须出现在所引原文摘录或所引事实的实体名称中（按完整数字比较） | 文档-2 §4.2(3)；实体名称来自已核验图谱 |
| ADR-013 | 版本冲突用 `status=insufficient` + `error.code=VERSION_CONFLICT`，可附带 citations 展示冲突来源 | V1.2 只有四种终态，文档-2 的 conflict 归入 insufficient |
| ADR-014 | 骨架阶段用 `settings.yaml → pipeline.stub_modules` 标记仍返回模拟数据的模块，`/health/ready` 如实报告 | 链路端到端可跑，同时不会把模拟数据误当成真实结果 |

## 待决问题（D1 签核时确认）

1. **课程归类关系重复**：白名单同时有 `Course -BELONGS_TO-> CourseCategory` 和 `CourseCategory -CONTAINS-> Course`，表达同一事实。建议只保留一个，避免重复路径和双倍核验工作量。
2. **T3 先修链是否随年级变化**：决定 `path_patterns.yaml` 中 T3 的 `required_scope`。
3. **P0 是否需要登录**：当前 prod 环境所有请求视为游客（安全默认），反馈、文档、评测接口会返回 403。
4. **D1 输入资产**：样例文档清单（来源/授权/哈希/专业/年级/版本）、预核验关系 CSV、≥10 道金标准题。
5. **基线实测**：镜像 digest、模型 SHA、在目标机器上实测内存与时延（`make baseline`）。
