# 任务分派表（骨架 → 真实实现）

规则：每人只替换自己模块内的实现，**不改函数签名和契约**；实现合入后，把模块名从
`config/settings.yaml → pipeline.stub_modules` 中删除，`make check` 必须通过。

| 天 | 模块 / 文件 | 负责角色 | 负责人 | 要做的事 | 验收 |
|---|---|---|---|---|---|
| D1 | `data/raw/manifest.csv` | Data + 架构师 | | 授权样例文档清单 | 每行有来源、授权依据、哈希 |
| D1 | `data/eval/questions_v1.jsonl` | QA + 架构师 | | ≥10 道金标准题并冻结哈希 | `dataset.load` 通过；T1/T2 各 ≥4 |
| D2 | `ingest/parse.py` `chunk.py` | Data | | PDF/DOCX/TXT 解析、条款分块 | 新增单测；块带页码、章节、哈希 |
| D2 | `ingest/extract_rules.py` `normalize.py` | Data | | 规则抽取、别名归一 → 待核验 CSV | CSV 表头与 `verify_csv.COLUMNS` 一致 |
| D2 | `data/relations/relations_verified.csv` | Data + 核验人 | | 逐边对照原文核验 | 每条 verified 边有 verified_by/at |
| D2 | `graph/build.py` `validate.py` | Data | | staging 构建、批次校验 | 批次可发布；失败批次不可发布 |
| D2 | `api/documents.py` | BE | | 上传校验、写 documents 表 | 越权、超大文件、伪造扩展名用例 |
| D3 | `retrieval/intent.py` | BE | | 题型识别、实体提及 | 缺范围返回 needs_context |
| D3 | `retrieval/anchors.py` `expand.py` | BE | | 锚点、逐跳 Cypher、跳级日志（移除 stub：snapshot/anchors/expand） | T1–T3 冻结题能找到路径 |
| D3 | `retrieval/path_check.py` `rank.py` | BE | | 完整路径判定、排序（移除 stub：path_check/rank） | 断链返回正确 failed_hop |
| D3 | `answer/facts.py` `generate.py` `llm/` | BE | | 事实读取、Ollama 生成（移除 stub：facts/generate） | 模型关闭时模板降级可见 |
| D3 | `storage/faiss_store.py` `llm/embedder.py` | BE | | 向量索引（按批次） | FAISS 关闭时 graph_only 可见 |
| D4 | `frontend/` | FE | | 专业下拉、路径图细化、四态细节、移动端 | 四态 mock 全部正确渲染 |
| D4 | `core/security.py` `api/feedback.py` `api/evidence.py` | BE | | 登录、反馈写入、原文读回 | 反馈可按 request_id 查到 |
| D5 | `eval/` `api/evaluations.py` | QA + BE | | 评测接口、报告、P50/P95 | 三项指标可复算；失败题能说明断在哪一跳 |
