"""One initialization command after installing dependencies and configuring the embedding API.

Run from backend/: python -m scripts.initialize_rag [--start-db]
No parsing, OCR, manual CSV editing or database-copying is required on the target computer.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
from pathlib import Path

from dotenv import load_dotenv, set_key

from app.core.config import REPO_ROOT, get_env
from app.core.errors import ServiceUnavailable
from app.graph import build, publish, validate
from app.ingest import bundle, review
from app.storage import document_corpus, faiss_store, neo4j_client, snapshot, sqlite
from scripts.configure_rag import configure


def initialize(root: Path, *, start_db: bool = False) -> dict:
    missing = configure(root)
    if missing:
        raise ValueError("Fill these fields in .env.rag first: " + ", ".join(missing))
    load_dotenv(root / ".env.rag")
    get_env.cache_clear()
    corpus_source = root / "data/corpus/all-documents-v3"
    corpus_manifest, _ = document_corpus.load_source(corpus_source)
    for document in corpus_manifest["documents"]:
        source_pdf = (root / "data/raw" / document["source_file"]).resolve()
        if not source_pdf.is_relative_to((root / "data/raw").resolve()):
            raise ValueError("Source path leaves data/raw")
        if hashlib.sha256(source_pdf.read_bytes()).hexdigest() != document["source_sha256"]:
            raise ValueError("Prepared corpus and source PDF do not match")
    if start_db:
        docker_config = root / ".cache/docker"
        docker_config.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "docker",
                "--config",
                str(docker_config),
                "compose",
                "--env-file",
                str(root / ".env.rag"),
                "-f",
                str(root / "docker-compose.rag.yml"),
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "120",
                "neo4j",
            ],
            check=True,
        )
    sqlite.migrate()
    neo4j_client.ping()
    neo4j_client.apply_constraints()
    source = root / "data/kb/cs2024-reviewed"
    graph_source = bundle.load(source)
    review.check(graph_source)
    graph_batch = None
    try:
        current = snapshot.get_active()
        with sqlite.connect() as conn:
            old = conn.execute(
                "SELECT source_manifest_sha FROM build_batches WHERE batch_id=?", (current,)
            ).fetchone()
        if old and old[0] == graph_source.manifest_sha and faiss_store.status(current) == "ready":
            graph_batch = current
    except ServiceUnavailable:
        pass
    if graph_batch is None:
        graph_batch = build.build_staging(source)
        checks = validate.validate(graph_batch)
        if not checks["ok"] or faiss_store.status(graph_batch) != "ready":
            raise ValueError(
                "Graph batch or vector index is not ready; previous active batch retained"
            )
        publish.publish(graph_batch)
    documents = document_corpus.build(corpus_source)
    portable = document_corpus.export_vectors(corpus_source)
    set_key(str(root / ".env.rag"), "DOCUMENT_RETRIEVAL_ENABLED", "true", quote_mode="never")
    import os

    os.environ["DOCUMENT_RETRIEVAL_ENABLED"] = "true"
    get_env.cache_clear()
    return {
        "state": "ready",
        "graph_batch": graph_batch,
        "document_corpus": documents,
        "portable_vectors": portable,
        "query_api_health_checked": False,
        "checked_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "model": get_env().embedding_model,
        "dimensions": get_env().embedding_dimensions,
        "interface": "app.rag.retrieve",
        "generator_started": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-db", action="store_true", help="Start only the Neo4j Docker service and wait"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = initialize(REPO_ROOT, start_db=args.start_db)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        neo4j_client.close()
