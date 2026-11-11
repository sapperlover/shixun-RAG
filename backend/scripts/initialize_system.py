"""Initialize the complete API-based system; verify sources and reuse portable vectors."""

from __future__ import annotations

import argparse
import hashlib
import json

from dotenv import load_dotenv

from app.core.config import REPO_ROOT, get_env
from app.core.errors import ServiceUnavailable
from app.graph import build, publish, validate
from app.ingest import bundle, review
from app.llm import chat_api
from app.storage import document_corpus, faiss_store, neo4j_client, snapshot, sqlite


def initialize(*, rebuild_embeddings: bool = False) -> dict:
    load_dotenv(REPO_ROOT / ".env")
    get_env.cache_clear()
    env = get_env()
    missing = [
        key
        for key in (
            "embedding_api_key",
            "embedding_base_url",
            "embedding_model",
            "embedding_dimensions",
        )
        if not getattr(env, key)
    ]
    if missing:
        raise ValueError("Fill .env fields: " + ", ".join(k.upper() for k in missing))
    chat_api.configuration()
    source = REPO_ROOT / "data/corpus/all-documents-v3"
    manifest, _ = document_corpus.load_source(source)
    raw = (REPO_ROOT / "data/raw").resolve()
    for document in manifest["documents"]:
        pdf = (raw / document["source_file"]).resolve()
        if not pdf.is_relative_to(raw) or not pdf.is_file():
            raise ValueError("Missing source PDF: " + document["source_file"])
        if hashlib.sha256(pdf.read_bytes()).hexdigest() != document["source_sha256"]:
            raise ValueError("Source PDF checksum mismatch: " + document["source_file"])
    sqlite.migrate()
    neo4j_client.ping()
    neo4j_client.apply_constraints()
    graph_source = REPO_ROOT / "data/kb/cs2024-reviewed"
    knowledge = bundle.load(graph_source)
    review.check(knowledge)
    # Prefer a ready local index after an explicit API rebuild. The original
    # portable archive may still belong to the previous workspace endpoint.
    # build() validates the archive only when it actually needs to import it.
    documents = document_corpus.build(source, reuse_portable=not rebuild_embeddings)
    graph_batch = None
    try:
        current = snapshot.get_active()
        with sqlite.connect() as conn:
            old = conn.execute(
                "SELECT source_manifest_sha FROM build_batches WHERE batch_id=?", (current,)
            ).fetchone()
        if old and old[0] == knowledge.manifest_sha and faiss_store.status(current) == "ready":
            graph_batch = current
    except ServiceUnavailable:
        pass
    if graph_batch is None:
        graph_batch = build.build_staging(graph_source)
        checks = validate.validate(graph_batch, REPO_ROOT / "data/eval/questions_v1.jsonl")
        if not checks["ok"] or faiss_store.status(graph_batch) != "ready":
            if checks["ok"]:
                build.mark_failed(
                    graph_batch, {"stage": "initialize", "reason": "entity_vectors_unavailable"}
                )
            raise ValueError("Graph/index initialization failed; check embedding API configuration")
        publish.publish(graph_batch)
    return {
        "state": "ready",
        "graph_batch": graph_batch,
        "document_corpus": documents,
        "model_runtime": "remote_api",
        "original_pdfs": len(manifest["documents"]),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild-embeddings",
        action="store_true",
        help="Explicitly build vectors for a different embedding model/endpoint",
    )
    args = parser.parse_args()
    try:
        print(
            json.dumps(initialize(rebuild_embeddings=args.rebuild_embeddings), ensure_ascii=False)
        )
    finally:
        neo4j_client.close()
