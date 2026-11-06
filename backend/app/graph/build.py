"""构建 staging 批次（V1.2 §4.1、附录 B.2）。输入是知识包（app.ingest.bundle），不在 active 批次上原地修改。

步骤：
1. 校验知识包（bundle.load）；
2. SQLite：build_batches(state=staging)、documents、chunks、relation_evidence（带 citation_id）；
3. Neo4j：按标签批量 MERGE 节点（node_key = batch_id:entity_id），MERGE 关系（relation_id 含 batch_id）；
   rejected 的关系不进图谱；unverified 的关系进图谱但 verified=false，检索时被剪掉并记入跳级日志；
4. 向量索引：为本批次实体名称构建独立 FAISS 索引；不可用时记录原因，检索降级为 graph_only。
任何一步失败：批次标为 failed，已写入的图谱数据删除。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from app.graph import ids
from app.ingest import bundle as bundle_mod
from app.storage import faiss_store, neo4j_client, sqlite

log = logging.getLogger(__name__)


def new_batch_id() -> str:
    return f"batch-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def build_staging(bundle_dir: str | Path) -> str:
    b = bundle_mod.load(Path(bundle_dir))
    batch = new_batch_id()
    with sqlite.connect() as conn:
        conn.execute(
            "INSERT INTO build_batches (batch_id, state, source_manifest_sha) VALUES (?, 'staging', ?)",
            (batch, b.manifest_sha),
        )
    try:
        stats = _write_metadata(batch, b)
        stats.update(_write_graph(batch, b))
        stats["faiss"] = _build_vectors(batch, b)
        with sqlite.connect() as conn:
            conn.execute(
                "UPDATE build_batches SET graph_node_count = ?, graph_edge_count = ?,"
                " faiss_index_sha = ?, build_stats_json = ? WHERE batch_id = ?",
                (
                    stats["nodes"],
                    stats["edges"],
                    stats["faiss"].get("sha"),
                    json.dumps(stats, ensure_ascii=False),
                    batch,
                ),
            )
        log.info("批次 %s 构建完成: %s", batch, stats)
        return batch
    except Exception as exc:
        mark_failed(batch, {"stage": "build", "error": str(exc)})
        raise


def mark_failed(batch: str, error: dict) -> None:
    try:
        drop_graph(batch)
    except Exception as exc:  # 图谱不可用时仍要把状态写成 failed
        log.error("清理批次 %s 图谱失败: %s", batch, exc)
    with sqlite.connect() as conn:
        conn.execute(
            "UPDATE build_batches SET state = 'failed', error_json = ? WHERE batch_id = ?",
            (json.dumps(error, ensure_ascii=False), batch),
        )


def drop_graph(batch: str) -> int:
    """删除某批次的全部节点和关系（失败批次清理 / retired 批次回收）。"""
    with neo4j_client.get_driver().session() as s:
        rec = s.run(
            "MATCH (n {batch_id: $b}) DETACH DELETE n RETURN count(n) AS n", b=batch
        ).single()
    return rec["n"] if rec else 0


def _write_metadata(batch: str, b: bundle_mod.Bundle) -> dict:
    with sqlite.connect() as conn:
        for d in b.documents:
            conn.execute(
                "INSERT INTO documents (doc_id, doc_version, title, source_uri, authorization_note,"
                " file_sha256, access_level, publish_state, college_code, major_code, entry_year,"
                " change_note) VALUES (?,?,?,?,?,?,?,'published',?,?,?,?)"
                " ON CONFLICT(doc_id, doc_version) DO NOTHING",
                (
                    d["doc_id"],
                    d["doc_version"],
                    d["title"],
                    d["source_uri"],
                    d["authorization_note"],
                    d["file_sha256"],
                    d["access_level"],
                    d["college_code"] or None,
                    d["major_code"] or None,
                    int(d["entry_year"]) if d["entry_year"] else None,
                    d["notes"] or None,
                ),
            )
        for c in b.chunks:
            conn.execute(
                "INSERT INTO chunks (batch_id, chunk_id, doc_id, doc_version, page_start, page_end,"
                " section, text, text_sha256) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    batch,
                    c["chunk_id"],
                    c["doc_id"],
                    c["doc_version"],
                    c.get("page_start"),
                    c.get("page_end"),
                    c.get("section"),
                    c["text"],
                    _sha(c["text"]),
                ),
            )
        n_ev = 0
        for r in b.relations:
            rid = _relation_id(batch, r)
            for chunk in bundle_mod.split_ids(r["evidence_chunk_ids"]):
                conn.execute(
                    "INSERT INTO relation_evidence (batch_id, relation_id, chunk_id, citation_id,"
                    " verification_status, verified_by, verified_at, note) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        batch,
                        rid,
                        chunk,
                        ids.citation_id(batch, rid, chunk),
                        r["verification_status"],
                        r["verified_by"] or None,
                        r["verified_at"] or None,
                        r["note"] or None,
                    ),
                )
                n_ev += 1
    return {"documents": len(b.documents), "chunks": len(b.chunks), "evidence_rows": n_ev}


def _write_graph(batch: str, b: bundle_mod.Bundle) -> dict:
    by_label: dict[str, list[dict]] = {}
    for e in b.entities:
        by_label.setdefault(e.label, []).append(
            {
                "node_key": ids.node_key(batch, e.entity_id),
                "props": {
                    **e.props,
                    "entity_id": e.entity_id,
                    "name": e.name,
                    "aliases": e.aliases,
                    "batch_id": batch,
                },
            }
        )
    by_type: dict[tuple[str, str, str], list[dict]] = {}
    skipped = 0
    for r in b.relations:
        if r["verification_status"] == "rejected":
            skipped += 1
            continue
        key = (r["type"], r["from_label"], r["to_label"])
        by_type.setdefault(key, []).append(
            {
                "from_key": ids.node_key(batch, r["from_entity_id"]),
                "to_key": ids.node_key(batch, r["to_entity_id"]),
                "props": {
                    "relation_id": _relation_id(batch, r),
                    "batch_id": batch,
                    "verified": r["verification_status"] == "verified",
                    "evidence_chunk_ids": bundle_mod.split_ids(r["evidence_chunk_ids"]),
                    "major_code": r["major_code"] or None,
                    "entry_year": int(r["entry_year"]) if r["entry_year"] else None,
                    "confidence": float(r["confidence"]) if r["confidence"] else None,
                },
            }
        )

    nodes = edges = 0
    with neo4j_client.get_driver().session() as s:
        # 标签与关系类型已由 bundle.load 按白名单校验，可安全拼入 Cypher
        for label, rows in by_label.items():
            s.run(
                f"UNWIND $rows AS row MERGE (n:{label} {{node_key: row.node_key}}) SET n += row.props",
                rows=rows,
            ).consume()
            nodes += len(rows)
        for (rtype, la, lb), rows in by_type.items():
            rec = s.run(
                f"UNWIND $rows AS row "
                f"MATCH (a:{la} {{node_key: row.from_key}}), (b:{lb} {{node_key: row.to_key}}) "
                f"MERGE (a)-[r:{rtype} {{relation_id: row.props.relation_id}}]->(b) "
                f"SET r += row.props RETURN count(r) AS n",
                rows=rows,
            ).single()
            written = rec["n"] if rec else 0
            if written != len(rows):
                raise RuntimeError(f"{rtype} 应写入 {len(rows)} 条，实际 {written} 条")
            edges += written
    return {"nodes": nodes, "edges": edges, "rejected_relations": skipped}


def _build_vectors(batch: str, b: bundle_mod.Bundle) -> dict:
    items = [(e.entity_id, e.label, n) for e in b.entities for n in {e.name, *e.aliases}]
    try:
        sha = faiss_store.build(batch, items)
        return {"status": "ready", "sha": sha, "items": len(items)}
    except Exception as exc:
        log.warning("批次 %s 向量索引未构建，检索将降级为 graph_only: %s", batch, exc)
        return {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}


def _relation_id(batch: str, r: dict) -> str:
    scope = ids.scope_from(r["major_code"], r["entry_year"])
    return ids.relation_id(batch, r["from_entity_id"], r["type"], r["to_entity_id"], scope)


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
