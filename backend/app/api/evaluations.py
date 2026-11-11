"""Start evaluations and inspect persisted, source-grounded results."""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import PlainTextResponse

from app.core.config import REPO_ROOT, get_settings
from app.core.errors import ApiError, ErrorCode, ServiceUnavailable
from app.core.security import Role, require_roles
from app.eval import report, service
from app.llm import chat_api
from app.schemas.common import Page
from app.schemas.resources import EvalRunIn, EvalRunOut
from app.storage import snapshot, sqlite

router = APIRouter(tags=["evaluations"])


@router.get("/evaluations/dataset")
def dataset_info():
    sha, questions = service.frozen_dataset()
    ready, message = True, ""
    try:
        chat_api.configuration()
        snapshot.get_active()
    except ServiceUnavailable:
        ready, message = False, "请先填写模型 API 配置并完成知识库初始化。"
    return {
        "sha256": sha,
        "questions": len(questions),
        "two_hop": sum(q.hop_count == 2 for q in questions),
        "three_hop": sum(q.hop_count == 3 for q in questions),
        "ready_to_run": ready,
        "setup_message": message,
        "scoring_note": "AI-authored source-grounded development set; answer scoring is automatic and needs review",
    }


@router.get("/evaluations", response_model=Page[EvalRunOut])
def list_runs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    with sqlite.connect() as conn:
        total = conn.execute("SELECT count(*) FROM eval_runs").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM eval_runs ORDER BY created_at DESC,run_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return Page[EvalRunOut](
        items=[service.to_output(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/evaluations/run", status_code=202, dependencies=[Depends(require_roles(Role.SYSTEM_ADMIN))]
)
def start_run(body: EvalRunIn, background: BackgroundTasks):
    try:
        run_id = service.create_run(body.dataset_sha256)
    except ValueError as exc:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, str(exc)) from None
    except RuntimeError as exc:
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, str(exc)) from None
    except ServiceUnavailable:
        raise ApiError(
            503, ErrorCode.NO_ACTIVE_BATCH, "请先填写模型 API 配置并完成知识库初始化"
        ) from None
    background.add_task(service.execute, run_id)
    return get_run(run_id)


@router.get("/evaluations/{run_id}", response_model=EvalRunOut)
def get_run(run_id: str):
    with sqlite.connect() as conn:
        row = conn.execute("SELECT * FROM eval_runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Evaluation not found")
    return service.to_output(row)


@router.get("/evaluations/{run_id}/results")
def results(run_id: str):
    get_run(run_id)
    with sqlite.connect() as conn:
        rows = conn.execute(
            "SELECT detail_json FROM eval_results WHERE run_id=? ORDER BY question_id", (run_id,)
        ).fetchall()
    return {"items": [json.loads(r[0]) for r in rows]}


@router.get("/evaluations/{run_id}/report", response_class=PlainTextResponse)
def markdown_report(run_id: str):
    run = get_run(run_id)
    if run.status != "finished":
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Evaluation not finished")
    # run_id must exist in SQLite before it is used as an artifact path.
    directory = (REPO_ROOT / get_settings().eval.runs_dir / run_id).resolve()
    if not directory.is_relative_to((REPO_ROOT / get_settings().eval.runs_dir).resolve()):
        raise ApiError(404, ErrorCode.NOT_FOUND, "Invalid evaluation path")
    return report.to_markdown(directory)
