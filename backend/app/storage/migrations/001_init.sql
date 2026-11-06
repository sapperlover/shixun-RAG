-- 元数据库初始结构。★ 冻结契约：只追加新的迁移文件（002_xxx.sql），不修改本文件。
-- 来源：V1.2 附录 B.1（Document/Chunk/RelationEvidence/BuildBatch/ActiveSnapshot）
--     + 文档-2 §4.3(2)（users/qa_logs/feedback/评测结果）。
-- 测试题本身以冻结的 JSONL 文件为准（V1.2 附录 D.1），不入库。

CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('guest', 'student', 'knowledge_admin', 'system_admin')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE documents (
    doc_id             TEXT NOT NULL,
    doc_version        TEXT NOT NULL,
    title              TEXT NOT NULL,
    source_uri         TEXT NOT NULL,
    authorization_note TEXT NOT NULL,                 -- 授权依据：公开链接 / 书面授权 / 脱敏模拟
    file_sha256        TEXT NOT NULL UNIQUE,          -- 按哈希去重
    access_level       TEXT NOT NULL DEFAULT 'public' CHECK (access_level IN ('public', 'restricted')),
    publish_state      TEXT NOT NULL DEFAULT 'draft' CHECK (publish_state IN ('draft', 'published', 'archived')),
    college_code       TEXT,
    major_code         TEXT,
    entry_year         INTEGER,
    operator           TEXT,
    change_note        TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (doc_id, doc_version)
);

CREATE TABLE build_batches (
    batch_id            TEXT PRIMARY KEY,
    state               TEXT NOT NULL CHECK (state IN ('staging', 'validated', 'active', 'failed', 'retired')),
    source_manifest_sha TEXT NOT NULL,
    graph_node_count    INTEGER,
    graph_edge_count    INTEGER,
    faiss_index_sha     TEXT,
    build_stats_json    TEXT,
    error_json          TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    checked_at          TEXT
);

-- 事务化切换指针；查询开始时读取一次并固定（V1.2 §3.3）
CREATE TABLE active_snapshot (
    project_key    TEXT PRIMARY KEY,
    active_version TEXT NOT NULL REFERENCES build_batches (batch_id),
    switched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE chunks (
    batch_id    TEXT NOT NULL REFERENCES build_batches (batch_id),
    chunk_id    TEXT NOT NULL,
    doc_id      TEXT NOT NULL,
    doc_version TEXT NOT NULL,
    page_start  INTEGER,
    page_end    INTEGER,
    section     TEXT,
    text        TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    PRIMARY KEY (batch_id, chunk_id),
    FOREIGN KEY (doc_id, doc_version) REFERENCES documents (doc_id, doc_version)
);

-- 逐边溯源：一条关系可关联多个 Chunk；无 verified 来源的边不得用于 success
CREATE TABLE relation_evidence (
    batch_id            TEXT NOT NULL,
    relation_id         TEXT NOT NULL,
    chunk_id            TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified'
                        CHECK (verification_status IN ('unverified', 'verified', 'rejected')),
    verified_by         TEXT,
    verified_at         TEXT,
    note                TEXT,
    PRIMARY KEY (batch_id, relation_id, chunk_id),
    FOREIGN KEY (batch_id, chunk_id) REFERENCES chunks (batch_id, chunk_id)
);
CREATE INDEX idx_relation_evidence_rel ON relation_evidence (batch_id, relation_id);

CREATE TABLE qa_logs (
    request_id      TEXT PRIMARY KEY,
    session_id      TEXT,
    question        TEXT NOT NULL,
    scope_json      TEXT NOT NULL,
    knowledge_batch TEXT,
    status          TEXT NOT NULL,
    response_json   TEXT NOT NULL,
    hop_logs_json   TEXT,
    latency_ms      INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE feedback (
    id         INTEGER PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES qa_logs (request_id),
    type       TEXT NOT NULL CHECK (type IN ('helpful', 'wrong_answer', 'citation_invalid', 'unresolved')),
    comment    TEXT,
    user_id    INTEGER REFERENCES users (id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_feedback_request ON feedback (request_id);

CREATE TABLE eval_runs (
    run_id         TEXT PRIMARY KEY,
    dataset_sha256 TEXT NOT NULL,
    scorer_version TEXT NOT NULL,
    git_commit     TEXT NOT NULL,
    batch_id       TEXT,
    config_json    TEXT NOT NULL,
    metrics_json   TEXT,
    status         TEXT NOT NULL CHECK (status IN ('running', 'finished', 'failed')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at    TEXT
);

CREATE TABLE eval_results (
    run_id              TEXT NOT NULL REFERENCES eval_runs (run_id),
    question_id         TEXT NOT NULL,
    request_id          TEXT NOT NULL,
    batch_id            TEXT,
    status              TEXT NOT NULL,
    predicted_path_json TEXT NOT NULL,
    path_hit            INTEGER NOT NULL,
    answer_correct      INTEGER NOT NULL,
    citation_covered    INTEGER NOT NULL,
    claims_total        INTEGER NOT NULL,
    failure_stage       TEXT,
    elapsed_ms          INTEGER NOT NULL,
    PRIMARY KEY (run_id, question_id)
);
