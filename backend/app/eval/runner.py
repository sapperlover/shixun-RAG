"""评测执行：逐题调用 pipeline.answer_question（与线上同一条链路），输出 records 与指标。"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from app import pipeline
from app.core.config import get_env, get_settings
from app.core.logging import new_request_id
from app.eval import attribution, metrics
from app.schemas.qa import QARequest, QAResponse
from app.schemas.resources import EvalMetrics, EvalQuestion, EvalRecord, GoldEdge


def predicted_edges(resp: QAResponse) -> list[list[GoldEdge]]:
    return [[GoldEdge(from_=e.from_, type=e.type, to=e.to) for e in p.edges] for p in resp.paths]


def is_path_hit(q: EvalQuestion, resp: QAResponse) -> bool:
    """输出路径中任意一条与标准关系链完全一致（按业务实体 ID，不含 batch）。"""
    if not q.gold_relation_path:
        return resp.status == q.expected_status
    gold = [(e.from_, e.type, e.to) for e in q.gold_relation_path]
    return any([(e.from_, e.type, e.to) for e in p] == gold for p in predicted_edges(resp))


def is_answer_correct(q: EvalQuestion, resp: QAResponse) -> bool:
    """自动初判：终态一致，且 success 时全部 key_points 出现在答案中。最终需人工复核。"""
    if resp.status != q.expected_status:
        return False
    if resp.status != "success":
        return True
    return all(kp in (resp.answer or "") for kp in q.key_points)


def run(questions: list[EvalQuestion], out_dir: Path) -> tuple[str, EvalMetrics]:
    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    records: list[EvalRecord] = []
    for q in questions:
        rid = new_request_id()
        t0 = time.perf_counter()
        resp = pipeline.answer_question(QARequest(question=q.question, scope=q.scope), rid).response
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
                citation_covered=len(resp.claims),  # 经过 validate_claims 的断言都有可读回引用
                claims_total=len(resp.claims),
                failure_stage=attribution.attribute(q, resp, hit, correct),
                elapsed_ms=elapsed,
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
