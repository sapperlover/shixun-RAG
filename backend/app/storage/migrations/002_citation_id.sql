-- 每条“关系-原文块”证据一个全局可读回的 citation_id（ADR-017）：
-- citation_id = "cit-" + sha256(batch_id|relation_id|chunk_id)[:12]，构建批次时写入。
-- GET /evidence/{citation_id}?knowledge_batch=... 按它读回原文，不依赖某次回答的上下文。
ALTER TABLE relation_evidence ADD COLUMN citation_id TEXT;
CREATE UNIQUE INDEX idx_relation_evidence_citation ON relation_evidence (batch_id, citation_id);
