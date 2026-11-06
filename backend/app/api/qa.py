"""POST /qa/ask —— 唯一的问答接口（V1.2 附录 C）。"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app import fixtures, pipeline
from app.core.config import get_env
from app.core.errors import ApiError, ErrorCode
from app.retrieval import hop_log
from app.schemas.qa import QARequest, QAResponse
from app.storage import sqlite

router = APIRouter(tags=["qa"])
log = logging.getLogger(__name__)


@router.post(
    "/qa/ask",
    response_model=QAResponse,
    response_model_by_alias=True,
    responses={503: {"model": QAResponse, "description": "基础设施不可用，status=error"}},
)
def ask(
    req: QARequest,
    request: Request,
    x_debug_force_status: str | None = Header(
        default=None, description="仅 APP_ENV=dev：直接返回指定终态的 mock，供前端联调"
    ),
) -> JSONResponse:
    request_id: str = request.state.request_id
    t0 = time.perf_counter()

    if x_debug_force_status and get_env().app_env == "dev":
        if x_debug_force_status not in fixtures.MOCK_STATUSES:
            raise ApiError(422, ErrorCode.VALIDATION_ERROR, f"未知状态 {x_debug_force_status}")
        resp = fixtures.load_mock(x_debug_force_status).model_copy(
            update={"request_id": request_id}
        )
        hops = []
    else:
        result = pipeline.answer_question(req, request_id)
        resp, hops = result.response, result.hop_log

    latency = int((time.perf_counter() - t0) * 1000)
    try:
        sqlite.log_qa(
            request_id=request_id,
            session_id=req.session_id,
            question=req.question,
            scope=req.scope.model_dump(),
            knowledge_batch=resp.knowledge_batch,
            status=resp.status,
            response=resp.model_dump(mode="json", by_alias=True),
            hop_logs=hop_log.to_json(hops),
            latency_ms=latency,
        )
    except Exception as exc:  # 日志失败不影响回答，但必须留痕
        log.error("qa_logs 写入失败: %s", exc)

    return JSONResponse(resp.model_dump(mode="json", by_alias=True), status_code=resp.http_status())
