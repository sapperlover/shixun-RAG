"""Shared online/evaluation pipeline: retrieval -> cited facts -> API -> guards."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app import rag
from app.answer import generate as gen_mod
from app.answer import retrieved_facts, template, validate_claims
from app.core.config import get_settings
from app.core.errors import ErrorCode, ServiceUnavailable
from app.domain import Draft, HopLogEntry
from app.schemas.qa import Claim, QARequest, QAResponse

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    response: QAResponse
    hop_log: list[HopLogEntry] = field(default_factory=list)


def answer_question(req: QARequest, request_id: str) -> PipelineResult:
    try:
        return _run(req, request_id)
    except ServiceUnavailable as exc:
        log.warning("Question failed: %s", exc.code)
        return PipelineResult(QAResponse.service_error(request_id, exc.code))


def _run(req: QARequest, request_id: str) -> PipelineResult:
    result = rag.retrieve(req.question, req.scope, request_id)
    hops = [HopLogEntry(**h) for h in result.hop_log]
    common = dict(
        retrieval_type=result.retrieval_type,
        warnings=result.warnings,
        resolved_scope=result.resolved_scope or req.scope.model_dump(),
        hop_log=result.hop_log,
    )
    if result.status != "success":
        if result.status == "needs_context":
            response = QAResponse.needs_context(
                request_id, result.knowledge_batch, result.missing_fields
            )
        elif result.status == "error":
            response = QAResponse.service_error(
                request_id, result.error.code, result.knowledge_batch
            )
        else:
            response = QAResponse.insufficient(
                request_id,
                result.knowledge_batch,
                result.error.code,
                result.error.failed_hop,
                retrieval_mode=result.retrieval_mode,
                degradation_reason=result.degradation_reason,
            )
        return PipelineResult(QAResponse(**{**response.model_dump(), **common}), hops)

    facts = retrieved_facts.build(result)
    draft, validation = _generate_with_guard(
        req.question, facts, get_settings().generation.max_retries
    )
    if not validation.kept:
        response = QAResponse.insufficient(
            request_id,
            result.knowledge_batch,
            ErrorCode.CITATION_INVALID,
            retrieval_mode=result.retrieval_mode,
            degradation_reason=result.degradation_reason,
        )
        return PipelineResult(QAResponse(**{**response.model_dump(), **common}), hops)

    reasons = [r for r in (result.degradation_reason, draft.degradation_reason) if r]
    used_paths = {pid for c in validation.kept for pid in c.path_ids}
    used_cits = {cid for c in validation.kept for cid in c.citation_ids}
    citations = {f.citation.citation_id: f.citation for f in facts}
    response = QAResponse(
        request_id=request_id,
        status="success",
        knowledge_batch=result.knowledge_batch,
        retrieval_mode=result.retrieval_mode,
        degraded_mode=bool(reasons),
        degradation_reason=",".join(reasons) or None,
        answer_mode=draft.answer_mode,
        answer=template.compose(validation.kept),
        claims=[Claim(**vars(c)) for c in validation.kept],
        paths=[p for p in result.paths if p.path_id in used_paths],
        citations=[c for cid, c in citations.items() if cid in used_cits],
        missing_fields=[],
        error=None,
        **common,
    )
    return PipelineResult(response, hops)


def _generate_with_guard(question, facts, max_retries):
    draft: Draft | None = None
    for _ in range(1 + max_retries):
        try:
            draft = gen_mod.generate(question, facts)
        except ServiceUnavailable:
            break
        validation = validate_claims.validate(draft.claims, facts)
        if validation.ok and validation.kept:
            return draft, validation
    if get_settings().generation.fallback == "template":
        draft = template.render(facts, reason="llm_unavailable" if draft is None else "llm_invalid")
        return draft, validate_claims.validate(draft.claims, facts)
    if draft is None:
        raise ServiceUnavailable(ErrorCode.LLM_UNAVAILABLE)
    return draft, validate_claims.validate(draft.claims, facts)
