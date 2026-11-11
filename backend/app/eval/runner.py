"""评测执行：逐题调用 pipeline.answer_question（与线上同一条链路），输出 records 与指标。"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from app import pipeline
from app.core.config import get_env, get_settings
from app.core.logging import new_request_id
from app.eval import attribution, metrics
from app.schemas.qa import QARequest, QAResponse
from app.schemas.resources import EvalMetrics, EvalQuestion, EvalRecord, GoldEdge
from app.storage import document_corpus, evidence


def predicted_edges(resp: QAResponse) -> list[list[GoldEdge]]:
    return [[GoldEdge(from_=e.from_, type=e.type, to=e.to) for e in p.edges] for p in resp.paths]


def is_path_hit(q: EvalQuestion, resp: QAResponse) -> bool:
    """输出路径中任意一条与标准关系链的边集合完全一致（按业务实体 ID，不含 batch，与书写顺序无关）。"""
    if not q.gold_relation_path:
        return resp.status == q.expected_status
    gold = {(e.from_, e.type, e.to) for e in q.gold_relation_path}
    return any({(e.from_, e.type, e.to) for e in p} == gold for p in predicted_edges(resp))


def is_answer_correct(q: EvalQuestion, resp: QAResponse) -> bool:
    """自动初判：终态一致，且 success 时全部 key_points 出现在答案中。最终需人工复核。"""
    if resp.status != q.expected_status:
        return False
    if resp.status != "success":
        return True
    answer = re.sub(r"\s+", "", resp.answer or "")
    return bool(q.key_points) and all(
        bool(re.search(r"(?<![\d.])" + re.escape(kp) + r"(?![\d.])", answer))
        if re.fullmatch(r"\d+(?:\.\d+)?", kp)
        else kp in answer
        for kp in q.key_points
    )


def covered_claims(resp: QAResponse) -> int:
    """Independently read citations from the response batch, rather than assume coverage."""
    readable = set()
    for citation in resp.citations:
        row = evidence.by_citation(resp.knowledge_batch, citation.citation_id)
        if row is None and resp.retrieval_type == "document":
            row = document_corpus.by_citation(resp.knowledge_batch, citation.citation_id)
        if row and row["text"].strip():
            readable.add(citation.citation_id)
    return sum(bool(c.citation_ids) and set(c.citation_ids) <= readable for c in resp.claims)


def run(
    questions: list[EvalQuestion], out_dir: Path, *, run_id: str | None = None
) -> tuple[str, EvalMetrics]:
    run_id = run_id or f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    records: list[EvalRecord] = []
    for q in questions:
        rid = new_request_id()
        t0 = time.perf_counter()
        result = pipeline.answer_question(QARequest(question=q.question, scope=q.scope), rid)
        resp = result.response
        elapsed = int((time.perf_counter() - t0) * 1000)
        hit = is_path_hit(q, resp)
        correct = is_answer_correct(q, resp)
        paths = predicted_edges(resp)
        records.append(
            EvalRecord(
                question_id=q.question_id,
                request_id=rid,
                batch_id=resp.knowledge_batch,
                status=resp.status,
                predicted_path=paths[0] if paths else [],
                path_hit=hit,
                answer_correct=correct,
                citation_covered=covered_claims(resp),
                claims_total=len(resp.claims),
                failure_stage=attribution.attribute(q, resp, hit, correct),
                elapsed_ms=elapsed,
                question=q.question,
                answer=resp.answer,
                answer_mode=resp.answer_mode,
                expected_status=q.expected_status,
                hop_count=q.hop_count,
                response=resp.model_dump(mode="json", by_alias=True),
                hop_log=[vars(h) for h in result.hop_log],
            )
        )

    m = metrics.compute(records)
    with open(run_dir / "records.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(r.model_dump_json(by_alias=True) + "\n")
    summary = {
        "run_id": run_id,
        "git_commit": get_env().git_commit,
        "scorer_version": get_settings().eval.scorer_version,
        "settings": get_settings().model_dump(),
        "metrics": m.model_dump(),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_id, m
