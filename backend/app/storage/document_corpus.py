"""Versioned source excerpts, keyword index and full-document FAISS retrieval."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from functools import lru_cache
from pathlib import Path

from app.core.config import get_env
from app.llm import embedder
from app.storage import sqlite


def tokens(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text.lower())
    out = re.findall(r"[a-z]+|\d+(?:\.\d+)?", compact)
    for segment in re.findall(r"[\u3400-\u9fff]+", compact):
        out.extend(segment[i : i + 2] for i in range(len(segment) - 1))
    return out


def load_source(root: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    data = (root / "chunks.jsonl").read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["chunks_sha256"]:
        raise ValueError("Prepared corpus checksum mismatch")
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != manifest["chunk_count"] or len({r["chunk_id"] for r in rows}) != len(rows):
        raise ValueError("Corpus count or IDs invalid")
    for r in rows:
        if hashlib.sha256(r["text"].encode()).hexdigest() != r["text_sha256"]:
            raise ValueError("Corpus source text changed without updating its hash")
    return manifest, rows


def identity() -> dict:
    return embedder.identity()


def portable_vectors(source: Path, manifest: dict, rows: list[dict]):
    """Accept only a checksum-bound archive for exactly this source and model."""
    import numpy as np

    metadata = source / "embeddings.json"
    if not metadata.exists():
        return {}
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    archive = source / "embeddings.npz"
    expected_ids = [r["chunk_id"] for r in rows]
    if (
        meta["identity"] != identity()
        or meta["source_sha256"] != manifest["chunks_sha256"]
        or meta["chunk_ids"] != expected_ids
        or meta["sha256"] != hashlib.sha256(archive.read_bytes()).hexdigest()
    ):
        raise ValueError("Portable embeddings mismatch; rebuild explicitly for the selected model")
    with np.load(archive, allow_pickle=False) as data:
        vectors = data["vectors"]
    if (
        vectors.ndim != 2
        or vectors.shape != (len(rows), meta["dimensions"])
        or not np.isfinite(vectors).all()
        or (np.abs(np.linalg.norm(vectors, axis=1) - 1) > 0.01).any()
        or (
            identity()["configured_dimensions"] is not None
            and vectors.shape[1] != identity()["configured_dimensions"]
        )
    ):
        raise ValueError("Invalid portable embedding vectors")
    return dict(zip((embedding_text(r) for r in rows), vectors, strict=True))


def export_vectors(source: Path) -> dict:
    """Create portable numeric data from a ready, matching active source batch."""
    import faiss
    import numpy as np

    manifest, source_rows = load_source(source)
    eligible = [r for r in source_rows if not r.get("needs_review") and not r.get("is_toc")]
    batch = active()
    if not batch or status(batch) != "ready":
        raise ValueError("No compatible ready document batch to export")
    with sqlite.connect() as conn:
        stored = conn.execute(
            "SELECT manifest_sha FROM document_batches WHERE batch_id=?", (batch,)
        ).fetchone()
    meta = json.loads((index_dir(batch) / "index.json").read_text(encoding="utf-8"))
    if (
        not stored
        or stored[0] != manifest["chunks_sha256"]
        or meta.get("chunk_ids") != [r["chunk_id"] for r in eligible]
    ):
        raise ValueError("Active document batch does not match portable source")
    index = faiss.read_index(str(index_dir(batch) / "index.faiss"))
    archive = source / "embeddings.npz"
    temporary = source / "embeddings.tmp.npz"
    np.savez_compressed(temporary, vectors=index.reconstruct_n(0, index.ntotal))
    temporary.replace(archive)
    result = dict(
        identity=identity(),
        source_sha256=manifest["chunks_sha256"],
        chunk_ids=meta["chunk_ids"],
        dimensions=index.d,
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    metadata = source / "embeddings.tmp.json"
    metadata.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata.replace(source / "embeddings.json")
    portable_vectors(source, manifest, eligible)
    return {"vectors": index.ntotal, "dimensions": index.d, "sha256": result["sha256"]}


def embedding_text(row: dict) -> str:
    return re.sub(
        r"\s+",
        " ",
        f"{row['title']} {row.get('program_title') or ''} {row.get('section') or ''}\n{row['text']}",
    ).strip()


def index_dir(batch: str) -> Path:
    return Path(get_env().document_index_dir) / batch


def active() -> str | None:
    with sqlite.connect() as conn:
        row = conn.execute("SELECT batch_id FROM document_active WHERE singleton=1").fetchone()
    return row[0] if row else None


def status(batch: str) -> str:
    try:
        directory = index_dir(batch)
        meta = json.loads((directory / "index.json").read_text(encoding="utf-8"))
        if meta["identity"] != identity():
            return "embedding configuration mismatch"
        if hashlib.sha256((directory / "index.faiss").read_bytes()).hexdigest() != meta["sha256"]:
            return "index checksum mismatch"
        return "ready"
    except (OSError, ValueError, KeyError):
        return "not built"


def build(source: Path, *, reuse_portable: bool = True) -> dict:
    """Build immutable staging data; publish after both keyword and vector data exist."""
    import faiss
    import numpy as np

    manifest, rows = load_source(source)
    sha = manifest["chunks_sha256"]
    current = active()
    previous_vectors = {}
    if current:
        with sqlite.connect() as conn:
            old = conn.execute(
                "SELECT manifest_sha FROM document_batches WHERE batch_id=?", (current,)
            ).fetchone()
        old_meta = (
            json.loads((index_dir(current) / "index.json").read_text(encoding="utf-8"))
            if status(current) == "ready"
            else {}
        )
        if (
            old
            and old[0] == sha
            and status(current) == "ready"
            and old_meta.get("layout_version") == 2
        ):
            return {"batch": current, "reused": True, "chunks": len(rows)}
        if status(current) == "ready":
            old_index = faiss.read_index(str(index_dir(current) / "index.faiss"))
            old_rows = _rows(get_env().sqlite_path, current)
            by_id = {r["chunk_id"]: r for r in old_rows}
            old_order = old_meta.get("chunk_ids", [r["chunk_id"] for r in old_rows])
            if old_index.ntotal == len(old_order):
                previous_vectors = {
                    embedding_text(by_id[cid]): old_index.reconstruct(i)
                    for i, cid in enumerate(old_order)
                }
    vector_rows = [r for r in rows if not r.get("needs_review") and not r.get("is_toc")]
    if reuse_portable:
        previous_vectors.update(portable_vectors(source, manifest, vector_rows))
    batch = "documents-" + sha[:10] + "-" + uuid.uuid4().hex[:6]
    directory = index_dir(batch)
    directory.mkdir(parents=True, exist_ok=True)
    cache_id = (
        hashlib.sha256(json.dumps(identity(), sort_keys=True).encode()).hexdigest()[:16]
        + "-eligible-v2"
    )
    cache = Path(get_env().document_index_dir) / "cache" / sha / cache_id
    cache.mkdir(parents=True, exist_ok=True)
    with sqlite.connect() as conn:
        conn.execute(
            "INSERT INTO document_batches(batch_id,manifest_sha,state) VALUES (?,?,'staging')",
            (batch, sha),
        )
    try:
        matrices = []
        for start in range(0, len(vector_rows), 50):
            part = vector_rows[start : start + 50]
            cached = cache / f"{start:05d}.npy"
            if cached.exists():
                matrix = np.load(cached, allow_pickle=False)
            else:
                texts = [embedding_text(r) for r in part]
                missing = list(dict.fromkeys(t for t in texts if t not in previous_vectors))
                if missing:
                    fresh = embedder.embed(missing)
                    previous_vectors.update(zip(missing, fresh, strict=True))
                matrix = np.asarray([previous_vectors[t] for t in texts], dtype="float32")
                np.save(cached, matrix, allow_pickle=False)
            if (
                matrix.ndim != 2
                or matrix.shape[0] != len(part)
                or (
                    identity()["configured_dimensions"] is not None
                    and matrix.shape[1] != identity()["configured_dimensions"]
                )
                or not np.isfinite(matrix).all()
                or (np.abs(np.linalg.norm(matrix, axis=1) - 1) > 0.01).any()
            ):
                raise ValueError("Invalid cached document vectors; remove the affected cache file")
            matrices.append(matrix)
            print(
                json.dumps({"embedding_chunks_done": start + len(part), "total": len(vector_rows)}),
                flush=True,
            )
        vectors = np.concatenate(matrices).astype("float32")
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        faiss.write_index(index, str(directory / "index.faiss"))
        meta = {
            "identity": identity(),
            "dimensions": index.d,
            "count": index.ntotal,
            "layout_version": 2,
            "chunk_ids": [r["chunk_id"] for r in vector_rows],
            "sha256": hashlib.sha256((directory / "index.faiss").read_bytes()).hexdigest(),
        }
        (directory / "index.json").write_text(json.dumps(meta), encoding="utf-8")
        with sqlite.connect() as conn:
            for r in rows:
                payload = json.dumps(r, ensure_ascii=False)
                conn.execute(
                    "INSERT INTO document_chunks VALUES (?,?,?,?)",
                    (batch, r["chunk_id"], r["doc_id"], payload),
                )
                words = " ".join(tokens(r["text"] + " " + (r.get("section") or "")))
                conn.execute(
                    "INSERT INTO document_fts VALUES (?,?,?)", (batch, r["chunk_id"], words)
                )
            conn.execute("UPDATE document_batches SET state='retired' WHERE state='active'")
            conn.execute(
                "UPDATE document_batches SET state='active',index_identity=? WHERE batch_id=?",
                (json.dumps(identity()), batch),
            )
            conn.execute(
                "INSERT INTO document_active VALUES (1,?) "
                "ON CONFLICT(singleton) DO UPDATE SET batch_id=excluded.batch_id",
                (batch,),
            )
        return {
            "batch": batch,
            "reused": False,
            "chunks": len(rows),
            "embedded_chunks": len(vector_rows),
            "dimensions": index.d,
        }
    except Exception:
        with sqlite.connect() as conn:
            conn.execute("UPDATE document_batches SET state='failed' WHERE batch_id=?", (batch,))
        raise


@lru_cache(maxsize=4)
def _rows(db: str, batch: str) -> list[dict]:
    with sqlite.connect(db) as conn:
        rows = conn.execute(
            "SELECT payload FROM document_chunks WHERE batch_id=? ORDER BY rowid", (batch,)
        ).fetchall()
    return [json.loads(r[0]) for r in rows]


def rows(batch: str) -> list[dict]:
    return _rows(get_env().sqlite_path, batch)


def by_citation(batch: str, citation_id: str) -> dict | None:
    for row in rows(batch):
        expected = (
            "doc-cit-" + hashlib.sha256(f"{batch}|{row['chunk_id']}".encode()).hexdigest()[:16]
        )
        if expected != citation_id or row.get("needs_review") or row.get("is_toc"):
            continue
        return {
            "citation_id": citation_id,
            "relation_id": None,
            "chunk_id": row["chunk_id"],
            "doc_id": row["doc_id"],
            "doc_title": row["title"],
            "doc_version": row["doc_version"],
            "section": row.get("section"),
            "page_start": row["page_start"],
            "page_end": row["page_end"],
            "text": row["text"],
            "verification_status": row["verification_status"],
        }
    return None


def keyword(batch: str, question: str) -> list[str]:
    words = list(dict.fromkeys(tokens(question)))[:80]
    if not words:
        return []
    match = " OR ".join('"' + word.replace('"', '""') + '"' for word in words)
    with sqlite.connect() as conn:
        result = conn.execute(
            "SELECT chunk_id FROM document_fts WHERE document_fts MATCH ? AND batch_id=? "
            "ORDER BY bm25(document_fts) LIMIT 2000",
            (match, batch),
        ).fetchall()
    return [r[0] for r in result]


def vector(batch: str, question: str) -> list[tuple[str, float]]:
    import faiss

    if status(batch) != "ready":
        raise ValueError("Document vector index unavailable or model identity changed")
    index = faiss.read_index(str(index_dir(batch) / "index.faiss"))
    source = rows(batch)
    meta = json.loads((index_dir(batch) / "index.json").read_text(encoding="utf-8"))
    chunk_ids = meta.get("chunk_ids", [r["chunk_id"] for r in source])
    q = embedder.embed([question])
    if q.shape[1] != index.d or len(chunk_ids) != index.ntotal:
        raise ValueError("Document vector dimensions or count mismatch")
    scores, positions = index.search(q, index.ntotal)
    return [
        (chunk_ids[i], float(s)) for s, i in zip(scores[0], positions[0], strict=True) if i >= 0
    ]
