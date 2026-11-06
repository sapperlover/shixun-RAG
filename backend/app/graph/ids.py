"""确定性 ID 规则（V1.2 附录 A.1/A.2）。★ 冻结契约：入库、预核验 CSV、评测金标准都依赖这些规则。"""

from __future__ import annotations

import hashlib

from app.schemas.qa import Scope


def node_key(batch_id: str, entity_id: str) -> str:
    return f"{batch_id}:{entity_id}"


def scope_key(scope: Scope | None) -> str:
    """规范化的适用范围字符串；无范围时为空串。"""
    if scope is None:
        return ""
    parts = []
    if scope.major_code:
        parts.append(f"major={scope.major_code}")
    if scope.entry_year:
        parts.append(f"year={scope.entry_year}")
    return ";".join(parts)


def relation_id(
    batch_id: str, from_entity: str, rel_type: str, to_entity: str, scope: Scope | None = None
) -> str:
    """relation_id = 由 batch_id + 起点 + 类型 + 终点 + scope 确定性生成。"""
    raw = "|".join([batch_id, from_entity, rel_type, to_entity, scope_key(scope)])
    return "rel-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def chunk_id(doc_id: str, doc_version: str, text_sha256: str) -> str:
    """同一文档版本内，内容相同的块 ID 相同 → 增量重建时可按哈希比对。"""
    raw = f"{doc_id}|{doc_version}|{text_sha256}"
    return "chunk-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
