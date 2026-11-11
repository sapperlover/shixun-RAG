from pathlib import Path

import pytest

from app import rag
from app.core.config import get_env
from app.core.errors import ErrorCode, ServiceUnavailable
from app.graph import build, dictionary, ids
from app.ingest import bundle
from app.retrieval import expand
from app.schemas.qa import Scope
from app.storage import faiss_store, snapshot, sqlite

DEMO = Path(__file__).parents[3] / "data/demo"


@pytest.fixture
def graph(tmp_path, monkeypatch):
    """Real parsing/traversal/guards/ranking and SQLite; only Neo4j I/O is replaced."""
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "rag.db"))
    get_env.cache_clear()
    sqlite.migrate()
    b = bundle.load(DEMO)
    with sqlite.connect() as conn:
        conn.execute(
            "INSERT INTO build_batches (batch_id,state,source_manifest_sha) VALUES ('b','validated','test')"
        )
    build._write_metadata("b", b)
    snapshot.switch_active("b")
    refs = {
        e.entity_id: dictionary.EntityRef(
            e.entity_id, e.label, e.name, {**e.props, "batch_id": "b"}
        )
        for e in b.entities
    }
    surfaces = {}
    for e in b.entities:
        for name in [e.name, *e.aliases]:
            surfaces.setdefault(dictionary.normalize(name), set()).add(e.entity_id)
    monkeypatch.setattr(dictionary, "load", lambda batch: dictionary.Dictionary(refs, surfaces))
    monkeypatch.setattr(faiss_store, "status", lambda batch: "not built")
    monkeypatch.setattr(
        faiss_store, "search", lambda *a: (_ for _ in ()).throw(ValueError("API unavailable"))
    )

    def query(hop, keys, batch):
        out = []
        for r in b.relations:
            if (
                r["type"] != hop.type
                or r["from_label"] != hop.stored[0]
                or r["to_label"] != hop.stored[1]
                or r["verification_status"] == "rejected"
            ):
                continue
            a, z = r["from_entity_id"], r["to_entity_id"]
            start, end = (a, z) if hop.traverse == "forward" else (z, a)
            if ids.node_key(batch, start) in keys:
                out.append(
                    dict(
                        from_key=ids.node_key(batch, start),
                        id=end,
                        name=refs[end].name,
                        props=refs[end].props,
                        rid=build._relation_id(batch, r),
                        s=a,
                        e=z,
                        verified=r["verification_status"] == "verified",
                        ev=bundle.split_ids(r["evidence_chunk_ids"]),
                        r_major=r["major_code"],
                        r_year=int(r["entry_year"]) if r["entry_year"] else None,
                        r_batch=batch,
                    )
                )
        return out

    monkeypatch.setattr(expand, "_query", query)
    yield refs
    get_env.cache_clear()


def test_success_returns_full_sources_no_generation(graph, monkeypatch):
    from app.llm import chat_api

    monkeypatch.setattr(chat_api, "chat_json", lambda *a: pytest.fail("No generation permitted"))
    result = rag.retrieve(
        "计算机科学与技术专业2024级的专业选修课跨院系怎么认定？",
        Scope(major_code="DEMO01", entry_year=2024),
        "req-success",
    )
    assert result.status == "success", result
    assert result.paths[0].hop_count == 3
    assert result.degraded_mode and result.retrieval_mode == "graph_only"
    assert {e.relation_id for p in result.paths for e in p.edges} <= {
        s.relation_id for s in result.evidence
    }
    assert all(s.page_start and s.text for s in result.evidence)
    assert "answer" not in result.model_dump()


def test_two_hop_and_reverse_prerequisites(graph):
    result = rag.retrieve(
        "2024级专业选修课跨院系怎么认定？", {"major_code": "DEMO01", "entry_year": 2024}, "req-two"
    )
    assert result.status == "success" and result.paths[0].hop_count == 2
    result = rag.retrieve("学操作系统之前需要先修哪些课？", {}, "req-prereq")
    assert result.status == "success" and result.paths[0].hop_count == 2


def test_needs_context_no_infrastructure(monkeypatch):
    monkeypatch.setattr(snapshot, "get_active", lambda: pytest.fail("Not needed before scope"))
    result = rag.retrieve("专业选修课怎么认定？", {}, "req-context")
    assert result.status == "needs_context" and result.missing_fields == ["entry_year"]


def test_no_major_code_needed(graph, monkeypatch):
    seen = []
    monkeypatch.setattr(
        rag.anchors,
        "match_with_diagnostics",
        lambda intent, batch: (seen.append(intent.scope.major_code) or [], None),
    )
    rag.retrieve("专业选修课怎么认定？", {"entry_year": 2024}, "req-default")
    assert seen == ["计算机科学与技术"]


def test_unverified_and_cross_year_no_success(graph):
    r = rag.retrieve(
        "2024级通识选修课修读要求？", {"major_code": "DEMO01", "entry_year": 2024}, "req-unverified"
    )
    assert r.status == "insufficient" and r.error.code == ErrorCode.EVIDENCE_UNVERIFIED
    assert not r.paths and not r.evidence
    r = rag.retrieve(
        "专业选修课跨院系怎么认定？", {"major_code": "DEMO01", "entry_year": 2025}, "req-year"
    )
    assert r.status == "insufficient"


def test_unreadable_source_is_not_success(graph):
    with sqlite.connect() as conn:
        conn.execute("UPDATE relation_evidence SET verification_status='unverified'")
    r = rag.retrieve(
        "2024级专业选修课怎么认定？", {"major_code": "DEMO01", "entry_year": 2024}, "req-source"
    )
    assert r.status == "insufficient" and r.error.code == ErrorCode.EVIDENCE_UNVERIFIED


def test_vector_runtime_failure_reported_with_existing_index(graph, monkeypatch):
    monkeypatch.setattr(faiss_store, "status", lambda batch: "ready")
    r = rag.retrieve(
        "完全没有对应实体的问句", {"major_code": "DEMO01", "entry_year": 2024}, "req-vector"
    )
    assert r.retrieval_mode == "graph_only" and r.degraded_mode
    assert r.degradation_reason == "vector_query_unavailable"


def test_graph_failure_and_batch_pin(graph, monkeypatch):
    reads = []
    monkeypatch.setattr(snapshot, "get_active", lambda: reads.append(1) or "b")

    def unavailable(*args):
        raise ServiceUnavailable(ErrorCode.GRAPH_UNAVAILABLE)

    monkeypatch.setattr(expand, "_query", unavailable)
    r = rag.retrieve(
        "专业选修课怎么认定？", {"major_code": "DEMO01", "entry_year": 2024}, "req-down"
    )
    assert r.status == "error" and r.error.code == ErrorCode.GRAPH_UNAVAILABLE
    assert r.knowledge_batch == "b" and len(reads) == 1


def test_input_validation():
    with pytest.raises(ValueError):
        rag.retrieve("", {}, "r")
    with pytest.raises(ValueError):
        rag.retrieve("问题", {}, " ")
