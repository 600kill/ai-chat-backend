"""API routes for Agent and Tool management."""

import asyncio
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentDetailResponse,
    AgentListResponse,
    ToolCreate,
    ToolUpdate,
    ToolResponse,
    ToolListResponse,
    BatchOperationRequest,
    BatchOperationResponse,
)
from app.services.database import database_service
from app.services.agent_service import AgentService
from app.services.workflow_service import workflow_service

router = APIRouter(tags=["agents"])

# Get AgentService instance
def get_agent_service():
    return AgentService(database_service.get_session_maker())


# ==================== Agent Routes ====================

@router.get("/", response_model=AgentListResponse)
async def get_agents(
    status: Optional[str] = Query(None, description="状态筛选: active/inactive/draft"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    service: AgentService = Depends(get_agent_service)
):
    """查询 Agent 列表"""
    agents = await service.get_all_agents(status=status, search=search)
    
    # Convert to response format with tool count
    agent_responses = []
    for agent in agents:
        tool_count = await service.get_agent_tool_count(agent.id)
        agent_responses.append({
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "status": agent.status,
            "system_prompt": agent.system_prompt,
            "model_name": agent.model_name,
            "temperature": agent.temperature,
            "max_tokens": agent.max_tokens,
            "tool_count": tool_count,
            "created_at": agent.created_at,
            "updated_at": getattr(agent, 'updated_at', None)
        })
    
    # Pagination
    start = (page - 1) * size
    end = start + size
    paginated_items = agent_responses[start:end]
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": paginated_items,
            "total": len(agent_responses),
            "page": page,
            "size": size
        }
    }


@router.get("/tools", response_model=ToolListResponse)
async def get_tools(
    status: Optional[str] = Query(None, description="状态筛选: enabled/disabled"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    service: AgentService = Depends(get_agent_service)
):
    """查询工具列表（必须定义在 GET /{agent_id} 之前，否则 "tools" 会被当成 agent_id 拦截）"""
    tools = await service.get_all_tools(status=status)

    # Filter by search
    if search:
        search_lower = search.lower()
        tools = [
            tool for tool in tools
            if search_lower in tool.name.lower() or
               (tool.description and search_lower in tool.description.lower())
        ]

    # Convert to response format
    tool_responses = [
        {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description,
            "function_name": tool.function_name,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "example": tool.example,
            "status": tool.status,
            "created_at": tool.created_at
        }
        for tool in tools
    ]

    # Pagination
    start = (page - 1) * size
    end = start + size
    paginated_items = tool_responses[start:end]

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": paginated_items,
            "total": len(tool_responses),
            "page": page,
            "size": size
        }
    }


@router.get("/{agent_id}", response_model=AgentDetailResponse)
async def get_agent(
    agent_id: UUID,
    service: AgentService = Depends(get_agent_service)
):
    """获取 Agent 详情"""
    agent = await service.get_agent_with_tools(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    
    tool_count = len(agent.tools)
    tools_response = [
        {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description,
            "function_name": tool.function_name,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "example": tool.example,
            "status": tool.status,
            "created_at": tool.created_at
        }
        for tool in agent.tools
    ]
    
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "graph_config": agent.graph_config,
        "status": agent.status,
        "system_prompt": agent.system_prompt,
        "model_name": agent.model_name,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "tool_count": tool_count,
        "created_at": agent.created_at,
        "updated_at": getattr(agent, 'updated_at', None),
        "tools": tools_response
    }


async def _bind_agent_kbs(agent_id: UUID, kb_ids: Optional[List[UUID]]) -> None:
    """管理端绑定知识库（不校验归属，仅校验库存在）。"""
    if not kb_ids:
        return
    from app.services.rag_service import rag_service

    try:
        await asyncio.to_thread(rag_service.set_agent_kbs, agent_id, kb_ids, None)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail="知识库不存在")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/", response_model=AgentResponse)
async def create_agent(
    agent_data: AgentCreate,
    service: AgentService = Depends(get_agent_service)
):
    """创建新 Agent"""
    data = agent_data.dict()
    tool_ids = data.pop('tool_ids', [])
    kb_ids = data.pop('kb_ids', []) or []

    agent = await service.create_agent(data, tool_ids)
    await _bind_agent_kbs(agent.id, kb_ids)
    tool_count = len(tool_ids)

    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "graph_config": agent.graph_config,
        "status": agent.status,
        "system_prompt": agent.system_prompt,
        "model_name": agent.model_name,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "tool_count": tool_count,
        "created_at": agent.created_at,
        "updated_at": getattr(agent, 'updated_at', None)
    }


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    agent_data: AgentUpdate,
    service: AgentService = Depends(get_agent_service)
):
    """更新 Agent 信息"""
    data = agent_data.dict(exclude_unset=True)
    # kb_ids 出现在请求中即全量覆盖绑定（传空列表=解绑全部）；不支持部分增删
    kb_ids = data.pop('kb_ids', None)
    agent = await service.update_agent(agent_id, data)
    if kb_ids is not None:
        from app.services.rag_service import rag_service

        try:
            await asyncio.to_thread(rag_service.set_agent_kbs, agent_id, kb_ids, None)
        except ValueError as e:
            if "not found" in str(e):
                raise HTTPException(status_code=404, detail="知识库不存在")
            raise HTTPException(status_code=400, detail=str(e))

    tool_count = await service.get_agent_tool_count(agent_id)
    
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "graph_config": agent.graph_config,
        "status": agent.status,
        "system_prompt": agent.system_prompt,
        "model_name": agent.model_name,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "tool_count": tool_count,
        "created_at": agent.created_at,
        "updated_at": getattr(agent, 'updated_at', None)
    }


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: UUID,
    service: AgentService = Depends(get_agent_service)
):
    """删除 Agent"""
    success = await service.delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    
    return {
        "code": 200,
        "message": "删除成功",
        "data": None
    }


@router.post("/batch", response_model=BatchOperationResponse)
async def batch_operation(
    request: BatchOperationRequest,
    service: AgentService = Depends(get_agent_service)
):
    """批量操作 Agent"""
    if request.action not in ["enable", "disable", "delete", "update"]:
        raise HTTPException(status_code=400, detail="无效的操作类型")
    
    result = await service.batch_operation(request.ids, request.action, request.data)
    
    return {
        "code": 200,
        "message": "操作完成",
        "success_count": result["success_count"],
        "failed_count": result["failed_count"],
        "failed_ids": result["failed_ids"]
    }


# ==================== Tool Routes ====================

@router.get("/tools/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: UUID,
    service: AgentService = Depends(get_agent_service)
):
    """获取工具详情"""
    tool = await service.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    
    return {
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "function_name": tool.function_name,
        "input_schema": tool.input_schema,
        "output_schema": tool.output_schema,
        "example": tool.example,
        "status": tool.status,
        "created_at": tool.created_at
    }


@router.post("/tools", response_model=ToolResponse)
async def create_tool(
    tool_data: ToolCreate,
    service: AgentService = Depends(get_agent_service)
):
    """创建新工具"""
    data = tool_data.dict()
    tool = await service.create_tool(data)
    
    return {
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "function_name": tool.function_name,
        "input_schema": tool.input_schema,
        "output_schema": tool.output_schema,
        "example": tool.example,
        "status": tool.status,
        "created_at": tool.created_at
    }


@router.put("/tools/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: UUID,
    tool_data: ToolUpdate,
    service: AgentService = Depends(get_agent_service)
):
    """更新工具信息"""
    data = tool_data.dict(exclude_unset=True)
    tool = await service.update_tool(tool_id, data)
    
    return {
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "function_name": tool.function_name,
        "input_schema": tool.input_schema,
        "output_schema": tool.output_schema,
        "example": tool.example,
        "status": tool.status,
        "created_at": tool.created_at
    }


@router.delete("/tools/{tool_id}")
async def delete_tool(
    tool_id: UUID,
    service: AgentService = Depends(get_agent_service)
):
    """删除工具"""
    success = await service.delete_tool(tool_id)
    if not success:
        raise HTTPException(status_code=404, detail="工具不存在")
    
    return {
        "code": 200,
        "message": "删除成功",
        "data": None
    }


@router.post("/tools/{tool_id}/test")
async def test_tool(
    tool_id: UUID,
    params: dict,
    service: AgentService = Depends(get_agent_service)
):
    """测试工具调用"""
    tool = await service.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    
    try:
        # Import tools dynamically based on function name
        from app.core.langgraph.tools.generate_chart import generate_chart
        from app.core.langgraph.tools.duckduckgo_search import duckduckgo_search_tool
        from app.core.langgraph.tools.ask_human import ask_human
        from app.core.langgraph.tools.calculator import calculator
        from app.core.langgraph.tools.document_search import document_search

        tool_map = {
            "generate_chart": generate_chart,
            "duckduckgo_search": duckduckgo_search_tool,
            "ask_human": ask_human,
            "calculator": calculator,
            "document_search": document_search,
        }
        
        tool_func = tool_map.get(tool.function_name)
        if not tool_func:
            raise HTTPException(status_code=400, detail="工具函数未找到")
        
        # Execute tool
        result = tool_func.invoke(params)
        
        return {
            "code": 200,
            "message": "测试成功",
            "data": {
                "tool_name": tool.name,
                "input": params,
                "output": str(result)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"工具执行失败: {str(e)}")


# ==================== Workflow Routes ====================

@router.get("/{agent_id}/workflow")
async def get_workflow(
    agent_id: UUID
):
    """获取 Agent 工作流数据"""
    try:
        workflow_data = await workflow_service.get_workflow_data(agent_id)
        return {
            "code": 200,
            "message": "success",
            "data": workflow_data
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取工作流失败: {str(e)}")