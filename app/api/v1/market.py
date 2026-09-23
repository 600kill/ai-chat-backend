"""API routes for public market."""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException

from app.schemas.market import (
    PublicAgentListResponse,
    PublicAgentDetailResponse,
    CopyAgentRequest,
    CopyAgentResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    WorkflowResponse,
)
from app.services.market_service import market_service
from app.utils.permissions import (
    get_current_user,
    get_current_user_optional,
    NotFoundError,
    ValidationError,
)
from app.models.user import User


router = APIRouter(tags=["market"])


@router.get("/agents", response_model=PublicAgentListResponse)
async def get_public_agents(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    order: Optional[str] = Query(None, description="排序方向"),
    user: Optional[User] = Depends(get_current_user_optional)
):
    """查询公共市场 Agent 列表
    
    权限：全员可访问（无需登录）
    """
    try:
        result = market_service.get_public_agents(
            page=page,
            size=size,
            search=search,
            sort_by=sort_by,
            order=order
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}", response_model=PublicAgentDetailResponse)
async def get_public_agent_detail(
    agent_id: UUID,
    user: Optional[User] = Depends(get_current_user_optional)
):
    """获取公共 Agent 详情
    
    权限：全员可访问（无需登录）
    """
    try:
        result = market_service.get_public_agent_detail(agent_id)
        
        if not result:
            raise NotFoundError("Agent not found or not public")
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/workflow", response_model=WorkflowResponse)
async def get_public_agent_workflow(
    agent_id: UUID,
    user: Optional[User] = Depends(get_current_user_optional)
):
    """获取公共 Agent 工作流图数据
    
    权限：全员可访问（无需登录）
    """
    try:
        workflow_data = await market_service.get_workflow_data(agent_id)
        
        return {
            "code": 200,
            "message": "success",
            "data": workflow_data
        }
    except ValueError as e:
        raise NotFoundError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/sessions", response_model=CreateSessionResponse)
async def create_test_session(
    agent_id: UUID,
    request: CreateSessionRequest,
    user: User = Depends(get_current_user)
):
    """创建测试会话（基于公共 Agent）
    
    权限：需登录
    """
    try:
        result = market_service.create_test_session(
            agent_id=agent_id,
            user=user,
            name=request.name
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except ValueError as e:
        raise NotFoundError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/copy", response_model=CopyAgentResponse)
async def copy_public_agent(
    agent_id: UUID,
    request: CopyAgentRequest,
    user: User = Depends(get_current_user)
):
    """复制公共 Agent 到私有库
    
    权限：需登录（普通用户）
    """
    try:
        result = market_service.copy_agent_to_private(
            agent_id=agent_id,
            user=user,
            new_name=request.new_name
        )
        
        return {
            "code": 200,
            "message": "复制成功",
            "data": result
        }
    except ValueError as e:
        raise NotFoundError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))