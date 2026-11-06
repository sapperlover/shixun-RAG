"""★ 多跳问答主流程：在线问答（api/qa.py）与评测（eval/runner.py）共用的唯一入口。

流程（V1.2 §4.2/§4.3）：
  固定 batch → 解析问题 → [缺范围 → needs_context]
  → 锚点 → [无锚点 → insufficient/ANCHOR_NOT_FOUND]
  → 逐跳扩展 → 完整路径判定 → [不完整/未核验/冲突 → insufficient]
  → 排序 → 事实 → 生成 → 断言校验（不过重试 1 次 → 模板降级 → 仍不过 insufficient）
  → success
基础设施不可用 → error（HTTP 503）。

本文件只负责编排和终态判定；各步骤的实现在对应模块中，替换实现时不需要修改本文件。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.answer import facts as facts_mod
from app.answer import generate as gen_mod
from app.answer import template, validate_claims
from app.core.config import get_settings
from app.core.errors import ErrorCode, ServiceUnavailable
from app.domain import Draft, HopLogEntry
from app.retrieval import anchors as anchors_mod
from app.retrieval import expand as expand_mod
from app.retrieval import intent as intent_mod
from app.retrieval import path_check, rank
from app.schemas.qa import Claim, QARequest, QAResponse
from app.storage import snapshot

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    response: QAResponse
    hop_log: list[HopLogEntry] = field(default_factory=list)


def answer_question(req: QARequest, request_id: str) -> PipelineResult:
    try:
        return _run(req, request_id)
    except ServiceUnavailable as exc:
        log.warning("service unavailable: %s", exc)
        return PipelineResult(QAResponse.service_error(request_id, exc.code))


def _run(req: QARequest, request_id: str) -> PipelineResult:
    settings = get_settings()
    batch = snapshot.get_active()  # 本次请求内固定，不再重新读取

    intent = intent_mod.parse(req.question, req.scope)
    if intent.missing_fields:
        return PipelineResult(QAResponse.needs_context(request_id, batch, intent.missing_fields))

    anchors = anchors_mod.match(intent, batch)[: settings.retrieval.max_anchors]
    if not anchors:
        return PipelineResult(
            QAResponse.insufficient(request_id, batch, ErrorCode.ANCHOR_NOT_FOUND)
        )

    exp = expand_mod.expand(anchors, intent, batch)
    degraded = exp.degradation_reason
    if not exp.candidates:
        return PipelineResult(
            QAResponse.insufficient(
                request_id,
                batch,
                ErrorCode.PATH_INCOMPLETE,
                exp.failed_hop,
                retrieval_mode=exp.retrieval_mode,
                degradation_reason=degraded,
            ),
            exp.hop_log,
        )

    complete, fail_code, fail_hop = path_check.filter_complete(exp.candidates, intent, batch)
    if not complete:
        return PipelineResult(
            QAResponse.insufficient(
                request_id,
                batch,
                fail_code or ErrorCode.PATH_INCOMPLETE,
                fail_hop,
                retrieval_mode=exp.retrieval_mode,
                degradation_reason=degraded,
            ),
            exp.hop_log,
        )

    ranked = rank.rank(complete, intent)
    facts = facts_mod.build(ranked, batch)

    draft, validation = _generate_with_guard(req.question, facts, settings.generation.max_retries)
    if not validation.kept:
        log.info("all claims dropped: %s", validation.dropped)
        return PipelineResult(
            QAResponse.insufficient(
                request_id,
                batch,
                ErrorCode.CITATION_INVALID,
                retrieval_mode=exp.retrieval_mode,
                degradation_reason=degraded,
            ),
            exp.hop_log,
        )

    reasons = [r for r in (degraded, draft.degradation_reason) if r]
    used_paths = {pid for c in validation.kept for pid in c.path_ids}
    used_cits = {cid for c in validation.kept for cid in c.citation_ids}
    response = QAResponse(
        request_id=request_id,
        status="success",
        knowledge_batch=batch,
        retrieval_mode=exp.retrieval_mode,
        degraded_mode=bool(reasons),
        degradation_reason=",".join(reasons) or None,
        answer_mode=draft.answer_mode,
        answer=draft.answer,
        claims=[Claim(**vars(c)) for c in validation.kept],
        paths=[cp.path for cp in ranked if cp.path.path_id in used_paths],
        citations=[f.citation for f in facts if f.citation.citation_id in used_cits],
        missing_fields=[],
        error=None,
    )
    return PipelineResult(response, exp.hop_log)


def _generate_with_guard(question, facts, max_retries):
    """生成 → 校验；不过则重试；仍不过则模板降级；模板也不过时返回空 kept。"""
    draft: Draft | None = None
    for _ in range(1 + max_retries):
        try:
            draft = gen_mod.generate(question, facts)
        except ServiceUnavailable:
            break  # 模型不可用 → 直接走模板
        validation = validate_claims.validate(draft.claims, facts)
        if validation.ok:
            return draft, validation
    if get_settings().generation.fallback == "template":
        draft = template.render(facts, reason="llm_unavailable" if draft is None else "llm_invalid")
        return draft, validate_claims.validate(draft.claims, facts)
    if draft is None:
        raise ServiceUnavailable(ErrorCode.LLM_UNAVAILABLE)
    return draft, validate_claims.validate(draft.claims, facts)
