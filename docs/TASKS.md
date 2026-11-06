# 任务分派表（骨架 → 真实实现）

规则：每人只替换自己模块内的实现，**不改函数签名和契约**；`make check` 与 `make test-int` 必须通过。

## 已完成（主干，2026-11-06）

知识包契约与校验、批次构建/校验/发布、逐跳 Cypher 检索与跳级日志、完整路径判定与语义约束、排序、
原文事实构建、Qwen 证据约束生成 + 模板降级、断言-引用校验、FAISS 向量锚点（CPU torch）、原文读回接口、
评测执行与指标。用【模拟】演示包端到端验证：`make kb-demo`、`make test-int`。

## 待分派

| 天 | 模块 / 文件 | 负责角色 | 负责人 | 要做的事 | 验收 |
|---|---|---|---|---|---|
| D1 | `data/kb/documents.csv` | Data + 架构师 | | 授权文档清单 | 每行有来源、授权依据、哈希 |
| D1 | `data/eval/questions_v1.jsonl` | QA + 架构师 | | ≥10 道金标准题并冻结哈希 | `dataset.load` 通过；T1/T2 各 ≥4 |
| D2 | `ingest/parse.py` `chunk.py` | Data | | PDF/DOCX/TXT 解析、条款分块 → `chunks.jsonl` | 块带页码、章节；`bundle.load` 通过 |
| D2 | `ingest/extract_rules.py` `extract_llm.py` `normalize.py` | Data | | 规则/LLM 抽取、别名归一 → `entities.jsonl` + `relations.csv` | `bundle.load` 通过 |
| D2 | `data/kb/relations.csv` 核验 | Data + 核验人 | | 逐边对照原文核验 | `make kb` 校验全部通过 |
| D2 | `api/documents.py` | BE | | 上传校验（白名单、大小、UUID 重命名、哈希去重） | 越权、超大文件、伪造扩展名用例 |
| D3 | 检索调优 | BE | | 用真实数据调 `settings.yaml`、别名词典、提示词；提升 Qwen 一次通过率 | 冻结题集指标 |
| D4 | `frontend/` | FE | | 专业下拉、路径图细化、四态细节、移动端 | 四态全部正确渲染 |
| D4 | `core/security.py` `api/feedback.py` | BE | | 登录、反馈写入、restricted 文档按角色读回 | 反馈可按 request_id 查到 |
| D5 | `api/evaluations.py` `eval/report.py` | QA + BE | | 评测接口、报告、P50/P95、资源占用 | 三项指标可复算；失败题能说明断在哪一跳 |
