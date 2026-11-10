"""Public retrieval-only Python entrypoint. No answer-generation model is called."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import get_env, get_settings
from app.core.errors import ErrorCode, ServiceUnavailable
from app.retrieval import anchors, expand, intent, path_check, rank
from app.schemas.qa import ErrorInfo, Path, QARequest, Scope
from app.storage import evidence, snapshot

log = logging.getLogger(__name__)


class RAGEvidence(BaseModel):
    citation_id: str
    relation_id: str | None = None
    chunk_id: str
    doc_id: str
    doc_version: str
    doc_title: str
    page_start: int | None
    page_end: int | None
    section: str | None
    text: str
    verified_by: str | None = None
    verified_at: str | None = None
    verification_note: str | None = None
    source_kind: str = "ai_verified_excerpt"
    verification_status: str = "ai_source_reviewed"
    needs_review: bool = False
    source_file: str | None = None
    source_sha256: str | None = None
    entry_year: int | None = None
    major: str | None = None
    program_variant: str | None = None
    book_year: int | None = None
    plan_revision: str | None = None
    score: float | None = None
    scope_verified: bool = True


class RAGResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    status: Literal["success", "needs_context", "insufficient", "error"]
    retrieval_type: Literal["graph", "document"] = "graph"
    knowledge_batch: str | None = None
    retrieval_mode: Literal["hybrid", "graph_only", "keyword_only"] | None = None
    degraded_mode: bool = False
    degradation_reason: str | None = None
    paths: list[Path] = Field(default_factory=list)
    evidence: list[RAGEvidence] = Field(default_factory=list)
    missing_fields: list[Literal["major_code", "entry_year", "program_variant"]] = Field(
        default_factory=list
    )
    error: ErrorInfo | None = None
    hop_log: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    resolved_scope: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _complete(self) -> RAGResult:
        if self.retrieval_mode in ("graph_only", "keyword_only") and not self.degraded_mode:
            raise ValueError("graph_only requires explicit degradation")
        if self.degraded_mode and not self.degradation_reason:
            raise ValueError("degradation reason required")
        if self.status == "success":
            covered = {e.relation_id for e in self.evidence if e.text.strip()}
            if not self.knowledge_batch or self.error or self.missing_fields or not self.evidence:
                raise ValueError("success requires batch and readable evidence")
            if self.retrieval_type == "graph" and not self.paths:
                raise ValueError("graph success requires complete paths")
            if self.retrieval_type == "document" and self.paths:
                raise ValueError("direct document retrieval must not fabricate graph paths")
            if not all(e.relation_id in covered for p in self.paths for e in p.edges):
                raise ValueError("every path edge needs readable evidence")
        if self.status == "needs_context" and not self.missing_fields:
            raise ValueError("missing_fields required")
        if self.status in ("error", "insufficient") and self.error is None:
            raise ValueError("failure reason required")
        if self.status != "success" and (self.paths or self.evidence):
            raise ValueError("unsuccessful retrieval must not expose usable evidence")
        return self


def retrieve(question: str, scope: Scope | dict | None, request_id: str) -> RAGResult:
    """Retrieve verified graph paths or direct document evidence, never generated answers."""
    if get_env().document_retrieval_enabled:
        from app.retrieval.documents import retrieve_documents

        return retrieve_documents(question, scope, request_id)
    return retrieve_graph(question, scope, request_id)


def available_scopes() -> dict:
    """Backend dropdown data: college, actual programme names, years and variants."""
    from app.storage import document_corpus

    batch = document_corpus.active()
    if not batch:
        return {"college": "计算机学院（国家示范性软件学院）", "programs": []}
    programs = {}
    for row in document_corpus.rows(batch):
        if not row.get("major") or row.get("is_toc"):
            continue
        key = (row["major"], row["book_year"], row["program_variant"], row["plan_revision"])
        programs.setdefault(
            key,
            {
                k: row.get(k)
                for k in (
                    "major",
                    "entry_year",
                    "book_year",
                    "program_variant",
                    "plan_revision",
                    "program_title",
                )
            },
        )
    return {"college": "计算机学院（国家示范性软件学院）", "programs": list(programs.values())}


def retrieve_graph(question: str, scope: Scope | dict | None, request_id: str) -> RAGResult:
    """Validate input; return retrieval state, full source text and 2/3-hop paths.

    Invalid input raises pydantic.ValidationError (or ValueError for blank request_id).
    Service failures return status=error; the caller owns HTTP, auth and answer generation.
    """
    if not request_id.strip():
        raise ValueError("request_id must not be blank")
    selected_scope = Scope.model_validate(scope or {}) if not isinstance(scope, Scope) else scope
    # v1 contains one professional programme. Callers need not know school codes.
    if selected_scope.major_code is None:
        selected_scope = selected_scope.model_copy(update={"major_code": "计算机科学与技术"})
    req = QARequest(question=question, scope=selected_scope)
    if not question.strip():
        raise ValueError("question must not be blank")
    batch = None
    try:
        parsed = intent.parse(req.question, req.scope)
        if parsed.missing_fields:
            return RAGResult(
                request_id=request_id, status="needs_context", missing_fields=parsed.missing_fields
            )
        batch = snapshot.get_active()
        found, vector_failure = anchors.match_with_diagnostics(parsed, batch)
        parsed = replace(parsed, mentions=[a.entity_id for a in found if a.match != "scope"])
        expansion = expand.expand(found[: get_settings().retrieval.max_anchors], parsed, batch)
        reason = vector_failure or expansion.degradation_reason
        common = dict(
            request_id=request_id,
            knowledge_batch=batch,
            retrieval_mode="graph_only" if reason else expansion.retrieval_mode,
            degraded_mode=bool(reason),
            degradation_reason=reason,
            hop_log=[vars(h) for h in expansion.hop_log],
        )

        def insufficient(code: ErrorCode, hop: int | None = None) -> RAGResult:
            return RAGResult(
                **common,
                status="insufficient",
                error=ErrorInfo(code=code, failed_hop=hop, retryable=False),
            )

        if not found:
            return insufficient(ErrorCode.ANCHOR_NOT_FOUND)
        if not expansion.candidates:
            return insufficient(
                expansion.failed_code or ErrorCode.PATH_INCOMPLETE, expansion.failed_hop
            )
        complete, code, hop = path_check.filter_complete(expansion.candidates, parsed, batch)
        if code == ErrorCode.VERSION_CONFLICT or not complete:
            return insufficient(
                code or expansion.failed_code or ErrorCode.PATH_INCOMPLETE,
                hop or expansion.failed_hop,
            )
        selected = rank.rank(complete, parsed)
        source_rows = evidence.all_evidence(
            batch, (e.relation_id for c in selected for e in c.path.edges)
        )
        rows = {}
        for row in source_rows:
            if row["text"].strip():
                rows.setdefault(row["relation_id"], []).append(row)
        paths, sources = [], {}
        for candidate in selected:
            edges = candidate.path.edges
            if len(candidate.evidence) != len(edges):
                continue
            if any(e.relation_id not in rows for e in edges):
                continue
            paths.append(candidate.path)
            for edge in edges:
                for row in rows[edge.relation_id]:
                    sources[row["citation_id"]] = RAGEvidence(
                        **{key: row[key] for key in RAGEvidence.model_fields if key in row}
                    )
        if not paths:
            return insufficient(ErrorCode.EVIDENCE_UNVERIFIED)
        return RAGResult(**common, status="success", paths=paths, evidence=list(sources.values()))
    except ServiceUnavailable as exc:
        return RAGResult(
            request_id=request_id,
            status="error",
            knowledge_batch=batch,
            error=ErrorInfo(code=exc.code, retryable=True),
        )
    except Exception:
        log.exception("RAG retrieval failed request_id=%s", request_id)
        return RAGResult(
            request_id=request_id,
            status="error",
            knowledge_batch=batch,
            error=ErrorInfo(code=ErrorCode.INTERNAL_ERROR, retryable=True),
        )
