-- Versioned direct-document retrieval, separate from verified graph relations.
CREATE TABLE document_batches (
    batch_id TEXT PRIMARY KEY,
    manifest_sha TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('staging','active','retired','failed')),
    index_identity TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE document_chunks (
    batch_id TEXT NOT NULL REFERENCES document_batches(batch_id),
    chunk_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (batch_id, chunk_id)
);
CREATE VIRTUAL TABLE document_fts USING fts5(batch_id UNINDEXED, chunk_id UNINDEXED, tokens);
CREATE TABLE document_active (
    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
    batch_id TEXT NOT NULL REFERENCES document_batches(batch_id)
);
