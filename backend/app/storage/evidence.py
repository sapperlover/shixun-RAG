"""证据读取（SQLite）：回答前的逐边复核、事实构建、原文读回都走这里。

只有 verification_status=verified、原文块属于本批次、文档 access_level=public 的证据才算“可读回”。
TODO(BE, D4)：登录后按角色放开 restricted 文档。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.storage import sqlite

_READABLE = (
    "FROM relation_evidence e "
    "JOIN chunks c ON c.batch_id = e.batch_id AND c.chunk_id = e.chunk_id "
    "JOIN documents d ON d.doc_id = c.doc_id AND d.doc_version = c.doc_version "
    "WHERE e.batch_id = ? AND e.verification_status = 'verified' AND d.access_level = 'public' "
)
_COLUMNS = (
    "SELECT e.citation_id, e.relation_id, e.chunk_id, e.verification_status, c.doc_id, "
    "c.doc_version, c.section, c.page_start, c.page_end, c.text, d.title AS doc_title "
)


def readable_relations(batch: str, relation_ids: Iterable[str]) -> set[str]:
    rids = list(set(relation_ids))
    if not rids:
        return set()
    marks = ",".join("?" * len(rids))
    with sqlite.connect() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT e.relation_id {_READABLE} AND e.relation_id IN ({marks})",
            (batch, *rids),
        ).fetchall()
    return {r["relation_id"] for r in rows}


def best_evidence(batch: str, relation_ids: Iterable[str]) -> dict[str, dict]:
    """每条关系取一条可读回证据（按 chunk_id 稳定排序取第一条）。"""
    rids = list(set(relation_ids))
    if not rids:
        return {}
    marks = ",".join("?" * len(rids))
    with sqlite.connect() as conn:
        rows = conn.execute(
            f"{_COLUMNS} {_READABLE} AND e.relation_id IN ({marks}) ORDER BY e.relation_id, e.chunk_id",
            (batch, *rids),
        ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["relation_id"], dict(r))
    return out


def by_citation(batch: str, citation_id: str) -> dict | None:
    with sqlite.connect() as conn:
        row = conn.execute(
            f"{_COLUMNS} {_READABLE} AND e.citation_id = ?", (batch, citation_id)
        ).fetchone()
    return dict(row) if row else None
