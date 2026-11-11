"""FastAPI 入口：request_id 中间件、统一错误结构、路由注册。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import documents, evaluations, evidence, feedback, health, qa
from app.core.config import get_env, get_patterns, get_settings, get_whitelist
from app.core.errors import ApiError, ErrorCode
from app.core.logging import new_request_id, request_id_var, setup_logging
from app.eval.service import recover_interrupted
from app.schemas.common import ApiErrorBody, ApiErrorInfo
from app.schemas.qa import ErrorInfo, QAResponse
from app.storage import neo4j_client, sqlite

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    get_settings(), get_whitelist(), get_patterns()  # 配置有误时启动即失败
    try:
        applied = sqlite.migrate()
        recover_interrupted()
        if applied:
            log.info("SQLite 迁移: %s", applied)
    except Exception as exc:  # 元数据库不可用时仍启动，由 /health/ready 报告
        log.error("SQLite 迁移失败: %s", exc)
    log.info("启动完成 env=%s", get_env().app_env)
    yield
    neo4j_client.close()


app = FastAPI(title="GraphRAG 校园问答 API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = new_request_id()
    request.state.request_id = rid
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    return response


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


def _error(request: Request, status: int, code: ErrorCode, detail=None) -> JSONResponse:
    rid = _rid(request)
    if request.url.path.endswith("/qa/ask"):
        # /qa/ask 的任何错误都返回完整 QAResponse 结构，前端只需处理一种形状
        body = QAResponse.service_error(rid, ErrorCode.INTERNAL_ERROR).model_copy(
            update={"error": ErrorInfo(code=code, retryable=status >= 500)}
        )
        return JSONResponse(body.model_dump(mode="json", by_alias=True), status_code=status)
    info = ApiErrorInfo(code=code, retryable=status >= 500, detail=detail)
    return JSONResponse(ApiErrorBody(request_id=rid, error=info).model_dump(mode="json"), status)


@app.exception_handler(ApiError)
async def _api_error(request: Request, exc: ApiError):
    return _error(request, exc.status_code, exc.code, exc.detail)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    detail = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
    return _error(request, 422, ErrorCode.VALIDATION_ERROR, detail)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    log.exception("未处理异常")
    return _error(request, 500, ErrorCode.INTERNAL_ERROR)


for r in (qa, evidence, documents, feedback, evaluations, health):
    app.include_router(r.router)
