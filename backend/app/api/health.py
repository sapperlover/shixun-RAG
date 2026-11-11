"""健康检查；模型配置检查不发送收费请求，降级能力单独报告。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_env
from app.core.errors import ErrorCode, ServiceUnavailable
from app.llm import chat_api
from app.storage import document_corpus, faiss_store, neo4j_client, snapshot, sqlite

router = APIRouter(tags=["health"])
REQUIRED = ("neo4j", "sqlite", "active_batch")


def _probe(fn):
    try:
        return {"ok": True, "detail": fn()}
    except ServiceUnavailable as exc:
        return {"ok": False, "detail": f"{exc.code}: {exc.detail}"}
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> JSONResponse:
    checks = {
        "neo4j": _probe(neo4j_client.ping),
        "sqlite": _probe(sqlite.ping),
        "active_batch": _probe(snapshot.get_active),
        "generation_api": _probe(chat_api.ping),
    }
    batch = checks["active_batch"]["detail"] if checks["active_batch"]["ok"] else None
    checks["faiss"] = {
        "ok": faiss_store.status(batch) == "ready",
        "detail": faiss_store.status(batch),
    }
    if get_env().document_retrieval_enabled:
        checks["document_corpus"] = _probe(lambda: document_corpus.active() or _no_documents())
        document_batch = document_corpus.active()
        checks["document_vectors"] = {
            "ok": bool(document_batch) and document_corpus.status(document_batch) == "ready",
            "detail": document_corpus.status(document_batch) if document_batch else "not built",
        }
    required = (*REQUIRED, "document_corpus") if get_env().document_retrieval_enabled else REQUIRED
    is_ready = all(checks[k]["ok"] for k in required)
    body = {
        "ready": is_ready,
        "active_version": batch,
        "checks": checks,
    }
    return JSONResponse(body, status_code=200 if is_ready else 503)


def _no_documents():
    raise ServiceUnavailable(ErrorCode.NO_ACTIVE_BATCH, "Document corpus not initialized")
