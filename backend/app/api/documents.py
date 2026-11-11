"""Public document catalogue and hash-checked original source PDFs."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.core.config import REPO_ROOT
from app.core.errors import ApiError, ErrorCode
from app.core.security import Role, require_roles
from app.schemas.common import Page
from app.schemas.qa import Scope
from app.schemas.resources import DocumentOut
from app.storage import document_corpus, sqlite

router = APIRouter(tags=["documents"])


@router.get("/documents", response_model=Page[DocumentOut])
def list_documents(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    batch = document_corpus.active()
    entries = {}
    if batch:
        for row in document_corpus.rows(batch):
            key = (row["doc_id"], row["doc_version"])
            entries.setdefault(
                key,
                DocumentOut(
                    doc_id=row["doc_id"],
                    doc_version=row["doc_version"],
                    title=row["title"],
                    source_uri="data/raw/" + row["source_file"],
                    file_sha256=row["source_sha256"],
                    access_level="public",
                    publish_state="published",
                    scope=Scope(),
                    created_at="",
                    knowledge_batch=batch,
                ),
            )
    else:
        with sqlite.connect() as conn:
            for row in conn.execute("SELECT * FROM documents WHERE access_level='public'"):
                row = dict(row)
                entries[(row["doc_id"], row["doc_version"])] = DocumentOut(
                    **{k: row[k] for k in DocumentOut.model_fields if k in row},
                    scope=Scope(major_code=row["major_code"], entry_year=row["entry_year"]),
                )
    items = sorted(entries.values(), key=lambda d: d.doc_id)
    return Page[DocumentOut](
        items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset
    )


@router.get("/documents/summary")
def summary():
    batch = document_corpus.active()
    corpus = document_corpus.rows(batch) if batch else []
    with sqlite.connect() as conn:
        graph = conn.execute(
            "SELECT b.graph_node_count,b.graph_edge_count FROM build_batches b JOIN active_snapshot a "
            "ON a.active_version=b.batch_id LIMIT 1"
        ).fetchone()
    return {
        "documents": len({r["doc_id"] for r in corpus}),
        "chunks": len(corpus),
        "searchable_chunks": sum(not r.get("needs_review") and not r.get("is_toc") for r in corpus),
        "pending_review": sum(bool(r.get("needs_review")) for r in corpus),
        "graph_nodes": graph[0] if graph else 0,
        "graph_edges": graph[1] if graph else 0,
        "document_batch": batch,
    }


@router.get("/documents/{doc_id}/source")
def original_pdf(doc_id: str, knowledge_batch: str = Query(...), doc_version: str = Query(...)):
    source_file = None
    expected_hash = None
    for row in document_corpus.rows(knowledge_batch):
        if row["doc_id"] == doc_id and row["doc_version"] == doc_version:
            source_file, expected_hash = row["source_file"], row["source_sha256"]
            break
    if source_file is None:
        with sqlite.connect() as conn:
            row = conn.execute(
                "SELECT d.source_uri,d.file_sha256 FROM documents d JOIN chunks c "
                "ON c.doc_id=d.doc_id AND c.doc_version=d.doc_version "
                "WHERE c.batch_id=? AND d.doc_id=? AND d.doc_version=? AND d.access_level='public' LIMIT 1",
                (knowledge_batch, doc_id, doc_version),
            ).fetchone()
        if row:
            source_file, expected_hash = row["source_uri"], row["file_sha256"]
    if source_file is None:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Source not found in this batch")
    raw = (REPO_ROOT / "data/raw").resolve()
    target = (
        (REPO_ROOT / source_file).resolve()
        if source_file.startswith("data/raw/")
        else (raw / source_file).resolve()
    )
    if not target.is_relative_to(raw) or not target.is_file():
        raise ApiError(404, ErrorCode.NOT_FOUND, "Original PDF unavailable")
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected_hash:
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Original PDF hash mismatch")
    return FileResponse(
        target,
        media_type="application/pdf",
        filename=target.name,
        content_disposition_type="inline",
    )


@router.post(
    "/documents", status_code=201, dependencies=[Depends(require_roles(Role.KNOWLEDGE_ADMIN))]
)
def upload_document() -> None:
    raise ApiError(501, ErrorCode.NOT_IMPLEMENTED, "Use the reviewed offline ingestion workflow")
