"""Real reviewed sources + Neo4j + portable vectors; API deliberately offline.

This proves source/path/fallback behavior and must not be reported as a live API evaluation.
"""

import json

import pytest

from app import pipeline
from app.core.config import REPO_ROOT, get_env
from app.core.errors import ErrorCode, ServiceUnavailable
from app.eval import dataset, runner
from app.graph import build, publish, validate
from app.llm import embedder
from app.storage import document_corpus, neo4j_client, sqlite

pytestmark = pytest.mark.integration
QUESTIONS = dataset.load(REPO_ROOT / "data/eval/questions_v1.jsonl")
NEGATIVES = dataset.load(REPO_ROOT / "data/eval/negatives.jsonl")


@pytest.fixture(scope="module")
def reviewed_system(tmp_path_factory):
    root = tmp_path_factory.mktemp("reviewed-system")
    source = REPO_ROOT / "data/corpus/all-documents-v3"
    identity = json.loads((source / "embeddings.json").read_text(encoding="utf-8"))["identity"]
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SQLITE_PATH", str(root / "reviewed.db"))
        patch.setenv("FAISS_DIR", str(root / "graph-vectors"))
        patch.setenv("DOCUMENT_INDEX_DIR", str(root / "document-vectors"))
        patch.setenv("DOCUMENT_RETRIEVAL_ENABLED", "true")
        for field, value in identity.items():
            env_key = "EMBEDDING_" + {
                "endpoint": "BASE_URL",
                "configured_dimensions": "DIMENSIONS",
            }.get(field, field.upper())
            patch.setenv(env_key, str(value))
        get_env.cache_clear()

        def down(*args):
            raise ServiceUnavailable(ErrorCode.LLM_UNAVAILABLE)

        patch.setattr(embedder, "embed", down)
        patch.setattr(pipeline.gen_mod.chat_api, "chat_json", down)
        sqlite.migrate()
        neo4j_client.apply_constraints()
        batch = build.build_staging(REPO_ROOT / "data/kb/cs2024-reviewed")
        try:
            checks = validate.validate(batch, REPO_ROOT / "data/eval/questions_v1.jsonl")
            assert checks["ok"], checks
            publish.publish(batch)
            corpus = document_corpus.build(source)
            assert corpus["embedded_chunks"] == 848
            yield batch
        finally:
            build.drop_graph(batch)
    get_env.cache_clear()


@pytest.mark.parametrize("question", QUESTIONS + NEGATIVES, ids=lambda q: q.question_id)
def test_real_reviewed_paths_sources_and_boundary_states(reviewed_system, question):
    from app.schemas.qa import QARequest

    response = pipeline.answer_question(
        QARequest(question=question.question, scope=question.scope),
        "req-reviewed-" + question.question_id,
    ).response
    assert response.status == question.expected_status, response.model_dump()
    assert runner.is_path_hit(question, response)
    assert runner.is_answer_correct(question, response)
    if response.status == "success":
        assert response.answer_mode == "template" and response.degraded_mode
        assert response.paths[0].hop_count == question.hop_count
        assert runner.covered_claims(response) == len(response.claims)


def test_portable_document_query_works_in_visible_keyword_fallback(reviewed_system):
    from app.schemas.qa import QARequest

    response = pipeline.answer_question(
        QARequest(question="申请期末考试缓考需要什么手续？"), "req-rule"
    ).response
    assert response.status == "success" and response.retrieval_type == "document"
    assert not response.paths and response.retrieval_mode == "keyword_only"
    assert runner.covered_claims(response) == len(response.claims)
