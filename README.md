# 轻量级多跳推理 GraphRAG 校园知识问答系统

“实体锚点 → 2–3 跳关系路径 → 逐边原文来源 → 受约束回答”的单机可复现 MVP。
设计依据见 `docs/architecture/`，取舍见 [docs/ADR.md](docs/ADR.md)，分工见 [docs/TASKS.md](docs/TASKS.md)。

> 当前处于**骨架阶段**：链路端到端可跑，但检索与生成模块返回的是 `contracts/mocks/` 中标注为【模拟】的数据。
> 仍在模拟状态的模块列在 `config/settings.yaml → pipeline.stub_modules`，`/health/ready` 也会显示。

## 环境要求

只需 **Docker（含 Compose v2）+ make**。不需要本地 Python / Node / conda。
最低配置（V1.2 附录 D.2，待实测签核）：4 vCPU / 16 GB 内存 / ≥25 GB 可用磁盘；GPU 可选。

## 启动

```bash
make env        # 生成 .env，然后修改 NEO4J_PASSWORD（至少 8 位）
make up         # 交付基线：web / api / neo4j / ollama；GPU 加速用 make up GPU=1
make init       # 首次：SQLite 迁移、Neo4j 约束、拉取 Qwen 模型
make health     # 查看 /health/ready
```

打开 http://localhost:8080 。只有 web 暴露端口；Neo4j、Ollama 仅在 Compose 内网可见。

## 开发

```bash
make dev        # api 热重载 :8000（/docs 看接口），Vite :5173，Neo4j Browser :7474
make test       # 后端契约 / 单元 / 接口测试（不依赖外部服务）
make lint       # ruff + eslint + prettier
make typecheck  # vue-tsc
make check      # 以上全部，提交前执行
make schema     # 改了 backend/app/schemas/qa.py 后重新导出 contracts/qa_ask.schema.json
make lock       # 改了 backend/requirements*.in 后重新生成锁文件
make baseline   # 记录镜像 digest、模型、锁文件哈希、硬件 → docs/BASELINE.md
```

VS Code：安装 Dev Containers 扩展 → “Reopen in Container”，直接在 api 容器里编辑、跑测试、打断点。

前端联调：
- 页面右上角可选“联调角色”（请求头 `X-Demo-Role`，仅 dev 生效）；
- 问答页可选“强制终态”（请求头 `X-Debug-Force-Status`，仅 dev 生效），用于检查四种状态的渲染；
- 不启动后端时可用 `npm run dev:mock`，直接读取 `contracts/mocks/`。

## 目录

```
config/        settings.yaml（参数）、schema_whitelist.yaml（图谱白名单）、path_patterns.yaml（T1–T3）
contracts/     ★ 前后端契约：qa_ask.schema.json + 四态 mock
backend/app/
  pipeline.py  ★ 在线问答与评测共用的唯一入口
  domain.py    ★ 模块之间传递的数据结构
  schemas/     ★ 接口契约（Pydantic，内置 V1.2 强制校验）
  core/        配置、错误码、日志脱敏、角色
  api/         路由：qa / evidence / documents / feedback / evaluations / health
  storage/     SQLite（迁移）、Neo4j（约束）、FAISS、active_version 指针
  ingest/ graph/ retrieval/ answer/ llm/ eval/   各功能模块
frontend/      Vue 3 + Vite + Element Plus + ECharts，四个页面
data/          文档清单、预核验关系 CSV、冻结题集（D1 补齐）
docs/          架构文档、ADR、任务分派、部署基线
```

★ 为冻结契约，修改须经架构师同意并记入 ADR。

## 契约要点

- `POST /qa/ask` 四种终态 `success / needs_context / insufficient / error` 返回相同顶层键；error 为 HTTP 503。
- 每条断言的引用必须覆盖其依赖路径的每一条边；断言中的数值必须出现在所引原文中。
- 每个请求开始时固定 `knowledge_batch`，本次请求只读这一批次的数据。
- 降级（`graph_only` / `template`）必须设置 `degraded_mode=true`，前端可见。
