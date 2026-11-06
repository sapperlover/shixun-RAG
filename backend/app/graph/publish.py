"""发布：validated 批次 → active（事务化切换见 app.storage.snapshot.switch_active）。"""

from __future__ import annotations

from app.storage.snapshot import switch_active


def publish(batch_id: str) -> str | None:
    """返回被替换的旧批次 ID。"""
    return switch_active(batch_id)
