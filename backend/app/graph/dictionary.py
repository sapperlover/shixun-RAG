"""批次实体词典：用于问题中的实体字面匹配。批次发布后不可变，因此按 batch_id 缓存。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.storage import neo4j_client

_TAG = re.compile(r"【[^】]*】")  # 去掉“【模拟】”等标注再做匹配


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", _TAG.sub("", text or "")).lower()


@dataclass(frozen=True)
class EntityRef:
    entity_id: str
    label: str
    name: str
    props: dict = field(default_factory=dict, hash=False, compare=False)


@dataclass
class Dictionary:
    entities: dict[str, EntityRef]
    surfaces: dict[str, set[str]]  # 规范化后的名称/别名 → entity_id 集合

    def find_mentions(self, question: str, min_chars: int) -> list[tuple[EntityRef, str]]:
        """问题中出现的实体（最长匹配优先：被更长的命中完全覆盖的短命中丢弃）。"""
        q = normalize(question)
        hits: list[tuple[int, int, str]] = []
        for surface in self.surfaces:
            if len(surface) < min_chars:
                continue
            start = q.find(surface)
            while start != -1:
                hits.append((start, start + len(surface), surface))
                start = q.find(surface, start + 1)
        hits.sort(key=lambda h: (-(h[1] - h[0]), h[0]))
        taken: list[tuple[int, int]] = []
        out: list[tuple[EntityRef, str]] = []
        seen: set[str] = set()
        for s, e, surface in hits:
            if any(s >= ts and e <= te for ts, te in taken):
                continue
            taken.append((s, e))
            for eid in sorted(self.surfaces[surface]):
                if eid not in seen:
                    seen.add(eid)
                    out.append((self.entities[eid], surface))
        return out


@lru_cache(maxsize=4)
def load(batch: str) -> Dictionary:
    rows = neo4j_client.run_read(
        "MATCH (n {batch_id: $b}) "
        "RETURN n.entity_id AS id, labels(n)[0] AS label, n.name AS name, "
        "coalesce(n.aliases, []) AS aliases, properties(n) AS props",
        b=batch,
    )
    entities: dict[str, EntityRef] = {}
    surfaces: dict[str, set[str]] = {}
    for r in rows:
        entities[r["id"]] = EntityRef(r["id"], r["label"], r["name"], r["props"])
        for text in {r["name"], *r["aliases"]}:
            key = normalize(text)
            if key:
                surfaces.setdefault(key, set()).add(r["id"])
    return Dictionary(entities, surfaces)
