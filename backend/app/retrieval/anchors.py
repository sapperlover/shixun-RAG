"""锚点匹配（V1.2 §4.2：解析 anchors；实体词典 + 可选 FAISS）。

输入：Intent、knowledge_batch。
输出：Anchor 列表（字面命中 > scope 推出 > 向量召回，按分数降序）。

来源：
1. 字面：问题中出现的实体名称/别名（最长匹配优先），match=exact/alias，score=1；
2. scope：major_code + entry_year 唯一确定的培养方案，match=scope；
3. 向量：没有任何字面命中时，用 FAISS 召回 top-k（≥ vector_anchor_min_score），match=vector。
除 scope 外的命中实体同时作为“问题语义约束”（Intent.mentions），由 path_check 使用。
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.domain import Anchor, Intent
from app.graph import dictionary
from app.storage import faiss_store

log = logging.getLogger(__name__)


def match(intent: Intent, batch_id: str) -> list[Anchor]:
    return match_with_diagnostics(intent, batch_id)[0]


def match_with_diagnostics(intent: Intent, batch_id: str) -> tuple[list[Anchor], str | None]:
    """Also report a failed vector request; an existing index is not proof of API health."""
    cfg = get_settings().retrieval
    vector_failure = None
    d = dictionary.load(batch_id)
    out: dict[str, Anchor] = {}

    for ref, surface in d.find_mentions(intent.question, cfg.min_surface_chars):
        kind = "exact" if dictionary.normalize(ref.name) == surface else "alias"
        out[ref.entity_id] = Anchor(ref.entity_id, ref.label, ref.name, 1.0, kind)

    s = intent.scope
    if s.major_code and s.entry_year:
        for ref in d.entities.values():
            if (
                ref.label == "ProgramPlan"
                and ref.props.get("major_id") == f"major:{s.major_code}"
                and ref.props.get("entry_year") == s.entry_year
            ):
                out.setdefault(
                    ref.entity_id, Anchor(ref.entity_id, ref.label, ref.name, 1.0, "scope")
                )

    if cfg.vector_enabled and not any(a.match in ("exact", "alias") for a in out.values()):
        try:
            hits = faiss_store.search(batch_id, intent.question, cfg.vector_anchor_top_k)
        except Exception as exc:  # 向量不可用只影响召回，不影响图检索
            log.info("向量锚点不可用: %s", exc)
            vector_failure = "vector_query_unavailable"
            hits = []
        for eid, label, score in hits:
            if score >= cfg.vector_anchor_min_score and eid in d.entities:
                out.setdefault(eid, Anchor(eid, label, d.entities[eid].name, score, "vector"))

    order = {"exact": 0, "alias": 0, "scope": 1, "vector": 2}
    return sorted(
        out.values(), key=lambda a: (order[a.match], -a.score, a.entity_id)
    ), vector_failure
