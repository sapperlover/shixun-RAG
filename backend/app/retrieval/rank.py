"""路径排序（V1.2 §4.2）。

优先级：目标链完整性与适用范围匹配 ＞ 逐边来源覆盖和证据质量 ＞ 路径长度 / 检索分值。
同分取跳数少的。返回前 top_k_paths 条，且证据总长不超过 evidence.token_budget。

TODO(BE, D3)：实现，并从 stub_modules 中移除 "rank"。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.domain import CandidatePath, Intent


def rank(paths: list[CandidatePath], intent: Intent) -> list[CandidatePath]:
    settings = get_settings()
    if settings.is_stub("rank"):
        return paths[: settings.retrieval.top_k_paths]
    raise NotImplementedError
