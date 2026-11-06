"""GET /evidence/{citation_id} —— 按当次 knowledge_batch 读回原文（V1.2 附录 C.2）。

TODO(BE, D4)：从 SQLite chunks + relation_evidence 读取，并对 restricted 文档做权限检查。
骨架阶段：仅能读回 mock 中的引用。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import fixtures
from app.core.errors import ApiError, ErrorCode
from app.schemas.resources import EvidenceOut

router = APIRouter(tags=["evidence"])


@router.get("/evidence/{citation_id}", response_model=EvidenceOut)
def get_evidence(citation_id: str, knowledge_batch: str = Query(...)) -> EvidenceOut:
    if knowledge_batch == fixtures.STUB_BATCH:
        for c in fixtures.success().citations:
            if c.citation_id == citation_id:
                return EvidenceOut(
                    citation_id=c.citation_id,
                    knowledge_batch=knowledge_batch,
                    relation_id=c.relation_id,
                    chunk_id=c.chunk_id,
                    doc_id=c.doc_id,
                    doc_title="【模拟】计算机科学与技术专业培养方案",
                    doc_version=c.doc_version,
                    section=c.section,
                    page_start=c.page,
                    page_end=c.page,
                    text=c.excerpt,
                    verification_status="verified",
                )
    raise ApiError(404, ErrorCode.NOT_FOUND, f"{knowledge_batch} 中没有引用 {citation_id}")
