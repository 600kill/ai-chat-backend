"""API routes for private agent and tool management."""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException

from app.schemas.my import (
    MyAgentCreate,
    MyAgentUpdate,
    MyAgentListResponse,
    MyToolCreate,
    MyToolUpdate,
    MyToolListResponse,
    BatchOperationRequest,
    BatchOperationResponse,
)
from app.services.my_service import my_service
from app.utils.permissions import (
    get_current_user,
    NotFoundError,
    ValidationError,
    PermissionError,
)
from app.models.user import User


router = APIRouter(tags=["my"])


# ==================== Agent Routes ====================

@router.get("/agents", response_model=MyAgentListResponse)
async def get_my_agents(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    user: User = Depends(get_current_user)
):
    """查询我的私有 Agent 列表
    
    权限：需登录（普通用户）
    """
    try:
        result = my_service.get_my_agents(
            user=user,
            page=page,
            size=size,
            status=status,
            search=search
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents")
async def create_my_agent(
    request: MyAgentCreate,
    user: User = Depends(get_current_user)
):
    """创建私有 Agent
    
    权限：需登录
    """
    try:
        agent = my_service.create_my_agent(
            user=user,
            name=request.name,
            description=request.description,
            graph_config=request.graph_config,
            tool_ids=request.tool_ids,
            system_prompt=request.system_prompt,
            model_name=request.model_name,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            kb_ids=request.kb_ids,
        )

        return {
            "code": 200,
            "message": "创建成功",
            "data": {
                "id": agent.id,
                "name": agent.name,
                "status": agent.status,
                "created_at": agent.created_at
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}")
async def get_my_agent_detail(
    agent_id: UUID,
    user: User = Depends(get_current_user)
):
    """获取私有 Agent 详情
    
    权限：需登录（仅 owner 可查看）
    """
    try:
        from app.services.market_service import market_service
        
        # Check if agent is private and owned by user
        result = market_service.get_public_agent_detail(agent_id)
        
        if not result:
            raise NotFoundError("Agent not found")
        
        # Check permission
        from app.services.database import database_service
        with database_service.get_session_maker()() as session:
            from app.models.agent import Agent
            agent = session.get(Agent, agent_id)
            
            if agent.is_public:
                # Public agent - return detail
                return {
                    "code": 200,
                    "message": "success",
                    "data": result
                }
            elif agent.owner_id == user.id:
                # Private agent owned by user - return detail
                return {
                    "code": 200,
                    "message": "success",
                    "data": result
                }
            else:
                raise PermissionError("Not authorized to access this agent")
    except (NotFoundError, PermissionError):
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/agents/{agent_id}")
async def update_my_agent(
    agent_id: UUID,
    request: MyAgentUpdate,
    user: User = Depends(get_current_user)
):
    """更新私有 Agent
    
    权限：需登录（仅 owner 可修改）
    """
    try:
        agent = my_service.update_my_agent(
            agent_id=agent_id,
            user=user,
            name=request.name,
            description=request.description,
            graph_config=request.graph_config,
            system_prompt=request.system_prompt,
            model_name=request.model_name,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            status=request.status,
            tool_ids=request.tool_ids,
            kb_ids=request.kb_ids,
        )
        
        return {
            "code": 200,
            "message": "更新成功",
            "data": {
                "id": agent.id,
                "name": agent.name,
                "status": agent.status
            }
        }
    except ValueError as e:
        if "not found" in str(e):
            raise NotFoundError(str(e))
        elif "public" in str(e):
            raise PermissionError(str(e), error_code=403002)
        else:
            raise PermissionError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}")
async def delete_my_agent(
    agent_id: UUID,
    user: User = Depends(get_current_user)
):
    """删除私有 Agent
    
    权限：需登录（仅 owner 可删除）
    """
    try:
        success = my_service.delete_my_agent(agent_id, user)
        
        return {
            "code": 200,
            "message": "删除成功",
            "data": None
        }
    except ValueError as e:
        if "not found" in str(e):
            raise NotFoundError(str(e))
        elif "public" in str(e):
            raise PermissionError(str(e), error_code=403002)
        else:
            raise PermissionError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/batch", response_model=BatchOperationResponse)
async def batch_operation_agents(
    request: BatchOperationRequest,
    user: User = Depends(get_current_user)
):
    """批量操作私有 Agent
    
    权限：需登录（仅 owner 可操作）
    """
    try:
        result = my_service.batch_operation(
            ids=request.ids,
            action=request.action,
            user=user
        )
        
        return {
            "code": 200,
            "message": "批量操作完成",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Tool Routes ====================

@router.get("/tools", response_model=MyToolListResponse)
async def get_my_tools(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    user: User = Depends(get_current_user)
):
    """查询我的工具列表（私有 + 公共）
    
    权限：需登录
    """
    try:
        result = my_service.get_my_tools(
            user=user,
            page=page,
            size=size,
            search=search
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools")
async def create_my_tool(
    request: MyToolCreate,
    user: User = Depends(get_current_user)
):
    """创建私有工具
    
    权限：需登录
    """
    try:
        tool = my_service.create_my_tool(
            user=user,
            name=request.name,
            description=request.description,
            function_name=request.function_name,
            input_schema=request.input_schema,
            output_schema=request.output_schema,
            example=request.example,
            status="enabled"
        )
        
        return {
            "code": 200,
            "message": "创建成功",
            "data": {
                "id": tool.id,
                "name": tool.name,
                "function_name": tool.function_name,
                "created_at": tool.created_at
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tools/{tool_id}")
async def update_my_tool(
    tool_id: UUID,
    request: MyToolUpdate,
    user: User = Depends(get_current_user)
):
    """更新私有工具
    
    权限：需登录（仅 owner 可修改）
    """
    try:
        tool = my_service.update_my_tool(
            tool_id=tool_id,
            user=user,
            name=request.name,
            description=request.description,
            input_schema=request.input_schema,
            output_schema=request.output_schema,
            example=request.example,
            status=request.status
        )
        
        return {
            "code": 200,
            "message": "更新成功",
            "data": {
                "id": tool.id,
                "name": tool.name,
                "status": tool.status
            }
        }
    except ValueError as e:
        if "not found" in str(e):
            raise NotFoundError(str(e))
        elif "public" in str(e):
            raise PermissionError(str(e), error_code=403002)
        else:
            raise PermissionError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tools/{tool_id}")
async def delete_my_tool(
    tool_id: UUID,
    user: User = Depends(get_current_user)
):
    """删除私有工具
    
    权限：需登录（仅 owner 可删除）
    """
    try:
        success = my_service.delete_my_tool(tool_id, user)
        
        return {
            "code": 200,
            "message": "删除成功",
            "data": None
        }
    except ValueError as e:
        if "not found" in str(e):
            raise NotFoundError(str(e))
        elif "public" in str(e):
            raise PermissionError(str(e), error_code=403002)
        else:
            raise PermissionError(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))