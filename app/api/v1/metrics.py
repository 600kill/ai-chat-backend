"""API routes for agent performance metrics."""

from datetime import datetime
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException

from app.schemas.metrics import (
    MetricsSessionDetailResponse,
    MetricsAgentStatsResponse,
    MetricsSessionListResponse,
    MetricsMarketStatsResponse,
    MetricsConcurrentResponse,
    MetricsTokenDailyResponse,
    MetricsTokenAllocationResponse,
    MetricsAgentRankingResponse,
    MetricsUserRankingResponse,
)
from app.services.metrics_service import metrics_service
from app.utils.permissions import get_current_user, require_admin
from app.models.user import User


router = APIRouter(tags=["metrics"])


async def check_metrics_permission(agent_id: UUID, user: User) -> bool:
    """Check if user has permission to access metrics for an agent."""
    if user.role == "admin":
        return True
    
    from app.services.database import database_service
    from app.models.agent import Agent
    
    with database_service.get_session_maker()() as session:
        agent = session.get(Agent, agent_id)
        if agent and (agent.is_public or agent.owner_id == user.id):
            return True
    
    return False


# ==================== Session Metrics ====================

@router.get("/sessions/{session_id}", response_model=MetricsSessionDetailResponse)
async def get_session_detail(
    session_id: str,
    user: User = Depends(get_current_user)
):
    """获取会话完整性能明细
    
    权限：普通用户仅可查看自己私有 Agent、公共 Agent 的会话；管理员可查看所有会话
    """
    try:
        # Get session metrics to find agent_id
        session_metrics = await metrics_service.get_session_metrics(session_id)
        
        if not session_metrics:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check permission
        if not await check_metrics_permission(session_metrics.agent_id, user):
            raise HTTPException(status_code=403, detail="Not authorized to access this session")
        
        result = await metrics_service.get_session_full_trace(session_id)
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=MetricsSessionListResponse)
async def get_session_list(
    agent_id: Optional[UUID] = Query(None, description="Agent ID"),
    user_id: Optional[int] = Query(None, description="用户 ID"),
    status: Optional[str] = Query(None, description="状态"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    sort_by: str = Query("started_at", description="排序字段"),
    order: str = Query("desc", description="排序方向"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: User = Depends(get_current_user)
):
    """性能指标分页查询
    
    权限：普通用户仅可查看自己私有 Agent、公共 Agent 的会话；管理员可查看所有会话
    """
    try:
        # For non-admin users, filter by their own user_id
        if user.role != "admin" and user_id is None:
            user_id = user.id
        
        result = await metrics_service.get_session_list(
            agent_id=agent_id,
            user_id=user_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            page=page,
            size=size,
            sort_by=sort_by,
            order=order
        )
        
        # Filter results for non-admin users
        if user.role != "admin":
            from app.services.database import database_service
            from app.models.agent import Agent
            
            with database_service.get_session_maker()() as session:
                valid_agent_ids = set()
                
                # Get user's private agents
                private_agents = session.query(Agent).filter(
                    Agent.owner_id == user.id,
                    Agent.is_public == False
                ).all()
                valid_agent_ids.update({a.id for a in private_agents})
                
                # Get public agents
                public_agents = session.query(Agent).filter(Agent.is_public == True).all()
                valid_agent_ids.update({a.id for a in public_agents})
                
                # Filter items
                result["items"] = [
                    item for item in result["items"]
                    if UUID(item["agent_id"]) in valid_agent_ids
                ]
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Agent Metrics ====================

@router.get("/agents/{agent_id}/stats", response_model=MetricsAgentStatsResponse)
async def get_agent_stats(
    agent_id: UUID,
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    user: User = Depends(get_current_user)
):
    """按 Agent 聚合统计
    
    权限：普通用户仅可查看自己私有 Agent、公共 Agent；管理员可查看所有 Agent
    """
    try:
        # Check permission
        if not await check_metrics_permission(agent_id, user):
            raise HTTPException(status_code=403, detail="Not authorized to access this agent's metrics")
        
        result = await metrics_service.get_agent_stats(
            agent_id=agent_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Market Stats ====================

@router.get("/market/stats", response_model=MetricsMarketStatsResponse)
async def get_market_stats(
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    user: User = Depends(get_current_user)
):
    """公共 Agent 市场统计
    
    权限：全员可访问
    """
    try:
        result = await metrics_service.get_market_stats(
            start_date=start_date,
            end_date=end_date
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Concurrent Stats ====================

@router.get("/concurrent", response_model=MetricsConcurrentResponse)
async def get_concurrent_stats(
    agent_id: Optional[UUID] = Query(None, description="Agent ID"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    user: User = Depends(get_current_user)
):
    """并发监控数据
    
    权限：普通用户仅可查看自己私有 Agent、公共 Agent；管理员可查看所有 Agent
    """
    try:
        # Check permission for specific agent
        if agent_id and not await check_metrics_permission(agent_id, user):
            raise HTTPException(status_code=403, detail="Not authorized to access this agent's concurrent stats")
        
        result = await metrics_service.get_concurrent_stats(
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Token Metrics ====================

@router.get("/token/daily", response_model=MetricsTokenDailyResponse)
async def get_daily_token_summary(
    agent_id: Optional[UUID] = Query(None, description="Agent ID"),
    user_id: Optional[int] = Query(None, description="用户 ID"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    user: User = Depends(get_current_user)
):
    """Token 日消耗明细
    
    权限：普通用户仅可查询自己的消耗；管理员可查询所有消耗
    """
    try:
        # For non-admin users, restrict to their own data
        if user.role != "admin":
            user_id = user.id
        
        result = await metrics_service.get_daily_token_summary(
            agent_id=agent_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/token/allocation", response_model=MetricsTokenAllocationResponse)
async def get_token_allocation(
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    group_by: str = Query("agent", description="分组维度"),
    user: User = Depends(get_current_user)
):
    """Token 成本分摊
    
    权限：仅管理员
    """
    require_admin(user)
    
    try:
        result = await metrics_service.get_token_allocation(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Admin Routes ====================

@router.get("/admin/agents/ranking", response_model=MetricsAgentRankingResponse)
async def get_agent_ranking(
    sort_by: str = Query("sessions", description="排序字段"),
    order: str = Query("desc", description="排序方向"),
    limit: int = Query(10, ge=1, description="返回数量"),
    user: User = Depends(get_current_user)
):
    """全量 Agent 性能排名
    
    权限：仅管理员
    """
    require_admin(user)
    
    try:
        result = await metrics_service.get_agent_ranking(
            sort_by=sort_by,
            order=order,
            limit=limit
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/users/ranking", response_model=MetricsUserRankingResponse)
async def get_user_ranking(
    sort_by: str = Query("tokens", description="排序字段"),
    order: str = Query("desc", description="排序方向"),
    limit: int = Query(10, ge=1, description="返回数量"),
    user: User = Depends(get_current_user)
):
    """全量用户 Token 消耗排名
    
    权限：仅管理员
    """
    require_admin(user)
    
    try:
        result = await metrics_service.get_user_ranking(
            sort_by=sort_by,
            order=order,
            limit=limit
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))