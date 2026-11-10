"""Source-grounded development probes across all five PDFs; never scores generated answers."""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

from app.core.config import REPO_ROOT, get_env
from app.eval import retrieval
from app.rag import available_scopes, retrieve, retrieve_graph
from app.storage import document_corpus, neo4j_client


def verify(*, keyword_only: bool = False, simple_ten: bool = False) -> dict:
    graph_root = REPO_ROOT / "data/kb/cs2024-reviewed"
    questions = retrieval.load(
        graph_root / "retrieval_questions.jsonl",
        (graph_root / "retrieval_questions.sha256").read_text().strip(),
    )
    graph = retrieval.run(questions, retriever=retrieve_graph)
    probes = []
    for year in (2023, 2024, 2025):
        for major in ("计算机科学与技术", "网络工程", "数据科学与大数据技术", "软件工程"):
            probes.append(
                {
                    "question": f"{major}{year}级普通本科的学制是几年、授予什么学位？",
                    "expected_doc": f"curriculum-{year}",
                    "major": major,
                    "year": year,
                    "source_terms": ["学制", "学位"],
                }
            )
    for question, doc, terms in [
        ("课程考试迟到多少分钟不准参加考试？", "assessment-rules", ["迟到", "15"]),
        ("补考不及格后应怎样处理？", "assessment-rules", ["补考", "重修"]),
        ("申请期末考试缓考需要什么手续？", "assessment-rules", ["缓考", "申请"]),
        ("学位申请被拒绝可以申请复核吗？", "degree-rules", ["学位", "复核"]),
        ("学位获得者在什么情况下可能被撤销学位？", "degree-rules", ["撤销", "学位"]),
        ("学士学位申请应在多少日内决定受理？", "degree-rules", ["学士", "受理"]),
    ]:
        probes.append({"question": question, "expected_doc": doc, "source_terms": terms})
    if simple_ten:
        probes = [probes[i] for i in (0, 5, 11, 12, 14, 15, 16, 17)]
    records = []
    for i, probe in enumerate(probes):
        result = retrieve(probe["question"], {}, f"all-documents-{i}")
        sources = [e for e in result.evidence if e.doc_id == probe["expected_doc"]]
        source_text = "\n".join(e.text for e in sources)
        hit = result.status == "success" and all(
            term in source_text for term in probe["source_terms"]
        )
        if probe.get("major"):
            hit = hit and all(
                e.major == probe["major"] and e.entry_year == probe["year"] for e in result.evidence
            )
        records.append(
            {
                **probe,
                "status": result.status,
                "retrieval_type": result.retrieval_type,
                "retrieval_mode": result.retrieval_mode,
                "passed": hit,
                "citations": [
                    {
                        "doc_id": e.doc_id,
                        "page": e.page_start,
                        "major": e.major,
                        "entry_year": e.entry_year,
                        "review_status": e.verification_status,
                    }
                    for e in result.evidence
                ],
            }
        )
    negative = []
    for name, question, scope, expected in [
        ("missing_major", "2025级专业课程最低选修多少学分？", {}, "needs_context"),
        ("missing_year", "软件工程专业课程最低选修多少学分？", {}, "needs_context"),
        (
            "inconsistent_year",
            "软件工程2025级专业课程最低学分？",
            {"entry_year": 2024},
            "needs_context",
        ),
        (
            "wrong_college",
            "软件工程2025级专业课程最低学分？",
            {"college": "通信学院"},
            "insufficient",
        ),
        ("no_source", "学生宿舍空调电费每度多少钱？", {}, "insufficient"),
    ]:
        if simple_ten and name not in ("missing_major", "no_source"):
            continue
        r = retrieve(question, scope, "all-negative-" + name)
        negative.append(
            {"case": name, "status": r.status, "expected": expected, "passed": r.status == expected}
        )
    batch = document_corpus.active()
    return {
        "state": "passed"
        if all(r["passed"] for r in records + negative) and graph["path_hit_rate"] == 1.0
        else "failed",
        "checked_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "keyword_only_fault_injected": keyword_only,
        "simple_ten": simple_ten,
        "boundary": "AI-authored source-grounded development probes; not blind gold or answer scoring",
        "graph_regression": graph,
        "document_probes": records,
        "negative_probes": negative,
        "document_batch": batch,
        "document_index": document_corpus.status(batch),
        "scope_catalog": available_scopes(),
    }


if __name__ == "__main__":
    load_dotenv(REPO_ROOT / ".env.rag")
    get_env.cache_clear()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keyword-only",
        action="store_true",
        help="Explicitly simulate unavailable query embeddings",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--simple-ten", action="store_true", help="Eight source probes plus two negative cases"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Select a new report path")
    try:
        if args.keyword_only:
            with patch.object(
                document_corpus, "vector", side_effect=ValueError("explicit keyword-only test")
            ):
                result = verify(keyword_only=True, simple_ten=args.simple_ten)
        else:
            result = verify(simple_ten=args.simple_ten)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "state": result["state"],
                    "documents_passed": sum(r["passed"] for r in result["document_probes"]),
                    "documents_total": len(result["document_probes"]),
                },
                ensure_ascii=False,
            )
        )
        if result["state"] != "passed":
            raise SystemExit(1)
    finally:
        neo4j_client.close()
