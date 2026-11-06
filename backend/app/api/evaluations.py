"""评测接口（系统管理员）。命令行入口：python -m scripts.run_eval。

TODO(QA/BE, D5)：POST /evaluations/run 用 BackgroundTasks 调用 eval.runner，结果写 eval_runs/eval_results。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.errors import ApiError, ErrorCode
from app.core.security import Role, require_roles
from app.schemas.common import Page
from app.schemas.resources import EvalRunIn, EvalRunOut

router = APIRouter(tags=["evaluations"])
_admin = Depends(require_roles(Role.SYSTEM_ADMIN))


@router.get("/evaluations", response_model=Page[EvalRunOut], dependencies=[_admin])
def list_runs(
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
) -> Page[EvalRunOut]:
    return Page[EvalRunOut](items=[], total=0, limit=limit, offset=offset)


@router.post("/evaluations/run", status_code=202, dependencies=[_admin])
def start_run(body: EvalRunIn) -> EvalRunOut:
    raise ApiError(501, ErrorCode.NOT_IMPLEMENTED, "评测接口将在 D5 实现，当前请用 make eval")


@router.get("/evaluations/{run_id}", response_model=EvalRunOut, dependencies=[_admin])
def get_run(run_id: str) -> EvalRunOut:
    raise ApiError(404, ErrorCode.NOT_FOUND, f"评测 {run_id} 不存在")
