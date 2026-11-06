"""SQLite 元数据库：连接、迁移、问答日志。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.config import get_env
from app.core.errors import ErrorCode, ServiceUnavailable

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@contextmanager
def connect(path: str | None = None) -> Iterator[sqlite3.Connection]:
    """短连接；with 块结束自动提交，异常回滚。"""
    db_path = path or get_env().sqlite_path
    try:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=5, isolation_level=None)
    except (sqlite3.Error, OSError) as exc:
        raise ServiceUnavailable(ErrorCode.METADATA_UNAVAILABLE, str(exc)) from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def migrate(path: str | None = None) -> list[str]:
    """按文件名顺序应用尚未执行的迁移，返回本次执行的文件名。"""
    applied: list[str] = []
    with connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if f.name in done:
                continue
            for stmt in _split_sql(f.read_text(encoding="utf-8")):
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (f.name,))
            applied.append(f.name)
    return applied


def _split_sql(script: str) -> list[str]:
    lines = [ln for ln in script.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def ping(path: str | None = None) -> str:
    with connect(path) as conn:
        rows = conn.execute("SELECT name FROM schema_migrations ORDER BY name").fetchall()
    return rows[-1]["name"] if rows else "no migrations"


def log_qa(
    *,
    request_id: str,
    session_id: str | None,
    question: str,
    scope: dict,
    knowledge_batch: str | None,
    status: str,
    response: dict,
    hop_logs: list[dict] | None,
    latency_ms: int,
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO qa_logs (request_id, session_id, question, scope_json, knowledge_batch,"
            " status, response_json, hop_logs_json, latency_ms) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                request_id,
                session_id,
                question,
                json.dumps(scope, ensure_ascii=False),
                knowledge_batch,
                status,
                json.dumps(response, ensure_ascii=False),
                json.dumps(hop_logs, ensure_ascii=False) if hop_logs is not None else None,
                latency_ms,
            ),
        )
