"""Record source-review sign-off; delegated AI reviews never impersonate a human."""

import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path

from app.ingest import bundle, review


def approve(
    root: Path,
    reviewer: str,
    review_kind: str = "human",
    delegated_by: str | None = None,
    delegation_note: str | None = None,
):
    if not reviewer.strip():
        raise ValueError("Reviewer cannot be blank")
    b = bundle.load(root)
    with (root / "review_checklist.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if {r["chunk_id"] for r in rows} != {c["chunk_id"] for c in b.chunks}:
        raise ValueError("Review checklist must cover every source chunk")
    if any(r["content_reviewed"] != "yes" or r["scope_reviewed"] != "yes" for r in rows):
        raise ValueError("Review all source chunks and scope; mark checklist yes only after review")
    if any(r["verification_status"] == "unverified" for r in b.relations):
        raise ValueError("Review every relation: verified or rejected")
    if not any(r["verification_status"] == "verified" for r in b.relations):
        raise ValueError("No verified relations to approve")
    if review_kind == "human" and reviewer.startswith("codex-ai"):
        raise ValueError("An AI reviewer must use review_kind=ai_source_review")
    approval = dict(
        reviewer=reviewer,
        reviewed_at=datetime.datetime.now(datetime.UTC).isoformat(),
        source_content_reviewed=True,
        scope_reviewed=True,
        manifest_sha256=b.manifest_sha,
        review_kind=review_kind,
    )
    if review_kind == "ai_source_review":
        if (
            delegated_by != "user" or not delegation_note or not delegation_note.strip()
            or not reviewer.startswith("codex-ai")
        ):
            raise ValueError("AI review requires explicit user delegation and an AI reviewer ID")
        if any(review.REVIEW_MARKER in d["notes"] for d in b.documents):
            raise ValueError("Human-only bundles cannot be signed as AI-reviewed bundles")
        approval.update(
            delegated_by=delegated_by,
            delegation_note=delegation_note,
            decision_report_sha256=hashlib.sha256(
                (root / "review_decisions.json").read_bytes()
            ).hexdigest(),
        )
    elif review_kind != "human":
        raise ValueError("Unknown review kind")
    (root / "review_approval.json").write_text(
        json.dumps(approval, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    review.check(b)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--review-kind", choices=["human", "ai_source_review"], default="human")
    parser.add_argument("--delegated-by", choices=["user"])
    parser.add_argument("--delegation-note")
    args = parser.parse_args()
    approve(args.bundle, args.reviewer, args.review_kind, args.delegated_by, args.delegation_note)
