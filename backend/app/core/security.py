"""角色与权限（V1.2 §4.4 访问权限检查；角色划分为本项目约定，见 ADR-002：
游客 / 学生 / 教务知识管理员 / 系统管理员）。

公开资料允许阅读与关联问答的反馈。管理操作使用ADMIN_TOKEN或本机DEMO_MODE；
开发环境另支持X-Demo-Role联调。当前不实现账号登录系统。
"""

from __future__ import annotations

from enum import StrEnum
from secrets import compare_digest

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

    def _check(
        x_demo_role: str | None = Header(default=None),
        x_admin_token: str | None = Header(default=None),
    ) -> Role:
        env = get_env()
        if env.demo_mode or (
            env.admin_token and compare_digest(x_admin_token or "", env.admin_token)
        ):
            return allowed[0]
        role = current_role(x_demo_role)
        if role not in allowed:
            raise ApiError(403, ErrorCode.FORBIDDEN, f"需要角色 {[r.value for r in allowed]}")
        return role

    return _check
