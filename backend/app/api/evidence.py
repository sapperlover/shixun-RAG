"""GET /evidence/{citation_id} —— 按当次 knowledge_batch 读回原文（V1.2 附录 C.2）。

citation_id 在构建批次时生成并写入 relation_evidence（ADR-017），因此不依赖某次回答的上下文。
只返回 verified、属于该批次、可公开访问的证据。TODO(BE, D4)：登录后按角色放开 restricted 文档。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import fixtures
from app.core.config import get_env
from app.core.errors import ApiError, ErrorCode
from app.schemas.resources import EvidenceOut
from app.storage import evidence

router = APIRouter(tags=["evidence"])


@router.get("/evidence/{citation_id}", response_model=EvidenceOut)
def get_evidence(citation_id: str, knowledge_batch: str = Query(...)) -> EvidenceOut:
    if knowledge_batch == fixtures.STUB_BATCH and get_env().app_env != "prod":
        return _from_mock(citation_id)
    row = evidence.by_citation(knowledge_batch, citation_id)
    if row is None:
        raise ApiError(
            404, ErrorCode.NOT_FOUND, f"{knowledge_batch} 中没有可读回的引用 {citation_id}"
        )
    return EvidenceOut(knowledge_batch=knowledge_batch, **row)


def _from_mock(citation_id: str) -> EvidenceOut:
    """开发联调：X-Debug-Force-Status 返回的 mock 回答，其引用也能点开。"""
    for c in fixtures.load_mock("success").citations:
        if c.citation_id == citation_id:
            return EvidenceOut(
                citation_id=c.citation_id,
                knowledge_batch=fixtures.STUB_BATCH,
                relation_id=c.relation_id,
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                doc_title="【模拟】契约 mock 文档",
                doc_version=c.doc_version,
                section=c.section,
                page_start=c.page,
                page_end=c.page,
                text=c.excerpt,
                verification_status="verified",
            )
    raise ApiError(404, ErrorCode.NOT_FOUND, f"mock 中没有引用 {citation_id}")
