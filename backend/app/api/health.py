"""健康检查（V1.2 附录 D.2）。

/health/live ：进程存活（容器健康检查用）。
/health/ready：Neo4j、SQLite、active batch、Ollama、FAISS 逐项状态；
               必需项（neo4j、sqlite、active_batch）全部正常才返回 200，否则 503。
               Ollama / FAISS 不可用不影响 ready（可降级），但会如实报告。
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable
from app.llm import ollama_client
from app.storage import faiss_store, neo4j_client, snapshot, sqlite

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
        "ollama": _probe(ollama_client.ping),
    }
    batch = checks["active_batch"]["detail"] if checks["active_batch"]["ok"] else None
    checks["faiss"] = {
        "ok": faiss_store.status(batch) == "ready",
        "detail": faiss_store.status(batch),
    }
    is_ready = all(checks[k]["ok"] for k in REQUIRED)
    body = {
        "ready": is_ready,
        "active_version": batch,
        "stub_modules": get_settings().pipeline.stub_modules,
        "checks": checks,
    }
    return JSONResponse(body, status_code=200 if is_ready else 503)
