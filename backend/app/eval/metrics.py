"""三项核心指标（V1.2 §6.1，与 PRD 一致）。负例集单独统计，不改变分母。"""

from __future__ import annotations

from collections import Counter

from app.schemas.resources import EvalMetrics, EvalRecord


def compute(records: list[EvalRecord]) -> EvalMetrics:
    n = len(records)
    claims_total = sum(r.claims_total for r in records)
    return EvalMetrics(
        questions=n,
        path_hit_rate=sum(r.path_hit for r in records) / n if n else None,
        answer_accuracy=sum(r.answer_correct for r in records) / n if n else None,
        citation_coverage=(
            sum(r.citation_covered for r in records) / claims_total if claims_total else None
        ),
        failure_distribution=dict(Counter(r.failure_stage for r in records if r.failure_stage)),
    )
