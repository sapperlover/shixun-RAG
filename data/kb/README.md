# 正式知识包（D1/D2 填充）

格式与 `data/demo/`（【模拟】演示包）完全相同，契约见 `backend/app/ingest/bundle.py`：

| 文件 | 内容 | 谁产出 |
|---|---|---|
| `documents.csv` | 授权文档清单：来源、授权依据、哈希、适用专业/年级、版本 | Data + 架构师（D1） |
| `chunks.jsonl` | 原文块；`chunk_id` 必须由 `app.graph.ids.chunk_id()` 生成 | ingest：parse + chunk（D2） |
| `entities.jsonl` | 实体与别名；属性须满足 `config/schema_whitelist.yaml` | ingest：extract + normalize（D2） |
| `relations.csv` | 候选关系 → 核验人逐边填写 `verification_status / verified_by / verified_at` | ingest 产出 + 人工核验（D2） |

只有 `verified` 的关系参与回答；`unverified` 进图谱但被剪掉并记入跳级日志；`rejected` 不进图谱。

构建并发布：`make kb DIR=data/kb Q=data/eval/questions_v1.jsonl`（校验不通过不会发布）。
