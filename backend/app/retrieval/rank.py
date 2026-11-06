"""路径排序（V1.2 §4.2）。

优先级：目标链与问题语义、适用范围的匹配程度 ＞ 逐边来源（通过 path_check 后均完整）＞ 路径长度。
具体排序键：问题提及实体的命中数（多者优先）→ 显式体现 scope 的节点数（多者优先）→ 跳数（少者优先）→ 稳定序。
被更靠前路径完全包含的子路径丢弃。返回前 top_k_paths 条，重新编号为 p-1、p-2…（对外的 path_id）。
证据长度预算在 facts.build 中执行。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.domain import CandidatePath, Intent


def rank(paths: list[CandidatePath], intent: Intent) -> list[CandidatePath]:
    mentions = set(intent.mentions)
    s = intent.scope

    def key(c: CandidatePath):
        hits = sum(n.node_id in mentions for n in c.path.nodes)
        scope_hits = sum(
            (n.label == "Professional" and n.node_id == f"major:{s.major_code}")
            or (
                n.label == "ProgramPlan"
                and s.entry_year is not None
                and c.node_props.get(n.node_id, {}).get("entry_year") == s.entry_year
            )
            for n in c.path.nodes
        )
        signature = "|".join(e.relation_id for e in c.path.edges)
        return (-hits, -scope_hits, c.path.hop_count, signature)

    ranked: list[CandidatePath] = []
    for c in sorted(paths, key=key):
        edges = {e.relation_id for e in c.path.edges}
        # 被更靠前路径完全包含的子路径（如 T2 中的 T1 段）不再单独给出，避免模型只引用其中一段
        if any(edges <= {e.relation_id for e in r.path.edges} for r in ranked):
            continue
        ranked.append(c)
        if len(ranked) == get_settings().retrieval.top_k_paths:
            break
    for i, c in enumerate(ranked, start=1):
        c.path = c.path.model_copy(update={"path_id": f"p-{i}"})
        c.score = float(len(ranked) - i + 1)
    return ranked
