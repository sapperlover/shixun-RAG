"""Persisted evaluation jobs shared by the browser and command line."""

from __future__ import annotations

import json
import logging
import time
import uuid

from app.core.config import REPO_ROOT, get_env, get_settings
from app.eval import dataset, runner
from app.llm import chat_api
from app.schemas.resources import EvalMetrics, EvalRunOut
from app.storage import snapshot, sqlite

log = logging.getLogger(__name__)


def frozen_dataset():
    cfg = get_settings().eval
    path = REPO_ROOT / cfg.dataset_file
    sha_path = REPO_ROOT / cfg.dataset_sha256_file
    sha = sha_path.read_text(encoding="utf-8").split()[0]
    questions = dataset.load(path, sha)
    if len(questions) < 10 or not all(any(q.hop_count == h for q in questions) for h in (2, 3)):
        raise ValueError("Evaluation requires at least ten reviewed 2/3-hop questions")
    return sha, questions


def create_run(expected_sha: str) -> str:
    sha, _ = frozen_dataset()
    if expected_sha != sha:
        raise ValueError("Dataset checksum mismatch")
    chat_api.configuration()
    snapshot.get_active()
    cfg, env = get_settings(), get_env()
    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    with sqlite.connect(immediate=True) as conn:
        if conn.execute("SELECT 1 FROM eval_runs WHERE status='running'").fetchone():
            raise RuntimeError("An evaluation is already running")
        active = conn.execute("SELECT active_version FROM active_snapshot LIMIT 1").fetchone()
        conn.execute(
            "INSERT INTO eval_runs(run_id,dataset_sha256,scorer_version,git_commit,batch_id,config_json,status) "
            "VALUES (?,?,?,?,?,?,'running')",
            (
                run_id,
                sha,
                cfg.eval.scorer_version,
                env.git_commit,
                active[0] if active else None,
                json.dumps(
                    {
                        "settings": cfg.model_dump(),
                        "model": env.llm_model,
                        "negative_sha256": dataset.sha256_of(
                            REPO_ROOT / "data/eval/negatives.jsonl"
                        ),
                    },
                    ensure_ascii=False,
                ),
            ),
        )
    return run_id


def execute(run_id: str) -> None:
    try:
        with sqlite.connect() as conn:
            job = conn.execute("SELECT * FROM eval_runs WHERE run_id=?", (run_id,)).fetchone()
        if not job or job["status"] != "running":
            raise ValueError("Evaluation job is not running")
        sha, questions = frozen_dataset()
        config = json.loads(job["config_json"])
        if sha != job["dataset_sha256"]:
            raise ValueError("Evaluation dataset changed after submission")
        questions += dataset.load(
            REPO_ROOT / "data/eval/negatives.jsonl", config["negative_sha256"]
        )
        out = REPO_ROOT / get_settings().eval.runs_dir
        _, metrics = runner.run(questions, out, run_id=run_id)
        records = [
            json.loads(line)
            for line in (out / run_id / "records.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        with sqlite.connect() as conn:
            for row in records:
                conn.execute(
                    "INSERT INTO eval_results(run_id,question_id,request_id,batch_id,status,predicted_path_json,"
                    "path_hit,answer_correct,citation_covered,claims_total,failure_stage,elapsed_ms,detail_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        row["question_id"],
                        row["request_id"],
                        row["batch_id"],
                        row["status"],
                        json.dumps(row["predicted_path"], ensure_ascii=False),
                        row["path_hit"],
                        row["answer_correct"],
                        row["citation_covered"],
                        row["claims_total"],
                        row["failure_stage"],
                        row["elapsed_ms"],
                        json.dumps(row, ensure_ascii=False),
                    ),
                )
            conn.execute(
                "UPDATE eval_runs SET status='finished',metrics_json=?,finished_at=datetime('now') WHERE run_id=?",
                (metrics.model_dump_json(), run_id),
            )
    except Exception as exc:
        log.error("Evaluation %s failed (%s)", run_id, type(exc).__name__)
        with sqlite.connect() as conn:
            conn.execute(
                "UPDATE eval_runs SET status='failed',error_detail=?,finished_at=datetime('now') WHERE run_id=?",
                (f"Evaluation failed ({type(exc).__name__}); check server logs", run_id),
            )


def recover_interrupted() -> None:
    """The single API process cannot resume a background job after a restart."""
    with sqlite.connect() as conn:
        conn.execute(
            "UPDATE eval_runs SET status='failed',error_detail='服务重启中断，请重新运行评测',"
            "finished_at=datetime('now') WHERE status='running'"
        )


def to_output(row) -> EvalRunOut:
    row = dict(row)
    return EvalRunOut(
        **{k: row[k] for k in EvalRunOut.model_fields if k in row and k != "metrics"},
        metrics=EvalMetrics.model_validate_json(row["metrics_json"])
        if row["metrics_json"]
        else None,
    )
