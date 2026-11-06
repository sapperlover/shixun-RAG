"""失败归因（V1.2 §6.1 六类）。依据：响应终态、error.code、failed_hop、是否命中标准路径。

TODO(QA, D5)：结合 hop_log 的剪枝原因细化“首跳未召回”与“后续跳缺失”的判定。
"""

from __future__ import annotations

from app.core.errors import ErrorCode
from app.schemas.qa import QAResponse
from app.schemas.resources import EvalQuestion, FailureStage


def attribute(
    q: EvalQuestion, resp: QAResponse, path_hit: bool, answer_correct: bool
) -> FailureStage | None:
    if resp.status == q.expected_status and path_hit and answer_correct:
        return None
    if q.expected_status != "success" and resp.status == q.expected_status:
        return "justified_refusal"
    code = resp.error.code if resp.error else None
    if code == ErrorCode.ANCHOR_NOT_FOUND:
        return "first_hop_miss"
    if code in (ErrorCode.PATH_INCOMPLETE, ErrorCode.EVIDENCE_UNVERIFIED):
        hop = resp.error.failed_hop if resp.error else None
        return "first_hop_miss" if hop == 1 else "later_hop_missing"
    if code == ErrorCode.VERSION_CONFLICT:
        return "version_conflict"
    if code == ErrorCode.CITATION_INVALID:
        return "citation_missing"
    return "model_misuse"
