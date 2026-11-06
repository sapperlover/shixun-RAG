"""Neo4j 驱动单例。所有 Cypher 查询必须带 $batch_id 条件（V1.2 附录 B.3「可隔离」）。"""

from __future__ import annotations

from pathlib import Path

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import Neo4jError
from neo4j.exceptions import ServiceUnavailable as Neo4jUnavailable

from app.core.config import get_env
from app.core.errors import ErrorCode, ServiceUnavailable

CONSTRAINTS_FILE = Path(__file__).parent / "cypher" / "constraints.cypher"

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        env = get_env()
        _driver = GraphDatabase.driver(
            env.neo4j_uri,
            auth=(env.neo4j_user, env.neo4j_password),
            connection_timeout=3,
            max_transaction_retry_time=5,
        )
    return _driver


def close() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def ping() -> str:
    try:
        get_driver().verify_connectivity()
        return "ok"
    except (Neo4jError, Neo4jUnavailable, OSError) as exc:
        raise ServiceUnavailable(ErrorCode.GRAPH_UNAVAILABLE, str(exc)) from exc


def apply_constraints() -> int:
    stmts = [
        s.strip()
        for s in "\n".join(
            ln
            for ln in CONSTRAINTS_FILE.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("//")
        ).split(";")
        if s.strip()
    ]
    with get_driver().session() as session:
        for s in stmts:
            session.run(s).consume()
    return len(stmts)
