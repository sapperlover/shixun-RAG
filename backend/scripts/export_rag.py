"""Export source, all raw documents and a portable reviewed bundle; exclude credentials/runtime."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.core.config import REPO_ROOT
from app.ingest import bundle, review

DIRECTORIES = (
    "backend",
    "config",
    "contracts",
    "docs",
    "data/raw",
    "data/processed",
    "data/demo",
    "data/relations",
    "data/kb/cs2024-reviewed",
    "data/kb/cs2024-v2",
    "data/corpus/all-documents-v3",
)
ROOT_FILES = (
    "README.md",
    ".gitignore",
    ".gitattributes",
    ".env.rag.example",
    "docker-compose.rag.yml",
)
EXCLUDED = {"__pycache__", ".pytest_cache", ".ruff_cache", ".cache", ".venv", ".git"}
BUNDLE_DIR = "data/kb/cs2024-reviewed"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def export(root: Path, output: Path) -> dict:
    root, output = root.resolve(), output.resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite an existing export")
    b = bundle.load(root / BUNDLE_DIR)
    review.check(b)
    files: dict[str, bytes] = {}
    for directory in DIRECTORIES:
        start = root / directory
        if not start.is_dir():
            continue
        for file in sorted(start.rglob("*")):
            if not file.is_file():
                continue
            if file.is_symlink() or not file.resolve().is_relative_to(root):
                raise ValueError("Export must not follow files outside the repository")
            rel = file.relative_to(root)
            if any(part in EXCLUDED for part in rel.parts):
                continue
            if file.name.startswith(".env") or file.suffix in (
                ".pyc",
                ".db",
                ".sqlite",
                ".faiss",
                ".key",
                ".pem",
            ):
                continue
            files[rel.as_posix()] = file.read_bytes()
    for name in ROOT_FILES:
        if (root / name).is_file():
            files[name] = (root / name).read_bytes()

    # Rebase source locators inside the export only. The live bundle is unchanged.
    documents_key = BUNDLE_DIR + "/documents.csv"
    reader = csv.DictReader(io.StringIO(files[documents_key].decode("utf-8")))
    columns, documents = reader.fieldnames, list(reader)
    for document in documents:
        uri = urlsplit(document["source_uri"])
        name = Path(unquote(uri.path).replace("\\", "/")).name
        relative_source = "data/raw/" + name
        if relative_source not in files or _sha(files[relative_source]) != document["file_sha256"]:
            raise ValueError("Raw source missing or mismatched: " + name)
        document["source_uri"] = relative_source
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(documents)
    files[documents_key] = stream.getvalue().encode("utf-8")
    manifest = _sha(b"".join(files[BUNDLE_DIR + "/" + f] for f in bundle.FILES))
    decision_key, approval_key = (
        BUNDLE_DIR + "/" + name for name in ("review_decisions.json", "review_approval.json")
    )
    decisions = json.loads(files[decision_key])
    transform = {
        "original_manifest_sha256": b.manifest_sha,
        "portable_manifest_sha256": manifest,
        "changed_fields": ["documents.csv:source_uri"],
        "source_content_unchanged": True,
        "reviewer_and_original_decisions_preserved": True,
    }
    decisions["portability_transformation"] = transform
    files[decision_key] = _json(decisions)
    approval = json.loads(files[approval_key])
    approval["manifest_sha256"] = manifest
    approval["decision_report_sha256"] = _sha(files[decision_key])
    approval["portability_transformation"] = transform
    files[approval_key] = _json(approval)
    preparation_key = BUNDLE_DIR + "/preparation_report.json"
    if preparation_key in files:
        preparation = json.loads(files[preparation_key])
        preparation.update(manifest_sha256=manifest, state="portable_reviewed_not_built")
        files[preparation_key] = _json(preparation)
    files[BUNDLE_DIR + "/portability.json"] = _json(transform)
    index = {name: _sha(data) for name, data in sorted(files.items())}
    files["PACKAGE_MANIFEST.json"] = _json(
        {
            "format": "rag-source-handoff-v1",
            "files_sha256": index,
            "includes_credentials": False,
            "includes_runtime_databases": False,
            "raw_pdf_count": sum(n.startswith("data/raw/") and n.endswith(".pdf") for n in files),
            "rebuild_required": True,
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return {
        "archive": str(output),
        "files": len(files),
        "bytes": output.stat().st_size,
        "sha256": _sha(output.read_bytes()),
        "portable_manifest_sha256": manifest,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(REPO_ROOT, args.output), ensure_ascii=False, indent=2))
