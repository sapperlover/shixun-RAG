"""POST /feedback —— 四类反馈，按 request_id 可在后台查到（文档-2 §6.3）。

TODO(BE, D4)：写入 feedback 表；request_id 必须存在于 qa_logs。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.errors import ApiError, ErrorCode
from app.core.security import Role, require_roles
from app.schemas.resources import FeedbackIn

router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    status_code=201,
    dependencies=[Depends(require_roles(Role.STUDENT, Role.KNOWLEDGE_ADMIN, Role.SYSTEM_ADMIN))],
)
def create_feedback(body: FeedbackIn) -> None:
    raise ApiError(501, ErrorCode.NOT_IMPLEMENTED, "反馈写入将在 D4 实现")
