"""Source-review gate. Record delegated AI reviews separately from human reviews."""

import hashlib
import json
from pathlib import Path

from app.ingest.bundle import Bundle, BundleError

REVIEW_MARKER = "requires_human_review"
SOURCE_REVIEW_MARKER = "requires_source_review"


def check(bundle: Bundle) -> None:
    if not any(
        REVIEW_MARKER in d["notes"] or SOURCE_REVIEW_MARKER in d["notes"] for d in bundle.documents
    ):
        return
    if not bundle.relations or any(
        r["verification_status"] == "unverified" for r in bundle.relations
    ):
        raise BundleError("Real bundle has unreviewed relations; complete relations.csv first")
    if not any(r["verification_status"] == "verified" for r in bundle.relations):
        raise BundleError("Real bundle has no verified relations")
    path = Path(bundle.root) / "review_approval.json"
    try:
        approval = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BundleError("Missing human approval: review_approval.json") from None
    if not (
        approval.get("reviewer")
        and approval.get("reviewed_at")
        and approval.get("source_content_reviewed") is True
        and approval.get("scope_reviewed") is True
        and approval.get("manifest_sha256") == bundle.manifest_sha
    ):
        raise BundleError("Human approval incomplete or bundle changed after review")
    kind = approval.get("review_kind", "human")
    if kind not in ("human", "ai_source_review"):
        raise BundleError("Unknown review kind")
    if kind == "human" and approval.get("reviewer", "").startswith("codex-ai"):
        raise BundleError("AI source review cannot be recorded as human review")
    if kind == "ai_source_review" and not (
        approval.get("delegated_by") == "user"
        and approval.get("delegation_note", "").strip()
        and approval.get("reviewer", "").startswith("codex-ai")
        and approval.get("decision_report_sha256")
        and not any(REVIEW_MARKER in d["notes"] for d in bundle.documents)
    ):
        raise BundleError("AI review requires explicit delegation and source-review marker")
    if kind == "ai_source_review":
        try:
            actual = hashlib.sha256(
                (Path(bundle.root) / "review_decisions.json").read_bytes()
            ).hexdigest()
        except OSError:
            raise BundleError("Missing AI source-review decisions") from None
        if actual != approval["decision_report_sha256"]:
            raise BundleError("Source-review decisions changed after approval")
