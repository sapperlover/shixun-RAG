import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from app.ingest import bundle, review
from scripts.configure_rag import configure
from scripts.export_rag import BUNDLE_DIR, export

REPO = Path(__file__).parents[3]


def test_export_is_portable_keeps_review_and_excludes_secrets(tmp_path):
    root = tmp_path / "source"
    shutil.copytree(REPO / BUNDLE_DIR, root / BUNDLE_DIR)
    b = bundle.load(root / BUNDLE_DIR)
    raw = root / "data/raw"
    raw.mkdir(parents=True)
    for d in b.documents:
        source = REPO / "data/raw" / Path(unquote(urlsplit(d["source_uri"]).path)).name
        if not source.exists():
            pytest.skip("Raw PDF is required for export tests; included in the handoff ZIP")
        shutil.copy2(source, raw / source.name)
    (raw / "other.pdf").write_bytes(b"another-source")
    secret = "TEST-SECRET-DO-NOT-EXPORT"
    (root / ".env.rag").write_text("EMBEDDING_API_KEY=" + secret)
    (root / ".env.rag.example").write_text("EMBEDDING_API_KEY=\n")
    (root / "backend").mkdir()
    (root / "backend/.env").write_text(secret)
    (root / "backend/example.py").write_text("# source file\n")
    before = (root / BUNDLE_DIR / "documents.csv").read_bytes()
    output = tmp_path / "handoff.zip"
    export(root, output)
    extracted = tmp_path / "new-machine"
    with zipfile.ZipFile(output) as archive:
        assert ".env.rag" not in archive.namelist()
        assert "backend/.env" not in archive.namelist()
        assert "data/raw/other.pdf" in archive.namelist()
        assert all(secret.encode() not in archive.read(n) for n in archive.namelist())
        archive.extractall(extracted)
    manifest = json.loads((extracted / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    for name, sha in manifest["files_sha256"].items():
        assert hashlib.sha256((extracted / name).read_bytes()).hexdigest() == sha
    portable = bundle.load(extracted / BUNDLE_DIR)
    review.check(portable)
    assert all(d["source_uri"].startswith("data/raw/") for d in portable.documents)
    assert all((extracted / d["source_uri"]).is_file() for d in portable.documents)
    if any(urlsplit(d["source_uri"]).scheme == "file" for d in b.documents):
        assert portable.manifest_sha != b.manifest_sha
    else:
        # Re-exporting a package already using relative paths is idempotent.
        assert portable.manifest_sha == b.manifest_sha
    assert (root / BUNDLE_DIR / "documents.csv").read_bytes() == before
    assert manifest["raw_pdf_count"] == 2
    with pytest.raises(ValueError, match="overwrite"):
        export(root, output)


def test_configure_preserves_existing_settings_and_generates_password(tmp_path):
    template = "EMBEDDING_API_KEY=\nEMBEDDING_BASE_URL=\nNEO4J_PASSWORD=\n"
    (tmp_path / ".env.rag.example").write_text(template)
    assert "EMBEDDING_API_KEY" in configure(tmp_path)
    first = (tmp_path / ".env.rag").read_text()
    assert "NEO4J_PASSWORD=\n" not in first
    configure(tmp_path)
    assert (tmp_path / ".env.rag").read_text() == first
