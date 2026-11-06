"""文档上传与列表（知识管理员）。

TODO(Data/BE, D2)：上传校验（扩展名白名单、大小上限、UUID 重命名、哈希去重）→ 写 documents 表。
P0 不做审批流（V1.2 §1.3），发布通过批次完成。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.errors import ApiError, ErrorCode
from app.core.security import Role, require_roles
from app.schemas.common import Page
from app.schemas.resources import DocumentOut

router = APIRouter(tags=["documents"])
_admin = Depends(require_roles(Role.KNOWLEDGE_ADMIN))


@router.get("/documents", response_model=Page[DocumentOut], dependencies=[_admin])
def list_documents(
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
) -> Page[DocumentOut]:
    return Page[DocumentOut](items=[], total=0, limit=limit, offset=offset)


@router.post("/documents", status_code=201, dependencies=[_admin])
def upload_document() -> None:
    raise ApiError(501, ErrorCode.NOT_IMPLEMENTED, "文档上传将在 D2 实现")
