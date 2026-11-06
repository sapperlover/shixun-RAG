# 轻量级多跳推理 GraphRAG 校园知识问答系统

“实体锚点 → 2–3 跳关系路径 → 逐边原文来源 → 受约束回答”的单机可复现 MVP。
设计依据见 `docs/architecture/`，取舍见 [docs/ADR.md](docs/ADR.md)，分工见 [docs/TASKS.md](docs/TASKS.md)。

> 主干已全部实现，并用 `data/demo/` 的【模拟】演示知识包端到端验证。真实文档的解析与抽取（D2）尚待实现，
> 正式知识包放在 `data/kb/`（格式见该目录 README）。

## 环境要求

只需 **Docker（含 Compose v2）+ make**。不需要本地 Python / Node / conda。
最低配置（V1.2 附录 D.2，待实测签核）：4 vCPU / 16 GB 内存 / ≥25 GB 可用磁盘；GPU 可选。

## 启动

```bash
make env        # 生成 .env，然后修改 NEO4J_PASSWORD（至少 8 位）
make up         # 交付基线：web / api / neo4j / ollama；GPU 加速用 make up GPU=1
make init       # 首次：SQLite 迁移、Neo4j 约束、拉取 Qwen 与 bge-small-zh 模型
make kb-demo    # 构建并发布【模拟】演示知识批次（正式数据：make kb DIR=data/kb Q=...）
make health     # 查看 /health/ready
```

演示问题（专业代码 `DEMO01`、年级 `2024`）：“计算机科学与技术专业 2024 级的专业选修课，跨院系修读的课程怎么认定？”、
“学操作系统之前需要先修哪些课？”（无需年级）、“2024 级通识选修课的修读有什么规定？”（应拒答：关系未核验）。

打开 http://localhost:8080 。只有 web 暴露端口；Neo4j、Ollama 仅在 Compose 内网可见。

## 开发

```bash
make dev        # api 热重载 :8000（/docs 看接口），Vite :5173，Neo4j Browser :7474
make test       # 后端契约 / 单元 / 接口测试（不依赖外部服务）
make test-int   # 集成测试：真实 Neo4j + Ollama 跑演示知识包（需先 make up）
make eval-demo  # 用演示题集跑评测，输出三项指标与失败分布
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
data/          kb/ 正式知识包（D1/D2）、demo/【模拟】演示包、eval/ 冻结题集
docs/          架构文档、ADR、任务分派、部署基线
```

★ 为冻结契约，修改须经架构师同意并记入 ADR。

## 契约要点

- `POST /qa/ask` 四种终态 `success / needs_context / insufficient / error` 返回相同顶层键；error 为 HTTP 503。
- 每条断言的引用必须覆盖其依赖路径的每一条边；断言中的数值必须出现在所引原文中。
- 每个请求开始时固定 `knowledge_batch`，本次请求只读这一批次的数据。
- 知识包 → staging 批次 → 6 项校验 → 事务化切换 active；校验不过的批次不会上线。
- 降级（`graph_only` / `template`）必须设置 `degraded_mode=true`，前端可见。
