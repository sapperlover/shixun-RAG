"""错误码表（前后端共用；前端按 code 显示文案）。

业务终态 insufficient 也通过 error 字段携带断链原因（V1.2 附录 C.2 insufficient 示例）。
基础设施错误：HTTP 503 + status=error。
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    # —— insufficient：业务上无法给出可信结论（HTTP 200）——
    ANCHOR_NOT_FOUND = "ANCHOR_NOT_FOUND"  # 首跳未召回：问题中没有能匹配的实体锚点
    PATH_INCOMPLETE = "PATH_INCOMPLETE"  # 第 failed_hop 跳无结果，或 3 跳内未到达目标类型
    EVIDENCE_UNVERIFIED = "EVIDENCE_UNVERIFIED"  # 路径存在但有边缺少 verified 来源
    VERSION_CONFLICT = "VERSION_CONFLICT"  # 同范围可信条款互相冲突
    CITATION_INVALID = "CITATION_INVALID"  # 生成后断言-引用校验不过，删光全部断言

    # —— error：服务不可用（HTTP 503）——
    GRAPH_UNAVAILABLE = "GRAPH_UNAVAILABLE"
    METADATA_UNAVAILABLE = "METADATA_UNAVAILABLE"
    NO_ACTIVE_BATCH = "NO_ACTIVE_BATCH"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"  # 模型不可用且事实无法安全模板化
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # —— 通用接口错误 ——
    VALIDATION_ERROR = "VALIDATION_ERROR"  # 422
    FORBIDDEN = "FORBIDDEN"  # 403
    NOT_FOUND = "NOT_FOUND"  # 404
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"  # 501：骨架阶段尚未实现的接口


RETRYABLE: set[ErrorCode] = {
    ErrorCode.GRAPH_UNAVAILABLE,
    ErrorCode.METADATA_UNAVAILABLE,
    ErrorCode.NO_ACTIVE_BATCH,
    ErrorCode.LLM_UNAVAILABLE,
    ErrorCode.INTERNAL_ERROR,
}


class ServiceUnavailable(Exception):
    """基础设施不可用。pipeline 捕获后返回 status=error / HTTP 503。"""

    def __init__(self, code: ErrorCode, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class ApiError(Exception):
    """非问答接口的业务错误，由 main.py 统一转换为错误响应。"""

    def __init__(self, status_code: int, code: ErrorCode, detail: str = ""):
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
