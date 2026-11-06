from pathlib import Path

import pytest

from app import fixtures, pipeline
from app.eval import dataset, metrics, runner

DEMO = Path(__file__).parents[3] / "data" / "demo" / "questions_demo.jsonl"


def test_demo_questions_match_contract():
    qs = dataset.load(DEMO)
    assert {q.expected_status for q in qs} == {"success", "needs_context", "insufficient"}


def test_freeze_check_rejects_modified_file():
    with pytest.raises(ValueError):
        dataset.load(DEMO, expected_sha256="0" * 64)


def test_path_hit_ignores_edge_order():
    q = dataset.load(DEMO)[0]
    mock = fixtures.load_mock("success")
    gold = [(e.from_, e.type, e.to) for e in q.gold_relation_path]
    edges = [
        mock.paths[0].edges[0].model_copy(update={"from_": a, "type": t, "to": b})
        for a, t, b in reversed(gold)
    ]
    resp = mock.model_copy(update={"paths": [mock.paths[0].model_copy(update={"edges": edges})]})
    assert runner.is_path_hit(q, resp)


def test_runner_writes_records(tmp_path, monkeypatch):
    def fake(req, rid):
        return pipeline.PipelineResult(
            fixtures.load_mock("needs_context").model_copy(update={"request_id": rid})
        )

    monkeypatch.setattr(pipeline, "answer_question", fake)
    qs = [q for q in dataset.load(DEMO) if q.expected_status == "needs_context"]
    run_id, m = runner.run(qs, tmp_path)
    assert m.answer_accuracy == 1.0 and m.citation_coverage is None
    assert (tmp_path / run_id / "records.jsonl").exists()


def test_metrics_na_when_no_claims():
    assert metrics.compute([]).citation_coverage is None
