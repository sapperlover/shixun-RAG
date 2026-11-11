import json
from pathlib import Path

import pytest

from app import fixtures, pipeline
from app.core.config import get_env, get_settings
from app.eval import report, service
from app.llm import chat_api
from app.storage import sqlite


@pytest.fixture
def evaluation(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "evaluation.db"))
    get_env.cache_clear()
    settings = get_settings().model_copy(deep=True)
    settings.eval.runs_dir = str(tmp_path / "runs")
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_api, "configuration", lambda: ("https://test.invalid/v1", {}))
    sqlite.migrate()
    with sqlite.connect() as conn:
        conn.execute(
            "INSERT INTO build_batches(batch_id,state,source_manifest_sha) VALUES ('test','active','x')"
        )
        conn.execute(
            "INSERT INTO active_snapshot(project_key,active_version) VALUES ('campus-graphrag','test')"
        )
    yield settings
    get_env.cache_clear()


def test_frozen_evaluation_persists_per_question_and_blocks_duplicates(evaluation, monkeypatch):
    sha, qs = service.frozen_dataset()
    assert len(qs) == 10 and {q.hop_count for q in qs} == {2, 3}
    run_id = service.create_run(sha)
    with pytest.raises(RuntimeError, match="already running"):
        service.create_run(sha)
    monkeypatch.setattr(
        pipeline,
        "answer_question",
        lambda req, rid: pipeline.PipelineResult(
            fixtures.load_mock("needs_context").model_copy(update={"request_id": rid})
        ),
    )
    service.execute(run_id)
    with sqlite.connect() as conn:
        row = conn.execute("SELECT * FROM eval_runs WHERE run_id=?", (run_id,)).fetchone()
        records = conn.execute(
            "SELECT detail_json FROM eval_results WHERE run_id=?", (run_id,)
        ).fetchall()
    assert service.to_output(row).status == "finished" and len(records) == 13
    assert json.loads(records[0][0])["question"]
    text = report.to_markdown(Path(evaluation.eval.runs_dir) / run_id)
    assert "逐题结果" in text and "P95" in text and qs[0].question in text


def test_dataset_change_fails_before_any_model_call(evaluation, monkeypatch):
    sha, questions = service.frozen_dataset()
    run_id = service.create_run(sha)
    monkeypatch.setattr(service, "frozen_dataset", lambda: ("changed", questions))
    monkeypatch.setattr(pipeline, "answer_question", lambda *a: pytest.fail("Unexpected API call"))
    service.execute(run_id)
    with sqlite.connect() as conn:
        row = conn.execute("SELECT * FROM eval_runs WHERE run_id=?", (run_id,)).fetchone()
    assert service.to_output(row).status == "failed"


def test_interrupted_evaluation_can_be_run_again(evaluation):
    sha, _ = service.frozen_dataset()
    previous = service.create_run(sha)
    service.recover_interrupted()
    assert service.create_run(sha) != previous


def test_evaluation_endpoints_expose_dataset_and_require_admin(evaluation, client):
    assert client.get("/evaluations/dataset").json()["questions"] == 10
    assert client.get("/evaluations").status_code == 200
    sha, _ = service.frozen_dataset()
    assert client.post("/evaluations/run", json={"dataset_sha256": sha}).status_code == 403
    assert client.get("/evaluations/unknown").status_code == 404
