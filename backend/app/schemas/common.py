"""非问答接口的通用结构。"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

from app.core.errors import ErrorCode

T = TypeVar("T")


class ApiErrorInfo(BaseModel):
    code: ErrorCode
    failed_hop: int | None = None
    retryable: bool = False
    detail: Any = None


class ApiErrorBody(BaseModel):
    """除 /qa/ask 外所有接口的错误响应。/qa/ask 的错误始终返回完整 QAResponse。"""

    request_id: str
    status: Literal["error"] = "error"
    error: ApiErrorInfo


class Page(BaseModel, Generic[T]):
    """列表接口统一分页（V1.2 附录 C.2：limit/offset + total）。"""

    items: list[T]
    total: int
    limit: int
    offset: int
