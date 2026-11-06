"""路径 → 可核验事实（V1.2 §4.3）。

输入：排序后的路径、knowledge_batch。
输出：FactRecord 列表：路径上每条边对应一条事实和一个 Citation。
Citation 的原文摘录一律从 SQLite chunks 表按本次 batch 读出，不由模型生成。
证据预算：按路径顺序累加摘录长度，超过 evidence.token_budget 时不再加入后续路径（第一条路径总是保留）。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.domain import CandidatePath, FactRecord
from app.schemas.qa import Citation
from app.storage import evidence


def build(paths: list[CandidatePath], batch_id: str) -> list[FactRecord]:
    cfg = get_settings().evidence
    rows = evidence.best_evidence(batch_id, (e.relation_id for c in paths for e in c.path.edges))

    facts: list[FactRecord] = []
    used = 0
    seen_cits: set[str] = set()
    for cp in paths:
        names = {n.node_id: n.name for n in cp.path.nodes}
        path_facts: list[FactRecord] = []
        cost = 0
        for e in cp.path.edges:
            r = rows.get(e.relation_id)
            if r is None:  # path_check 已保证可读回；出现即为数据不一致，放弃整条路径
                path_facts = []
                break
            excerpt = r["text"][: cfg.excerpt_chars]
            if r["citation_id"] not in seen_cits:
                cost += len(excerpt)
            path_facts.append(
                FactRecord(
                    fact_id=f"fact-{len(facts) + len(path_facts) + 1}",
                    path_id=cp.path.path_id,
                    relation_id=e.relation_id,
                    subject=names[e.from_],
                    predicate=e.type,
                    object=names[e.to],
                    citation=Citation(
                        citation_id=r["citation_id"],
                        relation_id=e.relation_id,
                        chunk_id=r["chunk_id"],
                        doc_id=r["doc_id"],
                        doc_version=r["doc_version"],
                        section=r["section"],
                        page=r["page_start"],
                        excerpt=excerpt,
                    ),
                )
            )
        if not path_facts:
            continue
        if facts and used + cost > cfg.token_budget:
            break
        used += cost
        seen_cits.update(f.citation.citation_id for f in path_facts)
        facts.extend(path_facts)
    return facts
