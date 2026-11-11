import json

from app import fixtures, pipeline, rag
from app.answer import generate, retrieved_facts, validate_claims
from app.core.errors import ErrorCode, ServiceUnavailable
from app.domain import DraftClaim
from app.llm import chat_api
from app.schemas.qa import QARequest


def document_result():
    return rag.RAGResult(
        request_id="req-document",
        status="success",
        retrieval_type="document",
        knowledge_batch="documents-test",
        retrieval_mode="hybrid",
        evidence=[
            rag.RAGEvidence(
                citation_id="doc-cit-1",
                chunk_id="k1",
                doc_id="assessment-rules",
                doc_version="v1",
                doc_title="考核规定",
                page_start=5,
                page_end=5,
                section="缓考",
                text="缓考须在考试前提出申请，经过批准后方可缓考。",
            )
        ],
    )


def test_document_answer_has_readable_citation_and_no_graph_path(monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda *a: document_result())
    monkeypatch.setattr(
        chat_api,
        "chat_json",
        lambda *a: json.dumps(
            {"claims": [{"text": "缓考须在考试前申请并获得批准。", "citation_ids": ["doc-cit-1"]}]},
            ensure_ascii=False,
        ),
    )
    response = pipeline.answer_question(QARequest(question="缓考如何申请？"), "req-test").response
    assert response.status == "success" and response.answer_mode == "llm"
    assert response.retrieval_type == "document" and not response.paths
    assert response.claims[0].path_ids == []
    assert response.citations[0].relation_id is None


def test_invalid_model_citations_and_numbers_trigger_visible_fallback(monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda *a: document_result())
    monkeypatch.setattr(
        chat_api,
        "chat_json",
        lambda *a: json.dumps(
            {"claims": [{"text": "必须提前99天申请。", "citation_ids": ["doc-cit-1"]}]}
        ),
    )
    response = pipeline.answer_question(
        QARequest(question="缓考如何申请？"), "req-invalid"
    ).response
    assert response.answer_mode == "template" and response.degraded_mode
    assert response.degradation_reason == "llm_invalid" and "99" not in response.answer


def test_api_failure_preserves_source_and_marks_degradation(monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda *a: document_result())

    def down(*args):
        raise ServiceUnavailable(ErrorCode.LLM_UNAVAILABLE)

    monkeypatch.setattr(chat_api, "chat_json", down)
    response = pipeline.answer_question(QARequest(question="缓考如何申请？"), "req-down").response
    assert response.status == "success" and response.answer_mode == "template"
    assert response.degradation_reason == "llm_unavailable"
    assert "考试前" in response.answer and response.citations


def test_graph_answer_requires_every_path_edge_citation():
    response = fixtures.success()
    sources = [
        rag.RAGEvidence(
            citation_id=c.citation_id,
            relation_id=c.relation_id,
            chunk_id=c.chunk_id,
            doc_id=c.doc_id,
            doc_version=c.doc_version,
            doc_title="模拟",
            page_start=c.page,
            page_end=c.page,
            section=c.section,
            text=c.excerpt,
        )
        for c in response.citations
    ]
    result = rag.RAGResult(
        request_id="r",
        status="success",
        knowledge_batch="b",
        paths=response.paths,
        evidence=sources,
    )
    facts = retrieved_facts.build(result)
    missing_edge = DraftClaim("c", "结论", [response.paths[0].path_id], [sources[0].citation_id])
    assert not validate_claims.validate([missing_edge], facts).ok
    assert generate.parse_claims('{"claims": "bad"}', facts) == []
    assert (
        generate.parse_claims('{"claims": [{"text": null, "citation_ids": ["cit-1"]}]}', facts)
        == []
    )
