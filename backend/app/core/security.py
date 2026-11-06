"""角色与权限（文档-2 §3.2：游客 / 学生 / 教务知识管理员 / 系统管理员）。

TODO(BE, D4)：实现 POST /login 与 token 校验。在那之前：
- prod：所有请求一律视为 guest（安全默认值，越权接口返回 403）；
- dev：可用请求头 X-Demo-Role 模拟角色，便于前端联调。
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import Header

from app.core.config import get_env
from app.core.errors import ApiError, ErrorCode


class Role(StrEnum):
    GUEST = "guest"
    STUDENT = "student"
    KNOWLEDGE_ADMIN = "knowledge_admin"
    SYSTEM_ADMIN = "system_admin"


def current_role(x_demo_role: str | None = Header(default=None)) -> Role:
    if get_env().app_env == "dev" and x_demo_role in Role.__members__.values():
        return Role(x_demo_role)
    return Role.GUEST


def require_roles(*allowed: Role):
    """FastAPI 依赖：`dependencies=[Depends(require_roles(Role.KNOWLEDGE_ADMIN))]`。"""

    def _check(x_demo_role: str | None = Header(default=None)) -> Role:
        role = current_role(x_demo_role)
        if role not in allowed:
            raise ApiError(403, ErrorCode.FORBIDDEN, f"需要角色 {[r.value for r in allowed]}")
        return role

    return _check
