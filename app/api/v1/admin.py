"""API routes for admin operations."""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException

from app.schemas.admin import (
    PrivateAgentListResponse,
    PublishAgentRequest,
    PublishAgentResponse,
    UnpublishAgentRequest,
    UnpublishAgentResponse,
    AgentStatsResponse,
    MarketStatsResponse,
)
from app.services.admin_service import admin_service
from app.utils.permissions import (
    get_current_user,
    require_admin,
    NotFoundError,
    ValidationError,
)
from app.models.user import User


router = APIRouter(tags=["admin"])


@router.get("/agents/private", response_model=PrivateAgentListResponse)
async def get_private_agents(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    owner_id: Optional[int] = Query(None, description="按用户筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    user: User = Depends(get_current_user)
):
    """全局查询所有用户私有 Agent
    
    权限：仅管理员
    """
    require_admin(user)
    
    try:
        result = admin_service.get_private_agents(
            page=page,
            size=size,
            owner_id=owner_id,
            status=status
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/publish", response_model=PublishAgentResponse)
async def publish_agent(
    agent_id: UUID,
    request: PublishAgentRequest,
    user: User = Depends(get_current_user)
):
    """收录私有 Agent 至公共市场
    
    权限：仅管理员
    """
    require_admin(user)
    
    try:
        result = admin_service.publish_agent(
            agent_id=agent_id,
            admin_user=user,
            publish_note=request.publish_note
        )
        
        return {
            "code": 200,
            "message": "收录成功",
            "data": result
        }
    except ValueError as e:
        if "not found" in str(e):
            raise NotFoundError(str(e))
        else:
            raise ValidationError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/unpublish", response_model=UnpublishAgentResponse)
async def unpublish_agent(
    agent_id: UUID,
    request: UnpublishAgentRequest,
    user: User = Depends(get_current_user)
):
    """下架公共市场 Agent
    
    权限：仅管理员
    """
    require_admin(user)
    
    try:
        result = admin_service.unpublish_agent(
            agent_id=agent_id,
            admin_user=user,
            unpublish_reason=request.unpublish_reason
        )
        
        return {
            "code": 200,
            "message": "下架成功",
            "data": result
        }
    except ValueError as e:
        if "not found" in str(e):
            raise NotFoundError(str(e))
        else:
            raise ValidationError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/stats", response_model=AgentStatsResponse)
async def get_agent_stats(
    agent_id: UUID,
    user: User = Depends(get_current_user)
):
    """查看公共 Agent 复制统计
    
    权限：仅管理员
    """
    require_admin(user)
    
    try:
        result = admin_service.get_agent_stats(agent_id)
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except ValueError as e:
        raise NotFoundError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/stats", response_model=MarketStatsResponse)
async def get_market_stats(
    user: User = Depends(get_current_user)
):
    """查看公共市场总体统计
    
    权限：仅管理员
    """
    require_admin(user)
    
    try:
        result = admin_service.get_market_stats()
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))