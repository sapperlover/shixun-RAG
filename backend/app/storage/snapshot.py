"""active_version 指针（V1.2 §3.3、附录 B.2）。

规则：
- 每个请求开始时调用一次 get_active()，此后本次请求内的节点、边、Chunk、向量候选都只用这个 batch；
- 只有 state=validated 的批次可以被 switch_active() 切换为 active，切换在一个 SQLite 事务内完成；
- 被替换的旧批次标为 retired，在途查询仍可读取，清理由运维任务另行执行。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.errors import ErrorCode, ServiceUnavailable
from app.fixtures import STUB_BATCH
from app.storage import sqlite

PROJECT_KEY = "campus-graphrag"


def get_active() -> str:
    if get_settings().is_stub("snapshot"):
        return STUB_BATCH
    with sqlite.connect() as conn:
        row = conn.execute(
            "SELECT active_version FROM active_snapshot WHERE project_key = ?", (PROJECT_KEY,)
        ).fetchone()
    if row is None:
        raise ServiceUnavailable(ErrorCode.NO_ACTIVE_BATCH, "尚未发布任何知识批次")
    return row["active_version"]


def switch_active(batch_id: str, db_path: str | None = None) -> str | None:
    """把 validated 批次切换为 active，返回被替换的旧批次 ID。"""
    with sqlite.connect(db_path) as conn:  # 单个事务；任何异常整体回滚
        row = conn.execute(
            "SELECT state FROM build_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None or row["state"] != "validated":
            raise ValueError(f"批次 {batch_id} 不存在或状态不是 validated")
        old = conn.execute(
            "SELECT active_version FROM active_snapshot WHERE project_key = ?", (PROJECT_KEY,)
        ).fetchone()
        old_id = old["active_version"] if old else None
        if old_id:
            conn.execute("UPDATE build_batches SET state = 'retired' WHERE batch_id = ?", (old_id,))
        conn.execute("UPDATE build_batches SET state = 'active' WHERE batch_id = ?", (batch_id,))
        conn.execute(
            "INSERT INTO active_snapshot (project_key, active_version) VALUES (?, ?) "
            "ON CONFLICT(project_key) DO UPDATE SET active_version = excluded.active_version,"
            " switched_at = datetime('now')",
            (PROJECT_KEY, batch_id),
        )
    return old_id
