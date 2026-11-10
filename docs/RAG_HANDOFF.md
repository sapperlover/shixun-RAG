# RAG交接与迁移

## 当前状态与边界

5份PDF共507页已离线处理，`data/corpus/all-documents-v3/` 含897块。排除24块目录、25块待复核OCR后，848块可参与检索。扫描制度24页中20页完成AI对照原图核验，4页公式/复杂表格仍待核验；培养方案补充OCR21页也不作为默认可用证据。原始OCR和纠错记录保留在 `data/processed/ocr/`。

培养方案按专业、入学年级、普通/留学生/第二学位/联合培养类型区分；书册年份与印刷方案修订年份分开，2023书册中的2021修订方案不擅自视为2023级。调用 `available_scopes()` 查看可选范围。默认普通本科，其他类型应显式提供。制度原文可直接检索，但不据发布日期断定适用于某届。

多跳图谱保留已核验CS2024子集：17实体、15通过关系及1拒绝记录。其余文档使用直接原文检索，未编造先修、引用或适用边。AI核验有明确标识，不代表人工签字。

## 调用方式

在首次导入前加载配置，路径使用实际位置：

```python
from dotenv import load_dotenv
load_dotenv("项目目录/.env.rag")
from app.rag import retrieve, available_scopes
result = retrieve("软件工程2025级的学制和授予学位是什么？", {}, "request-001")
payload = result.model_dump(mode="json", by_alias=True)
```

也可通过scope传 `major_code`（当前使用专业中文名称，无需学校官方代码）、`entry_year`、`college`、`program_variant`。缺少必要范围或问题与scope冲突返回 `needs_context`；无证据返回 `insufficient`；基础设施故障返回 `error`。异步后端在线程池中调用同步函数。

`retrieval_type=graph` 的success要求完整可信路径和逐边证据；`document` 的success表示找到相关原文证据，paths为空，不证明制度对某届适用。两者均未生成或验证最终答案。`retrieval_mode` 标识 `hybrid / graph_only / keyword_only`，降级必须读取说明。

## 新电脑初始化

需要Python 3.11、Docker Desktop/Engine及Compose，以及有权限的embedding API Key。不需要本地GPU、Ollama或Windows OCR。OCR已在原机器离线处理。

PowerShell从解压目录执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-rag.lock
cd backend
..\.venv\Scripts\python.exe -m scripts.configure_rag
```

根目录 `.env.rag` 填写 `EMBEDDING_API_KEY`，确认地址、模型 `qwen3.7-text-embedding-flash` 和1024维；Neo4j密码自动生成。不要把密钥发给AI或提交。启动Docker引擎后：

```powershell
..\.venv\Scripts\python.exe -m scripts.initialize_rag --start-db --output ../docs/logs/local_initialization.json
..\.venv\Scripts\python.exe -m scripts.verify_all_documents --simple-ten --output ../docs/logs/local_ten_cases.json
```

初始化检查5份原件哈希，建约束、构建和校验图谱及全文索引，然后发布；失败保留相应旧批次。初始化ready表示数据准备完成，单独的10例验证才检查真实查询。数据库只绑定本机7474/7687。Linux/macOS改用 `.venv/bin/python`。

完整的 `embeddings.npz / embeddings.json` 已随知识包提供：源文本哈希、模型、端点、维度和向量校验通过后直接重建索引，无需全文重嵌入。图谱小索引首次仍可能调用API，查询也需要API。切换模型或端点时不得混用旧向量，须明确重新构建。迁移不拷贝Neo4j卷或本机SQLite，避免批次不一致和密码泄露。

## 已完成的验证与消耗

当前全文批次 `documents-5d0bc4db29-df92fe`，848向量、1024维；图谱批次 `batch-20261110-105715-0cb3`。初始化输出见 `logs/full_corpus_flash_ready_20261110.json`。

- `logs/ten_cases_flash_live_20261110.json`：8个来源正例覆盖5PDF，全部真实hybrid模式；2个范围/无来源负例符合预期。另有原10道CS2024多跳开发题回归，路径命中率1.0。
- `logs/full_flash_portability_20261110.json`：在另一SQLite/FAISS目录，从完整可迁移向量重建848条索引，禁止API调用仍成功，且索引哈希一致。这是本机迁移演练，尚非第二台电脑实测。
- 101项离线测试通过，9项外部集成默认跳过。此前真实Neo4j集成和故障注入见 `real_validation_20261110.json`、`recheck_20261110.json`。代码变更涉及的ruff检查通过。
- 25块待复核OCR详见 `data/corpus/all-documents-v3/review_queue.json`；原始识别和AI纠错记录保留，不擅自将复杂公式或图表标记为准确。其余原生文本标记为提取结果，不伪称逐页人工核验。

题目由AI依原文制作和检查，属于非盲开发验证；检验来源、范围与路径，不评测生成答案正确率，也不保证任意问题均可命中。

用户已将Flash额度要求更新为100万token。账本保留此前60万历史预留（含旧模型调用，不是实际Flash账单）；新调用按服务端usage记账，未知请求保留上界，调用前先检查额度。最终统计见 `logs/flash_usage_final_20261110.json`。新电脑样例历史预留为0，自己的调用独立计量。早期暂停及关键词报告仅作历史记录，不代替此次真实hybrid验证。

## 导出与维护

从backend执行 `python -m scripts.export_rag --output ../dist/唯一文件名.zip`。包含5PDF、离线文本、OCR纠错、知识包、代码和文档；不包含密钥、环境或运行数据库。四文件图谱包仅在导出副本中改为相对原件路径并同步哈希。最终包为 `dist/rag-ready-20261110.zip`；`rag-handoff-*` 和 `rag-flash-checkpoint-*` 均为旧阶段快照，不应当作最终交付。

维护流程见 [数据维护](AI_EXPANSION.md)。架构原件在design，旧设计中本地模型和完整前后端部署不取代本交接。
