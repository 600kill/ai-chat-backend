"""Agent 版本快照 API：发布 / 列表 / 详情 / 软回滚。

权限模型（与 Agent 一致）：
- 读（版本列表/详情）：owner 或 admin，公开 Agent 所有人可读
- 写（发布/回滚）：仅 owner 或 admin
"""

import asyncio
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.models.user import User
from app.services.version_service import VersionNotFoundError, version_service
from app.utils.permissions import (
    HTTPException,
    NotFoundError,
    PermissionError,
    get_current_user,
)

router = APIRouter(tags=["versions"])


class VersionPublishRequest(BaseModel):
    """发布版本请求。"""

    note: Optional[str] = Field(default=None, max_length=500, description="版本说明")


class VersionRollbackRequest(BaseModel):
    """回滚请求（软回滚：新建版本，不覆盖历史）。"""

    note: Optional[str] = Field(default=None, max_length=500, description="自定义说明；缺省为 Rollback from vN")


def _require_agent_access(agent_id: UUID, user: User, write: bool) -> None:
    """校验当前用户对 Agent 的访问权限（读：owner/admin/public；写：owner/admin）。"""
    from app.models.agent import Agent
    from app.services.database import database_service

    with database_service.get_session_maker()() as session:
        agent = session.get(Agent, agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    if write:
        if user.role != "admin" and agent.owner_id != user.id:
            raise PermissionError("Only owner or admin can modify this agent")
    else:
        if not agent.is_public and user.role != "admin" and agent.owner_id != user.id:
            raise PermissionError("Not authorized to access this agent")


def _map_version_errors(exc: Exception) -> None:
    if isinstance(exc, VersionNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=404, detail="Agent not found")
    raise exc


@router.post("/agents/{agent_id}/versions")
async def publish_version(
    agent_id: UUID,
    request: VersionPublishRequest,
    user: User = Depends(get_current_user),
):
    """发布版本：把 Agent 当前配置固化为新版本快照。"""
    _require_agent_access(agent_id, user, write=True)
    try:
        version = await asyncio.to_thread(
            version_service.publish_version, agent_id, request.note, user.id
        )
    except Exception as exc:
        _map_version_errors(exc)
    return {"code": 200, "message": "success", "data": version}


@router.get("/agents/{agent_id}/versions")
async def list_versions(agent_id: UUID, user: User = Depends(get_current_user)):
    """版本列表（version_no 降序，人读 v1/v2/v3）。"""
    _require_agent_access(agent_id, user, write=False)
    versions = await asyncio.to_thread(version_service.list_versions, agent_id)
    return {
        "code": 200,
        "message": "success",
        "data": {"items": versions, "total": len(versions)},
    }


@router.get("/agents/{agent_id}/versions/{version_no}")
async def get_version(agent_id: UUID, version_no: int, user: User = Depends(get_current_user)):
    """版本详情（含完整快照）。"""
    _require_agent_access(agent_id, user, write=False)
    try:
        version = await asyncio.to_thread(version_service.get_version, agent_id, version_no)
    except Exception as exc:
        _map_version_errors(exc)
    return {"code": 200, "message": "success", "data": version}


@router.post("/agents/{agent_id}/versions/{version_no}/rollback")
async def rollback_version(
    agent_id: UUID,
    version_no: int,
    request: VersionRollbackRequest,
    user: User = Depends(get_current_user),
):
    """软回滚：从目标版本拷贝快照新建版本并应用到当前配置，历史版本原样保留。

    快照中已删除的知识库/工具会跳过并在响应 warnings 中提示。
    """
    _require_agent_access(agent_id, user, write=True)
    try:
        result = await asyncio.to_thread(version_service.rollback, agent_id, version_no, user.id)
    except Exception as exc:
        _map_version_errors(exc)
    return {
        "code": 200,
        "message": "success",
        "data": {"version": result["version"], "warnings": result["warnings"]},
    }
