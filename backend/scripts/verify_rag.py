"""Verify the retrieval module against Neo4j, SQLite and the configured embedding API.

Run from backend/: python -m scripts.verify_rag --build --publish
No answer-generation service is used. Without --build this only queries the active batch.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

from app.core.config import REPO_ROOT, get_env
from app.core.errors import ErrorCode, ServiceUnavailable
from app.eval import retrieval
from app.graph import build, dictionary, publish, validate
from app.ingest import bundle, review
from app.rag import retrieve_graph as retrieve
from app.storage import faiss_store, neo4j_client, snapshot, sqlite


def verify(bundle_dir: Path, *, create_batch: bool, publish_batch: bool) -> dict:
    if publish_batch and not create_batch:
        raise ValueError("--publish requires --build")
    b = bundle.load(bundle_dir)
    review.check(b)
    questions_path = bundle_dir / "retrieval_questions.jsonl"
    checksum = (bundle_dir / "retrieval_questions.sha256").read_text().strip()
    questions = retrieval.load(questions_path, checksum)
    sqlite.migrate()
    neo4j_client.ping()
    neo4j_client.apply_constraints()
    checks = None
    if create_batch:
        batch = build.build_staging(bundle_dir)
        checks = validate.validate(batch)
        if not checks["ok"]:
            raise ValueError(f"Batch validation failed: {checks}")
        rows = neo4j_client.run_read(
            "MATCH (a)-[r {batch_id:$batch, verified:true}]->(z) "
            "RETURN a.entity_id AS a, type(r) AS t, z.entity_id AS z",
            batch=batch,
        )
        edges = {(r["a"], r["t"], r["z"]) for r in rows}
        if not all(
            (e.from_, e.type, e.to) in edges for q in questions for e in q.gold_relation_path
        ):
            raise ValueError("Reviewed question path is not present in this batch")
        if not publish_batch:
            return {"state": "validated_not_published", "batch": batch, "checks": checks}
        publish.publish(batch)
    else:
        batch = snapshot.get_active()
    dictionary.load.cache_clear()
    positive = retrieval.run(questions, retriever=retrieve)
    cases = [
        ("missing_year", "专业课程最低选修多少学分？", {}, "needs_context"),
        ("wrong_year", "专业课程最低选修多少学分？", {"entry_year": 2025}, "insufficient"),
        (
            "rejected_relation",
            "专业教育课程的修读规定是什么？",
            {"entry_year": 2024},
            "insufficient",
        ),
        ("no_source", "学生宿舍空调电费每度多少钱？", {"entry_year": 2024}, "insufficient"),
        ("no_prerequisite", "数据结构之前需要先修哪些课？", {"entry_year": 2024}, "insufficient"),
    ]
    negatives = []
    for name, question, scope, expected in cases:
        result = retrieve(question, scope, "verify-" + name)
        negatives.append(
            {
                "case": name,
                "expected": expected,
                "status": result.status,
                "passed": result.status == expected,
                "error": result.error.model_dump(mode="json") if result.error else None,
            }
        )
    sample_question = "2024级培养方案中专业课程最多可选修本院其他专业的课程多少学分？"
    sample = retrieve(sample_question, {"entry_year": 2024}, "verify-sample")
    with patch.object(faiss_store, "status", return_value="not built"):
        degraded = retrieve(sample_question, {"entry_year": 2024}, "verify-vector-down")
    dictionary.load.cache_clear()
    with patch.object(
        neo4j_client, "run_read", side_effect=ServiceUnavailable(ErrorCode.GRAPH_UNAVAILABLE)
    ):
        graph_down = retrieve(sample_question, {"entry_year": 2024}, "verify-graph-down")
    dictionary.load.cache_clear()
    faults = {
        "vector_unavailable": {
            "fault_injected_in_process": True,
            "status": degraded.status,
            "mode": degraded.retrieval_mode,
            "passed": degraded.status == "success"
            and degraded.degraded_mode
            and degraded.retrieval_mode == "graph_only",
        },
        "graph_unavailable": {
            "fault_injected_in_process": True,
            "status": graph_down.status,
            "passed": graph_down.status == "error"
            and graph_down.error is not None
            and graph_down.error.code == ErrorCode.GRAPH_UNAVAILABLE,
        },
    }
    index_status = faiss_store.status(batch)
    complete = (
        index_status == "ready"
        and positive["path_hit_rate"] == 1.0
        and positive["gold_evidence_hit_rate"] == 1.0
        and all(r["status_match"] for r in positive["records"])
        and all(n["passed"] for n in negatives)
        and all(f["passed"] for f in faults.values())
    )
    return {
        "state": "passed" if complete else "failed",
        "batch": batch,
        "checked_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "source_manifest_sha256": b.manifest_sha,
        "dataset_sha256": checksum,
        "evaluation_boundary": "AI-made and AI-source-reviewed development set; not human blind gold",
        "embedding_model": get_env().embedding_model,
        "embedding_dimensions": get_env().embedding_dimensions,
        "faiss": index_status,
        "batch_checks": checks,
        "positive_retrieval": positive,
        "negative_cases": negatives,
        "fault_cases": faults,
        "sample": sample.model_dump(mode="json", by_alias=True),
    }


if __name__ == "__main__":
    load_dotenv(REPO_ROOT / ".env.rag")
    get_env.cache_clear()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=REPO_ROOT / "data/kb/cs2024-reviewed")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing verification report")
    try:
        report = verify(args.bundle, create_batch=args.build, publish_batch=args.publish)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"state": report["state"], "batch": report["batch"], "report": str(args.output)},
                ensure_ascii=False,
            )
        )
        if report["state"] == "failed":
            sys.exit(1)
    finally:
        neo4j_client.close()
