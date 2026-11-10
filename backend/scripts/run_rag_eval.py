"""Run frozen, human-reviewed retrieval questions, without invoking generation."""

import argparse
import json
from pathlib import Path

from app.eval.retrieval import load, run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    questions = load(args.questions, args.sha256)
    if len([q for q in questions if q.expected_status == "success"]) < 10 or any(
        sum(q.expected_status == "success" and q.hop_count == h for q in questions) < 4
        for h in (2, 3)
    ):
        parser.error("Formal evaluation requires >=10 positive questions, >=4 each of 2/3 hops")
    if args.output.exists():
        parser.error("Refusing to overwrite an evaluation report")
    report = run(questions)
    report["dataset_sha256"] = args.sha256
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
