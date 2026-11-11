"""路径命中率仅统计正例，答案终态正确率含负例，引用覆盖率按可读回断言统计。"""

from __future__ import annotations

from collections import Counter
from math import ceil

from app.schemas.resources import EvalMetrics, EvalRecord


def compute(records: list[EvalRecord]) -> EvalMetrics:
    n = len(records)
    claims_total = sum(r.claims_total for r in records)
    positives = [r for r in records if r.expected_status == "success"]
    latencies = sorted(r.elapsed_ms for r in records)

    def hop_rate(hops):
        selected = [r for r in positives if r.hop_count == hops]
        return sum(r.path_hit for r in selected) / len(selected) if selected else None

    return EvalMetrics(
        questions=n,
        path_hit_rate=sum(r.path_hit for r in positives) / len(positives) if positives else None,
        answer_accuracy=sum(r.answer_correct for r in records) / n if n else None,
        citation_coverage=(
            sum(r.citation_covered for r in records) / claims_total if claims_total else None
        ),
        failure_distribution=dict(Counter(r.failure_stage for r in records if r.failure_stage)),
        two_hop_path_hit_rate=hop_rate(2),
        three_hop_path_hit_rate=hop_rate(3),
        api_answer_rate=sum(r.answer_mode == "llm" for r in positives) / len(positives)
        if positives
        else None,
        average_latency_ms=sum(latencies) / n if n else None,
        p95_latency_ms=latencies[ceil(n * 0.95) - 1] if n else None,
    )
