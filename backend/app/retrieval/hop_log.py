"""跳级日志序列化：写入 qa_logs.hop_logs_json，供按 request_id 复现与失败归因。"""

from __future__ import annotations

from dataclasses import asdict

from app.domain import HopLogEntry


def to_json(entries: list[HopLogEntry]) -> list[dict]:
    return [asdict(e) for e in entries]
