"""完整路径判定（V1.2 §4.2「任意连通的 2 跳并不等于能回答该问题」）。

输入：候选路径、Intent、knowledge_batch。
输出：(通过的路径, 失败原因 ErrorCode 或 None, 失败跳次)。

逐条检查：终点类型、关系序列与方向符合 path_patterns.yaml、全部节点/边 batch_id 一致、
每条边 verified 且 evidence_chunk_ids 非空、年份与 scope 一致。

TODO(BE, D3)：实现，并从 stub_modules 中移除 "path_check"。
check_edge_evidence() 已实现（逐边来源 + 批次隔离），真实实现应复用它。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.domain import CandidatePath, Intent


def check_edge_evidence(c: CandidatePath, batch_id: str) -> int | None:
    """返回第一条不合格边的跳次（1 起）；全部合格返回 None。"""
    for i, ev in enumerate(c.evidence, start=1):
        if ev.batch_id != batch_id or not ev.verified or not ev.evidence_chunk_ids:
            return i
    return None


def filter_complete(
    candidates: list[CandidatePath], intent: Intent, batch_id: str
) -> tuple[list[CandidatePath], ErrorCode | None, int | None]:
    if get_settings().is_stub("path_check"):
        ok = [c for c in candidates if check_edge_evidence(c, batch_id) is None]
        if ok:
            return ok, None, None
        return [], ErrorCode.EVIDENCE_UNVERIFIED, check_edge_evidence(candidates[0], batch_id)
    raise NotImplementedError
