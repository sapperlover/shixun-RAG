"""Turn retrieved evidence into generation facts without inventing graph edges."""

from __future__ import annotations

from app.core.config import get_settings
from app.domain import FactRecord
from app.rag import RAGResult
from app.schemas.qa import Citation


def build(result: RAGResult) -> list[FactRecord]:
    cfg = get_settings().evidence
    facts: list[FactRecord] = []
    by_relation: dict[str, list] = {}
    for source in result.evidence:
        if source.relation_id:
            by_relation.setdefault(source.relation_id, []).append(source)

    def append(source, path_id, subject, predicate, object_name):
        facts.append(
            FactRecord(
                fact_id=f"fact-{len(facts) + 1}",
                path_id=path_id,
                relation_id=source.relation_id,
                subject=subject,
                predicate=predicate,
                object=object_name,
                citation=Citation(
                    citation_id=source.citation_id,
                    relation_id=source.relation_id,
                    chunk_id=source.chunk_id,
                    doc_id=source.doc_id,
                    doc_version=source.doc_version,
                    section=source.section,
                    page=source.page_start,
                    excerpt=source.text[: cfg.excerpt_chars],
                    doc_title=source.doc_title,
                ),
            )
        )

    if result.retrieval_type == "document":
        used = 0
        for source in result.evidence:
            cost = min(len(source.text), cfg.excerpt_chars)
            if facts and used + cost > cfg.token_budget:
                break
            append(source, None, source.doc_title, "SOURCE", source.section or "原文")
            used += cost
        return facts

    used = 0
    for path in result.paths:
        sources = [s for edge in path.edges for s in by_relation.get(edge.relation_id, [])]
        cost = sum(min(len(s.text), cfg.excerpt_chars) for s in sources)
        if facts and used + cost > cfg.token_budget:
            break
        if any(not by_relation.get(edge.relation_id) for edge in path.edges):
            continue
        names = {n.node_id: n.name for n in path.nodes}
        for edge in path.edges:
            for source in by_relation[edge.relation_id]:
                append(source, path.path_id, names[edge.from_], edge.type, names[edge.to])
        used += cost
    return facts
