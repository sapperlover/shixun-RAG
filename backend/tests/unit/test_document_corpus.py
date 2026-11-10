import hashlib
import json

import numpy as np
import pytest

from app.core.config import get_env
from app.rag import RAGEvidence, RAGResult
from app.retrieval.documents import parse_scope, retrieve_documents
from app.storage import document_corpus, sqlite
from scripts.prepare_all_documents import _heading


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "sources.db"))
    monkeypatch.setenv("DOCUMENT_INDEX_DIR", str(tmp_path / "indexes"))
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "128")
    get_env.cache_clear()
    sqlite.migrate()
    records = []
    for i, (kind, year, text, pending) in enumerate(
        [
            ("curriculum", 2024, "软件工程专业专业课程最低选修12学分。", False),
            ("curriculum", 2025, "软件工程专业专业课程最低选修14学分。", False),
            ("institution", None, "缓考须在考试前提出申请，经过批准后方可缓考。", False),
            ("institution", None, "某个未核验的绩点公式。", True),
            ("curriculum", 2023, "每月进行宿舍卫生检查，参加劳动教育。", False),
        ]
    ):
        records.append(
            dict(
                chunk_id=f"test-{i}",
                doc_id="assessment-rules" if kind == "institution" else f"source-{i}",
                doc_version="v1",
                title="模拟来源",
                source_file="test.pdf",
                source_sha256="a" * 64,
                book_year=year,
                page_start=1,
                page_end=1,
                section="第一条",
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                kind=kind,
                entry_year=year,
                major="软件工程" if year else None,
                program_variant="regular" if year else None,
                plan_revision=str(year),
                needs_review=pending,
                verification_status="ocr_unreviewed" if pending else "source_text_extracted",
                source_kind="ocr" if pending else "native_text",
                scope_note="模拟数据，不是真实制度",
            )
        )
    source = tmp_path / "prepared"
    source.mkdir()
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    (source / "chunks.jsonl").write_bytes(data.encode("utf-8"))
    (source / "manifest.json").write_text(
        json.dumps(
            dict(chunk_count=len(records), chunks_sha256=hashlib.sha256(data.encode()).hexdigest())
        ),
        encoding="utf-8",
    )

    def embedding(texts):
        matrix = np.zeros((len(texts), 128), dtype="float32")
        for i, text in enumerate(texts):
            for t in document_corpus.tokens(text):
                column = int(hashlib.sha256(t.encode()).hexdigest()[:6], 16) % 128
                matrix[i, column] += 1
            matrix[i] /= np.linalg.norm(matrix[i])
        return matrix

    monkeypatch.setattr(document_corpus.embedder, "embed", embedding)
    result = document_corpus.build(source)
    yield source, result
    get_env.cache_clear()


def test_scope_infers_clear_year_and_major_and_rejects_conflicting_context():
    s, missing, institutional = parse_scope("软件工程2025级专业课程最低学分", {})
    assert s.major_code == "软件工程" and s.entry_year == 2025 and not missing and not institutional
    _, missing, _ = parse_scope("软件工程2025级专业课程最低学分", {"entry_year": 2024})
    assert "entry_year" in missing
    _, missing, institutional = parse_scope("缓考应该如何申请？", {})
    assert not missing and institutional


def test_direct_retrieval_keeps_years_separate(corpus):
    result = retrieve_documents("软件工程2025级专业课程最低选修学分？", {}, "source-query")
    assert result.status == "success" and result.retrieval_type == "document"
    assert not result.paths
    assert all(e.entry_year == 2025 for e in result.evidence)
    assert "14学分" in result.evidence[0].text
    assert all(e.relation_id is None and not e.scope_verified for e in result.evidence)


def test_rules_do_not_require_major_and_unreviewed_ocr_is_not_returned(corpus):
    result = retrieve_documents("缓考须如何提出申请？", {}, "rule-query")
    assert result.status == "success" and all(
        e.doc_id == "assessment-rules" for e in result.evidence
    )
    assert not any(e.needs_review for e in result.evidence)
    result = retrieve_documents("未核验的绩点公式是什么？", {}, "pending-query")
    assert result.status == "insufficient"


def test_document_keyword_degradation_and_idempotent_build(corpus, monkeypatch):
    source, initial = corpus
    second = document_corpus.build(source)
    assert second["reused"] and second["batch"] == initial["batch"]
    monkeypatch.setattr(
        document_corpus, "vector", lambda *args: (_ for _ in ()).throw(ValueError("offline"))
    )
    result = retrieve_documents("缓考应该如何申请？", {}, "keywords")
    assert result.status == "success" and result.degraded_mode
    assert result.retrieval_mode == "keyword_only"
    unrelated = retrieve_documents("学生宿舍空调电费每度多少钱？", {}, "unsupported")
    assert unrelated.status == "insufficient"  # Only the incidental word 宿舍 appears in source.


def test_failed_new_index_retains_active_corpus(corpus, monkeypatch):
    source, initial = corpus
    data = (source / "chunks.jsonl").read_text(encoding="utf-8").replace("14学分", "16学分")
    rows = [json.loads(line) for line in data.splitlines()]
    for r in rows:
        r["text_sha256"] = hashlib.sha256(r["text"].encode()).hexdigest()
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    (source / "chunks.jsonl").write_bytes(data.encode("utf-8"))
    (source / "manifest.json").write_text(
        json.dumps(
            dict(chunk_count=len(rows), chunks_sha256=hashlib.sha256(data.encode()).hexdigest())
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        document_corpus.embedder,
        "embed",
        lambda texts: (_ for _ in ()).throw(ValueError("API down")),
    )
    with pytest.raises(ValueError, match="API down"):
        document_corpus.build(source)
    assert document_corpus.active() == initial["batch"]


def test_graph_and_document_success_have_distinct_invariants():
    item = RAGEvidence(
        citation_id="c",
        chunk_id="k",
        doc_id="d",
        doc_version="v",
        doc_title="t",
        page_start=1,
        page_end=1,
        section=None,
        text="source",
    )
    with pytest.raises(ValueError, match="graph success"):
        RAGResult(request_id="r", status="success", knowledge_batch="b", evidence=[item])
    direct = RAGResult(
        request_id="r",
        status="success",
        knowledge_batch="b",
        retrieval_type="document",
        evidence=[item],
    )
    assert not direct.paths


def test_portable_vectors_rebuild_without_embedding_calls(corpus, monkeypatch, tmp_path):
    source, initial = corpus
    exported = document_corpus.export_vectors(source)
    assert exported["vectors"] == 4
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "target.db"))
    monkeypatch.setenv("DOCUMENT_INDEX_DIR", str(tmp_path / "target-indexes"))
    get_env.cache_clear()
    sqlite.migrate()
    monkeypatch.setattr(
        document_corpus.embedder,
        "embed",
        lambda _: (_ for _ in ()).throw(AssertionError("Unexpected paid API call")),
    )
    rebuilt = document_corpus.build(source)
    assert rebuilt["embedded_chunks"] == 4 and rebuilt["batch"] != initial["batch"]
    assert document_corpus.status(rebuilt["batch"]) == "ready"
    # Corrupt archives fail before any call or active-pointer change.
    (source / "embeddings.npz").write_bytes(b"corrupt")
    manifest, rows = document_corpus.load_source(source)
    with pytest.raises(ValueError, match="Portable embeddings mismatch"):
        document_corpus.portable_vectors(
            source, manifest, [r for r in rows if not r["needs_review"]]
        )
    assert document_corpus.active() == rebuilt["batch"]


def test_cached_vector_dimension_change_cannot_publish(corpus, monkeypatch, tmp_path):
    source, _ = corpus
    cache = list((tmp_path / "indexes/cache").rglob("*.npy"))
    assert len(cache) == 1
    # Same count and valid unit vectors, but a different dimension.
    wrong = np.zeros((4, 64), dtype="float32")
    wrong[:, 0] = 1
    np.save(cache[0], wrong, allow_pickle=False)
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "fresh.db"))
    get_env.cache_clear()
    sqlite.migrate()
    with pytest.raises(ValueError, match="Invalid cached document vectors"):
        document_corpus.build(source)
    assert document_corpus.active() is None


def test_printed_old_revision_is_not_the_book_year():
    result = _heading("计算机科学与技术专业留学生培养方案（2021年版）\n一、专业定位\n正文")
    assert result["printed_revision"] == "2021" and result["program_variant"] == "international"
    assert _heading("目录\n软件工程专业培养方案................20") is None
    assert _heading("目录\n软件工程专业培养方案........20\n一、专业定位.....20") is None
