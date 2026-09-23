"""API routes for Agent test session management."""

from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas.session import (
    AgentSessionCreate,
    AgentSessionResponse,
    ChatRequest,
    ChatResponse,
    AgentSessionListResponse,
)
from app.services.database import database_service
from app.services.agent_service import AgentService

router = APIRouter(tags=["agent-sessions"])

# Get AgentService instance
def get_agent_service():
    return AgentService(database_service.get_session_maker())


# ==================== Session Routes ====================

@router.post("/", response_model=AgentSessionResponse)
async def create_agent_session(
    session_data: AgentSessionCreate,
    service: AgentService = Depends(get_agent_service)
):
    """创建 Agent 测试会话"""
    # Verify agent exists
    agent = await service.get_agent(session_data.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    
    if agent.status != "active":
        raise HTTPException(status_code=400, detail="Agent 未启用，无法创建会话")
    
    # Create session
    from app.services.database import database_service
    session_id = str(uuid4())
    chat_session = await database_service.create_session(
        session_id=session_id,
        user_id=session_data.user_id,
        name=f"测试 {agent.name}",
        username="Test User"
    )
    
    # Update session with agent_id
    with database_service.get_session_maker()() as session:
        from app.models.session import Session
        db_session = session.get(Session, session_id)
        db_session.agent_id = session_data.agent_id
        session.add(db_session)
        session.commit()
    
    return {
        "id": session_id,
        "agent_id": agent.id,
        "agent_name": agent.name,
        "user_id": session_data.user_id,
        "status": "active",
        "created_at": chat_session.created_at
    }


@router.get("/", response_model=AgentSessionListResponse)
async def get_agent_sessions(
    agent_id: Optional[UUID] = Query(None, description="Agent ID 筛选"),
    user_id: Optional[int] = Query(None, description="用户 ID 筛选"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    service: AgentService = Depends(get_agent_service)
):
    """获取 Agent 测试会话列表"""
    from app.services.database import database_service
    
    sessions = await database_service.get_all_sessions()
    
    # Filter
    if agent_id:
        sessions = [s for s in sessions if s.agent_id == agent_id]
    if user_id:
        sessions = [s for s in sessions if s.user_id == user_id]
    
    # Pagination
    start = (page - 1) * size
    end = start + size
    paginated_items = sessions[start:end]
    
    # Convert to response format
    session_responses = []
    for s in paginated_items:
        agent = await service.get_agent(s.agent_id) if s.agent_id else None
        session_responses.append({
            "id": s.id,
            "agent_id": s.agent_id,
            "agent_name": agent.name if agent else None,
            "user_id": s.user_id,
            "status": "active",
            "created_at": s.created_at
        })
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": session_responses,
            "total": len(sessions),
            "page": page,
            "size": size
        }
    }


@router.get("/{session_id}", response_model=AgentSessionResponse)
async def get_agent_session(
    session_id: str,
    service: AgentService = Depends(get_agent_service)
):
    """获取 Agent 测试会话详情"""
    from app.services.database import database_service
    
    session = await database_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    agent = await service.get_agent(session.agent_id) if session.agent_id else None
    
    return {
        "id": session.id,
        "agent_id": session.agent_id,
        "agent_name": agent.name if agent else None,
        "user_id": session.user_id,
        "status": "active",
        "created_at": session.created_at
    }


@router.post("/{session_id}/chat")
async def chat_with_agent(
    session_id: str,
    request: ChatRequest,
    service: AgentService = Depends(get_agent_service)
):
    """与 Agent 对话（走配置驱动的 Agent Runtime，含 ReAct 工具循环与 Trace 埋点）"""
    from app.services.database import database_service
    from app.services.agent_runtime_service import agent_runtime_service
    from app.api.v1.chatbot import agent as graph_agent
    from app.schemas import Message

    # Verify session exists
    session = await database_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # Verify agent exists
    if not session.agent_id:
        raise HTTPException(status_code=400, detail="会话未关联 Agent")

    agent = await service.get_agent(session.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    if agent.status != "active":
        raise HTTPException(status_code=400, detail="Agent 未启用")

    from app.services.agent_runtime_service import AgentVersionNotFoundError

    try:
        agent_config = await agent_runtime_service.build_config(
            session.agent_id,
            version_id=request.version_id,
            version_no=request.version_no,
        )
    except AgentVersionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = await graph_agent.run(
        [Message(role="user", content=request.message)],
        session_id,
        config=agent_config,
        user_id=str(session.user_id) if session.user_id is not None else None,
        username=session.username,
        agent_id=str(session.agent_id),
    )

    if result.error:
        raise HTTPException(status_code=500, detail=f"Agent 执行失败：{result.error}")

    assistant_messages = [m for m in result.messages if m.get("role") == "assistant"]
    content = assistant_messages[-1]["content"] if assistant_messages else ""

    response = ChatResponse(
        role="assistant",
        content=content,
        tool_calls=result.tool_calls or None,
        node_name="tool_call" if result.tool_calls else "chat",
    )

    data = {
        **response.model_dump(),
        "model": result.model,
        "latency_ms": result.latency_ms,
        "interrupted": result.interrupted,
    }
    if request.version_id or request.version_no:
        data["version_no"] = request.version_no
    if result.warnings:
        data["warnings"] = result.warnings

    return {"code": 200, "message": "success", "data": data}


@router.post("/{session_id}/chat/stream")
async def chat_with_agent_stream(
    session_id: str,
    request: ChatRequest,
    service: AgentService = Depends(get_agent_service)
):
    """与 Agent 对话（SSE 流式输出，使用 Agent 配置驱动）"""
    from app.services.database import database_service
    from app.services.agent_runtime_service import agent_runtime_service
    from app.api.v1.chatbot import agent as graph_agent
    from app.schemas import Message

    session = await database_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not session.agent_id:
        raise HTTPException(status_code=400, detail="会话未关联 Agent")

    agent = await service.get_agent(session.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    if agent.status != "active":
        raise HTTPException(status_code=400, detail="Agent 未启用")

    from app.services.agent_runtime_service import AgentVersionNotFoundError

    try:
        agent_config = await agent_runtime_service.build_config(
            session.agent_id,
            version_id=request.version_id,
            version_no=request.version_no,
        )
    except AgentVersionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    async def event_generator():
        try:
            if agent_config is not None and agent_config.warnings:
                import json as _json

                yield f"event: warnings\ndata: {_json.dumps(agent_config.warnings, ensure_ascii=False)}\n\n"
            async for token in graph_agent.get_stream_response(
                [Message(role="user", content=request.message)],
                session_id,
                user_id=str(session.user_id) if session.user_id is not None else None,
                username=session.username,
                agent_config=agent_config,
            ):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f'event: error\ndata: {{"detail": "{str(e)}"}}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{session_id}")
async def delete_agent_session(
    session_id: str
):
    """删除 Agent 测试会话"""
    from app.services.database import database_service
    
    success = await database_service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return {
        "code": 200,
        "message": "删除成功",
        "data": None
    }