# 数据维护与AI接手

先读RAG_HANDOFF和最近日志。5份原始PDF已完成离线整理；不要重跑全部OCR或全文嵌入来确认状态。

1. 原件只读，检查 `data/corpus/all-documents-v3/manifest.json` 及来源哈希。新文档或纠错输出新目录，保留旧批次。
2. 两份制度纠错在 `data/processed/ocr/rules_corrections.json`，绑定页码和原OCR哈希。未核验的公式/表格与培养方案图像页不能仅改状态发布。需要实际对照PDF图像记录修改依据；用户委托AI核验时明确标识AI，不伪装人工。
3. 离线命令 `python -m scripts.prepare_all_documents --help`，WindowsOCR `scripts/ocr_windows.ps1`。准备脚本保留页码、专业、书册年和修订年。制度适用范围不明时询问负责人，不以时间推断。培养方案课程开设顺序不构成先修关系。
4. 全文直接检索不需要编造图谱边。新增多跳关系须符合schema、原文明确、scope一致并通过来源复核；未核验/缺证据/跨年级路径不能返回成功。保留旧10题回归。
5. 新模型先少量确认权限和维度，再建新索引；禁止重用不同模型向量。API请求级缓存与文档50块缓存支持恢复。注意 `data/embedding_usage.json` 的总量保护。用户最新要求Flash不超过100万；本机仍保留60万旧调用预留，不为通过构建随意调低。
6. `python -m scripts.initialize_rag` 在校验后发布，并从完整活动批次生成 `embeddings.npz/json` 供迁移。缺此文件时不能承诺新电脑无需全文重嵌入。
7. `python -m scripts.verify_all_documents --simple-ten --output 新文件.json` 验证8个来源正例和2个负例。`--keyword-only` 仅验证明确降级，不作为真实混合检索成功。报告来源质量与路径质量，不声称答案生成正确率。

当前全量848条Flash向量及真实混合检索10例验证已完成，完整向量随包迁移。后续维护重点是review_queue中25块OCR来源复核、新文档范围确认与真实图谱关系扩充；不要为凑多跳而造边。
