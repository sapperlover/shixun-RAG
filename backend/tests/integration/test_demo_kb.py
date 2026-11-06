"""集成测试：在真实 Neo4j 上构建【模拟】演示知识包，跑通完整问答链路。

运行：make test-int（需要 Neo4j 在线；Ollama 可选，不可用时验证模板降级）。
测试使用独立的临时 SQLite，并在结束时删除自己构建的图谱批次，不影响正在运行的服务。
"""

from pathlib import Path

import pytest

from app import pipeline
from app.core.errors import ErrorCode, ServiceUnavailable
from app.eval import dataset, runner
from app.graph import build, dictionary, publish, validate
from app.llm import ollama_client
from app.schemas.qa import QARequest
from app.storage import sqlite

pytestmark = pytest.mark.integration
DEMO = Path(__file__).parents[3] / "data" / "demo"
QUESTIONS = {q.question_id: q for q in dataset.load(DEMO / "questions_demo.jsonl")}


@pytest.fixture(scope="module")
def batch():
    sqlite.migrate()
    b = build.build_staging(DEMO)
    report = validate.validate(b, DEMO / "questions_demo.jsonl")
    assert report["ok"], report
    publish.publish(b)
    dictionary.load.cache_clear()
    yield b
    build.drop_graph(b)


def ask(qid: str):
    q = QUESTIONS[qid]
    return pipeline.answer_question(QARequest(question=q.question, scope=q.scope), f"req-{qid}")


def test_t2_three_hop_success(batch):
    res = ask("demo-t2-001")
    r = res.response
    assert r.status == "success", r.error
    assert r.knowledge_batch == batch and r.paths[0].hop_count == 3
    assert runner.is_path_hit(QUESTIONS["demo-t2-001"], r)
    assert all(c.citation_id.startswith("cit-") for c in r.citations)
    # 2023 级方案在第 1 跳被年级过滤，并记入跳级日志
    assert res.hop_log[0].pruned.get("scope_mismatch", 0) >= 1


def test_t1_two_hop_success(batch):
    r = ask("demo-t1-001").response
    assert r.status == "success", r.error
    assert r.paths[0].hop_count == 2 and runner.is_path_hit(QUESTIONS["demo-t1-001"], r)


def test_t3_prerequisite_chain_reverse(batch):
    r = ask("demo-t3-001").response
    assert r.status == "success", r.error
    assert runner.is_path_hit(QUESTIONS["demo-t3-001"], r)


def test_needs_context(batch):
    r = ask("demo-neg-001").response
    assert r.status == "needs_context" and r.missing_fields == ["entry_year"]


def test_unverified_relation_is_refused_with_hop(batch):
    r = ask("demo-neg-002").response
    assert r.status == "insufficient"
    assert r.error.code == ErrorCode.EVIDENCE_UNVERIFIED and r.error.failed_hop == 2
    assert r.claims == []


def test_unknown_entity_is_anchor_not_found(batch):
    req = QARequest(
        question="火星殖民课程有哪些？", scope={"major_code": "NOPE", "entry_year": 2024}
    )
    r = pipeline.answer_question(req, "req-x").response
    assert r.status == "insufficient" and r.error.code == ErrorCode.ANCHOR_NOT_FOUND


def test_llm_down_falls_back_to_template(batch, monkeypatch):
    def down(*a, **k):
        raise ServiceUnavailable(ErrorCode.LLM_UNAVAILABLE)

    monkeypatch.setattr(ollama_client, "chat_json", down)
    r = ask("demo-t2-001").response
    assert r.status == "success" and r.answer_mode == "template" and r.degraded_mode
    assert "llm_unavailable" in r.degradation_reason


def test_evidence_readback_via_api(batch, client):
    r = ask("demo-t2-001").response
    cit = r.citations[0]
    got = client.get(f"/evidence/{cit.citation_id}", params={"knowledge_batch": batch})
    assert got.status_code == 200
    assert got.json()["text"].startswith(cit.excerpt[:20])
    other = client.get(f"/evidence/{cit.citation_id}", params={"knowledge_batch": "batch-other"})
    assert other.status_code == 404  # 按批次隔离


def test_eval_runner_on_demo(batch, tmp_path, monkeypatch):
    """检索与评测流程本身：用模板生成使结果确定。模型的真实答题质量由 make eval 的报告反映。"""

    def down(*a, **k):
        raise ServiceUnavailable(ErrorCode.LLM_UNAVAILABLE)

    monkeypatch.setattr(ollama_client, "chat_json", down)
    _, m = runner.run(list(QUESTIONS.values()), tmp_path)
    assert m.path_hit_rate == 1.0 and m.answer_accuracy == 1.0
    assert m.citation_coverage == 1.0
