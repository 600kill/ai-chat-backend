"""Metrics service for tracking agent execution performance."""

import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from app.models.metrics import (
    AgentMetricsSession,
    AgentMetricsLLM,
    AgentMetricsVector,
    AgentMetricsTool,
    AgentMetricsNode,
    AgentMetricsConcurrent,
    AgentMetricsTokenSummary,
)
from app.models.agent import Agent
from app.models.user import User
from app.services.database import database_service
from app.core.logging import logger


class MetricsService:
    """Service for collecting and querying agent performance metrics."""
    
    def __init__(self):
        self.session_maker = database_service.get_session_maker()
        self._execution_order_cache: Dict[str, int] = {}
    
    def _get_next_execution_order(self, session_id: str) -> int:
        """Get next execution order for node metrics."""
        if session_id not in self._execution_order_cache:
            self._execution_order_cache[session_id] = 0
        self._execution_order_cache[session_id] += 1
        return self._execution_order_cache[session_id]
    
    def _clear_execution_order(self, session_id: str):
        """Clear execution order cache for a session."""
        if session_id in self._execution_order_cache:
            del self._execution_order_cache[session_id]
    
    async def start_session(
        self,
        session_id: str,
        agent_id: UUID,
        user_id: int
    ) -> UUID:
        """Start a new metrics session.
        
        Args:
            session_id: The session ID
            agent_id: The agent ID
            user_id: The user ID
        
        Returns:
            The metrics session ID
        """
        with self.session_maker() as session:
            metrics_session = AgentMetricsSession(
                id=uuid4(),
                session_id=session_id,
                agent_id=agent_id,
                user_id=user_id,
                started_at=datetime.now(),
                status="running"
            )
            session.add(metrics_session)
            session.commit()
            session.refresh(metrics_session)
            
            logger.info(
                "metrics_session_started",
                session_id=session_id,
                agent_id=str(agent_id),
                user_id=user_id
            )
            
            return metrics_session.id
    
    async def end_session(
        self,
        metrics_session_id: UUID,
        total_duration_ms: int,
        status: str = "success",
        error_message: Optional[str] = None,
        node_count: int = 0
    ):
        """End a metrics session.
        
        Args:
            metrics_session_id: The metrics session ID
            total_duration_ms: Total duration in milliseconds
            status: Session status
            error_message: Error message if failed
            node_count: Number of nodes executed
        """
        with self.session_maker() as session:
            metrics_session = session.get(AgentMetricsSession, metrics_session_id)
            
            if metrics_session:
                metrics_session.ended_at = datetime.now()
                metrics_session.total_duration_ms = total_duration_ms
                metrics_session.status = status
                metrics_session.error_message = error_message
                session.commit()
                
                # Update concurrent count
                self._update_concurrent_count(metrics_session.agent_id, -1)
                
                # Update token summary
                await self._update_token_summary(metrics_session)
                
                self._clear_execution_order(metrics_session.session_id)
                
                logger.info(
                    "metrics_session_ended",
                    session_id=metrics_session.session_id,
                    total_duration_ms=total_duration_ms,
                    status=status
                )
    
    async def record_llm_inference(
        self,
        metrics_session_id: UUID,
        session_id: str,
        llm_model: str,
        inference_duration_ms: int,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        ttft_ms: Optional[int] = None,
        token_cost: Optional[float] = None,
        status: str = "success",
        error_message: Optional[str] = None
    ):
        """Record LLM inference metrics."""
        with self.session_maker() as session:
            llm_metrics = AgentMetricsLLM(
                id=uuid4(),
                metrics_session_id=metrics_session_id,
                session_id=session_id,
                llm_model=llm_model,
                inference_duration_ms=inference_duration_ms,
                ttft_ms=ttft_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                token_cost=token_cost,
                status=status,
                error_message=error_message
            )
            session.add(llm_metrics)
            session.commit()
    
    async def record_vector_search(
        self,
        metrics_session_id: UUID,
        session_id: str,
        search_duration_ms: int,
        results_count: int,
        query_length: Optional[int] = None,
        memory_type: Optional[str] = "long_term",
        status: str = "success"
    ):
        """Record vector search metrics."""
        with self.session_maker() as session:
            vector_metrics = AgentMetricsVector(
                id=uuid4(),
                metrics_session_id=metrics_session_id,
                session_id=session_id,
                search_duration_ms=search_duration_ms,
                results_count=results_count,
                query_length=query_length,
                memory_type=memory_type,
                status=status
            )
            session.add(vector_metrics)
            session.commit()
    
    async def record_tool_call(
        self,
        metrics_session_id: UUID,
        session_id: str,
        tool_name: str,
        call_duration_ms: int,
        tool_id: Optional[UUID] = None,
        input_params: Optional[dict] = None,
        output_result: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None
    ):
        """Record tool call metrics."""
        with self.session_maker() as session:
            tool_metrics = AgentMetricsTool(
                id=uuid4(),
                metrics_session_id=metrics_session_id,
                session_id=session_id,
                tool_name=tool_name,
                tool_id=tool_id,
                call_duration_ms=call_duration_ms,
                input_params=input_params,
                output_result=output_result,
                status=status,
                error_message=error_message
            )
            session.add(tool_metrics)
            session.commit()
    
    async def record_node_execution(
        self,
        metrics_session_id: UUID,
        session_id: str,
        node_name: str,
        node_type: str,
        duration_ms: int,
        input_snapshot: Optional[dict] = None,
        output_snapshot: Optional[dict] = None,
        status: str = "success"
    ):
        """Record node execution metrics."""
        execution_order = self._get_next_execution_order(session_id)
        
        with self.session_maker() as session:
            node_metrics = AgentMetricsNode(
                id=uuid4(),
                metrics_session_id=metrics_session_id,
                session_id=session_id,
                node_name=node_name,
                node_type=node_type,
                execution_order=execution_order,
                duration_ms=duration_ms,
                input_snapshot=input_snapshot,
                output_snapshot=output_snapshot,
                status=status
            )
            session.add(node_metrics)
            session.commit()
    
    def _update_concurrent_count(self, agent_id: UUID, delta: int):
        """Update concurrent session count for an agent."""
        with self.session_maker() as session:
            snapshot = AgentMetricsConcurrent(
                id=uuid4(),
                agent_id=agent_id,
                active_sessions=self.get_active_session_count(agent_id) + delta,
                active_tasks=self.get_active_task_count(agent_id),
                recorded_at=datetime.now()
            )
            session.add(snapshot)
            session.commit()
    
    def get_active_session_count(self, agent_id: UUID) -> int:
        """Get current active session count for an agent."""
        with self.session_maker() as session:
            count = session.query(AgentMetricsSession).filter(
                AgentMetricsSession.agent_id == agent_id,
                AgentMetricsSession.status == "running"
            ).count()
            return count
    
    def get_active_task_count(self, agent_id: UUID) -> int:
        """Get current active task count for an agent."""
        # This would be more complex in a real implementation
        return self.get_active_session_count(agent_id)
    
    async def _update_token_summary(self, metrics_session: AgentMetricsSession):
        """Update daily token consumption summary."""
        with self.session_maker() as session:
            today = date.today()
            
            # Get LLM metrics for this session
            llm_metrics = session.query(AgentMetricsLLM).filter(
                AgentMetricsLLM.metrics_session_id == metrics_session.id
            ).first()
            
            if not llm_metrics:
                return
            
            # Find or create summary record
            summary = session.query(AgentMetricsTokenSummary).filter(
                AgentMetricsTokenSummary.agent_id == metrics_session.agent_id,
                AgentMetricsTokenSummary.user_id == metrics_session.user_id,
                AgentMetricsTokenSummary.date == today
            ).first()
            
            if summary:
                summary.total_input_tokens += llm_metrics.input_tokens
                summary.total_output_tokens += llm_metrics.output_tokens
                summary.total_tokens += llm_metrics.total_tokens
                summary.total_cost += llm_metrics.token_cost or 0
                summary.request_count += 1
            else:
                summary = AgentMetricsTokenSummary(
                    id=uuid4(),
                    agent_id=metrics_session.agent_id,
                    user_id=metrics_session.user_id,
                    date=today,
                    total_input_tokens=llm_metrics.input_tokens,
                    total_output_tokens=llm_metrics.output_tokens,
                    total_tokens=llm_metrics.total_tokens,
                    total_cost=llm_metrics.token_cost or 0,
                    request_count=1
                )
                session.add(summary)
            
            session.commit()
    
    async def get_session_metrics(self, session_id: str) -> Optional[AgentMetricsSession]:
        """Get metrics for a specific session."""
        with self.session_maker() as session:
            return session.query(AgentMetricsSession).filter(
                AgentMetricsSession.session_id == session_id
            ).first()
    
    async def get_session_full_trace(self, session_id: str):
        """Get full performance trace for a session."""
        with self.session_maker() as session:
            # Get session metrics（同一物理会话每次 run 一条，取最新一次）
            session_metrics = session.query(AgentMetricsSession).filter(
                AgentMetricsSession.session_id == session_id
            ).order_by(AgentMetricsSession.created_at.desc()).first()
            
            if not session_metrics:
                return None
            
            # Get agent and user info
            agent = session.get(Agent, session_metrics.agent_id)
            user = session.get(User, session_metrics.user_id)
            
            # Get LLM metrics（多轮 ReAct 会产生多条，旧实现 .first() 会丢数据）
            llm_metrics = session.query(AgentMetricsLLM).filter(
                AgentMetricsLLM.metrics_session_id == session_metrics.id
            ).order_by(AgentMetricsLLM.created_at).all()

            # Get vector metrics
            vector_metrics = session.query(AgentMetricsVector).filter(
                AgentMetricsVector.metrics_session_id == session_metrics.id
            ).order_by(AgentMetricsVector.created_at).all()

            # Get tool metrics
            tool_metrics = session.query(AgentMetricsTool).filter(
                AgentMetricsTool.metrics_session_id == session_metrics.id
            ).order_by(AgentMetricsTool.created_at).all()

            # Get node metrics
            node_metrics = session.query(AgentMetricsNode).filter(
                AgentMetricsNode.metrics_session_id == session_metrics.id
            ).order_by(AgentMetricsNode.execution_order).all()

            # ===== 统一 Trace 时间线：Memory / RAG / LLM / Tool / Node 合并排序 =====
            timeline: List[Dict] = []

            for vm in vector_metrics:
                is_rag = (vm.memory_type or "").lower() == "rag"
                timeline.append({
                    "type": "rag" if is_rag else "memory",
                    "name": "knowledge_base" if is_rag else "long_term_memory",
                    "at": vm.created_at,
                    "duration_ms": vm.search_duration_ms,
                    "status": vm.status,
                    "detail": {
                        "results_count": vm.results_count,
                        "query_length": vm.query_length,
                        "memory_type": vm.memory_type,
                    },
                })

            for lm in llm_metrics:
                timeline.append({
                    "type": "llm",
                    "name": lm.llm_model,
                    "at": lm.created_at,
                    "duration_ms": lm.inference_duration_ms,
                    "status": lm.status,
                    "detail": {
                        "ttft_ms": lm.ttft_ms,
                        "input_tokens": lm.input_tokens,
                        "output_tokens": lm.output_tokens,
                        "total_tokens": lm.total_tokens,
                        "token_cost": lm.token_cost,
                        "error_message": lm.error_message,
                    },
                })

            for tm in tool_metrics:
                timeline.append({
                    "type": "tool",
                    "name": tm.tool_name,
                    "at": tm.created_at,
                    "duration_ms": tm.call_duration_ms,
                    "status": tm.status,
                    "detail": {
                        "tool_id": str(tm.tool_id) if tm.tool_id else None,
                        "input_params": tm.input_params,
                        "output_result": tm.output_result,
                        "error_message": tm.error_message,
                    },
                })

            for nm in node_metrics:
                timeline.append({
                    "type": "node",
                    "name": nm.node_name,
                    "at": nm.created_at,
                    "duration_ms": nm.duration_ms,
                    "status": nm.status,
                    "detail": {
                        "node_type": nm.node_type,
                        "execution_order": nm.execution_order,
                        "input_snapshot": nm.input_snapshot,
                        "output_snapshot": nm.output_snapshot,
                    },
                })

            timeline.sort(key=lambda e: (e["at"] or datetime.min, e["detail"].get("execution_order", 0)))

            return {
                "session_info": {
                    "session_id": session_metrics.session_id,
                    "agent_id": str(session_metrics.agent_id),
                    "agent_name": agent.name if agent else None,
                    "user_id": session_metrics.user_id,
                    "user_name": user.username if user else None,
                    "started_at": session_metrics.started_at,
                    "ended_at": session_metrics.ended_at,
                    "total_duration_ms": session_metrics.total_duration_ms,
                    "status": session_metrics.status,
                    "error_message": session_metrics.error_message
                },
                "timeline": timeline,
                "summary": {
                    "llm_calls": len(llm_metrics),
                    "tool_calls": len(tool_metrics),
                    "retrievals": len(vector_metrics),
                    "node_executions": len(node_metrics),
                },
                "llm_metrics": [{
                    "llm_model": lm.llm_model,
                    "inference_duration_ms": lm.inference_duration_ms,
                    "ttft_ms": lm.ttft_ms,
                    "input_tokens": lm.input_tokens,
                    "output_tokens": lm.output_tokens,
                    "total_tokens": lm.total_tokens,
                    "token_cost": lm.token_cost,
                    "status": lm.status,
                    "error_message": lm.error_message,
                    "at": lm.created_at,
                } for lm in llm_metrics],
                "vector_metrics": [{
                    "search_duration_ms": vm.search_duration_ms,
                    "results_count": vm.results_count,
                    "query_length": vm.query_length,
                    "memory_type": vm.memory_type,
                    "status": vm.status
                } for vm in vector_metrics],
                "tool_metrics": [{
                    "tool_name": tm.tool_name,
                    "tool_id": str(tm.tool_id) if tm.tool_id else None,
                    "call_duration_ms": tm.call_duration_ms,
                    "input_params": tm.input_params,
                    "output_result": tm.output_result,
                    "status": tm.status,
                    "error_message": tm.error_message
                } for tm in tool_metrics],
                "node_metrics": [{
                    "node_name": nm.node_name,
                    "node_type": nm.node_type,
                    "execution_order": nm.execution_order,
                    "duration_ms": nm.duration_ms,
                    "input_snapshot": nm.input_snapshot,
                    "output_snapshot": nm.output_snapshot,
                    "status": nm.status
                } for nm in node_metrics]
            }
    
    def _percentile(self, sorted_list: List[int], p: float) -> float:
        """Calculate percentile."""
        if not sorted_list:
            return 0.0
        k = (len(sorted_list) - 1) * p
        f = int(k)
        c = k - f
        if f + 1 < len(sorted_list):
            return sorted_list[f] + c * (sorted_list[f + 1] - sorted_list[f])
        return sorted_list[f]
    
    async def calculate_latency_percentiles(
        self,
        agent_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Calculate latency percentiles for an agent."""
        with self.session_maker() as session:
            query = session.query(AgentMetricsSession.total_duration_ms).filter(
                AgentMetricsSession.agent_id == agent_id,
                AgentMetricsSession.status == "success"
            )
            
            if start_date:
                query = query.filter(AgentMetricsSession.started_at >= start_date)
            if end_date:
                query = query.filter(AgentMetricsSession.started_at <= end_date)
            
            results = query.order_by(AgentMetricsSession.total_duration_ms).all()
            durations = [r[0] for r in results]
            
            if not durations:
                return {}
            
            return {
                "total_sessions": len(durations),
                "avg_duration_ms": sum(durations) / len(durations),
                "p50_latency_ms": self._percentile(durations, 0.50),
                "p90_latency_ms": self._percentile(durations, 0.90),
                "p95_latency_ms": self._percentile(durations, 0.95),
                "p99_latency_ms": self._percentile(durations, 0.99),
                "min_duration_ms": min(durations),
                "max_duration_ms": max(durations)
            }
    
    async def get_agent_stats(
        self,
        agent_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Get aggregated statistics for an agent."""
        with self.session_maker() as session:
            # Get agent info
            agent = session.get(Agent, agent_id)
            if not agent:
                return {}
            
            # Base query
            base_query = session.query(AgentMetricsSession).filter(
                AgentMetricsSession.agent_id == agent_id
            )
            
            if start_date:
                base_query = base_query.filter(AgentMetricsSession.started_at >= start_date)
            if end_date:
                base_query = base_query.filter(AgentMetricsSession.started_at <= end_date)
            
            # Session stats
            total_sessions = base_query.count()
            success_count = base_query.filter(AgentMetricsSession.status == "success").count()
            failed_count = total_sessions - success_count
            success_rate = success_count / total_sessions if total_sessions > 0 else 0
            
            # Latency stats
            latency_stats = await self.calculate_latency_percentiles(agent_id, start_date, end_date)
            
            # LLM stats
            llm_query = session.query(AgentMetricsLLM).filter(
                AgentMetricsLLM.metrics_session_id.in_(
                    session.query(AgentMetricsSession.id).filter(
                        AgentMetricsSession.agent_id == agent_id
                    )
                )
            )
            if start_date:
                llm_query = llm_query.join(AgentMetricsSession).filter(
                    AgentMetricsSession.started_at >= start_date
                )
            llm_metrics = llm_query.all()
            
            total_input_tokens = sum(m.input_tokens for m in llm_metrics)
            total_output_tokens = sum(m.output_tokens for m in llm_metrics)
            total_tokens = sum(m.total_tokens for m in llm_metrics)
            total_cost = sum(m.token_cost or 0 for m in llm_metrics)
            
            avg_inference_ms = sum(m.inference_duration_ms for m in llm_metrics) / len(llm_metrics) if llm_metrics else 0
            avg_ttft_ms = sum(m.ttft_ms or 0 for m in llm_metrics) / len(llm_metrics) if llm_metrics else 0
            
            # Vector stats
            vector_query = session.query(AgentMetricsVector).filter(
                AgentMetricsVector.metrics_session_id.in_(
                    session.query(AgentMetricsSession.id).filter(
                        AgentMetricsSession.agent_id == agent_id
                    )
                )
            )
            vector_metrics = vector_query.all()
            total_searches = len(vector_metrics)
            avg_search_ms = sum(m.search_duration_ms for m in vector_metrics) / len(vector_metrics) if vector_metrics else 0
            
            # Tool stats
            tool_query = session.query(AgentMetricsTool).filter(
                AgentMetricsTool.metrics_session_id.in_(
                    session.query(AgentMetricsSession.id).filter(
                        AgentMetricsSession.agent_id == agent_id
                    )
                )
            )
            tool_metrics = tool_query.all()
            total_calls = len(tool_metrics)
            avg_call_ms = sum(m.call_duration_ms for m in tool_metrics) / len(tool_metrics) if tool_metrics else 0
            
            # Top tools
            tool_counts = {}
            for tm in tool_metrics:
                tool_counts[tm.tool_name] = tool_counts.get(tm.tool_name, 0) + 1
            top_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            return {
                "agent_id": str(agent_id),
                "agent_name": agent.name,
                "period": {
                    "start_date": start_date,
                    "end_date": end_date
                },
                "session_stats": {
                    "total_sessions": total_sessions,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "success_rate": success_rate
                },
                "latency_stats": latency_stats,
                "token_stats": {
                    "total_input_tokens": total_input_tokens,
                    "total_output_tokens": total_output_tokens,
                    "total_tokens": total_tokens,
                    "avg_input_tokens": total_input_tokens / total_sessions if total_sessions > 0 else 0,
                    "avg_output_tokens": total_output_tokens / total_sessions if total_sessions > 0 else 0,
                    "total_cost": total_cost
                },
                "llm_stats": {
                    "avg_inference_duration_ms": avg_inference_ms,
                    "avg_ttft_ms": avg_ttft_ms
                },
                "vector_stats": {
                    "total_searches": total_searches,
                    "avg_search_duration_ms": avg_search_ms
                },
                "tool_stats": {
                    "total_calls": total_calls,
                    "avg_call_duration_ms": avg_call_ms,
                    "top_tools": [{"tool_name": name, "call_count": count} for name, count in top_tools]
                }
            }
    
    async def get_session_list(
        self,
        agent_id: Optional[UUID] = None,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        size: int = 20,
        sort_by: str = "started_at",
        order: str = "desc"
    ) -> Dict:
        """Get paginated list of sessions."""
        with self.session_maker() as session:
            query = session.query(AgentMetricsSession)
            
            if agent_id:
                query = query.filter(AgentMetricsSession.agent_id == agent_id)
            if user_id:
                query = query.filter(AgentMetricsSession.user_id == user_id)
            if status:
                query = query.filter(AgentMetricsSession.status == status)
            if start_date:
                query = query.filter(AgentMetricsSession.started_at >= start_date)
            if end_date:
                query = query.filter(AgentMetricsSession.started_at <= end_date)
            
            # Sort
            if sort_by == "total_duration_ms":
                query = query.order_by(
                    getattr(AgentMetricsSession, sort_by).desc() if order == "desc" else getattr(AgentMetricsSession, sort_by)
                )
            else:
                query = query.order_by(
                    getattr(AgentMetricsSession, sort_by).desc() if order == "desc" else getattr(AgentMetricsSession, sort_by)
                )
            
            # Count
            total = query.count()
            
            # Pagination
            sessions = query.offset((page - 1) * size).limit(size).all()
            
            # Get agent names
            agent_ids = {s.agent_id for s in sessions}
            agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
            agent_map = {a.id: a.name for a in agents}
            
            # Get user names
            user_ids = {s.user_id for s in sessions}
            users = session.query(User).filter(User.id.in_(user_ids)).all()
            user_map = {u.id: u.username for u in users}
            
            # Get LLM token info for each session
            session_ids = {s.id for s in sessions}
            llm_metrics = session.query(AgentMetricsLLM).filter(
                AgentMetricsLLM.metrics_session_id.in_(session_ids)
            ).all()
            llm_map = {m.metrics_session_id: m for m in llm_metrics}
            
            items = []
            for s in sessions:
                llm = llm_map.get(s.id)
                items.append({
                    "session_id": s.session_id,
                    "agent_id": str(s.agent_id),
                    "agent_name": agent_map.get(s.agent_id),
                    "user_id": s.user_id,
                    "user_name": user_map.get(s.user_id),
                    "total_duration_ms": s.total_duration_ms,
                    "status": s.status,
                    "input_tokens": llm.input_tokens if llm else 0,
                    "output_tokens": llm.output_tokens if llm else 0,
                    "started_at": s.started_at
                })
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "size": size
            }
    
    async def get_market_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Get public market statistics."""
        with self.session_maker() as session:
            # Get public agents
            public_agents = session.query(Agent).filter(Agent.is_public == True).all()
            public_agent_ids = {a.id for a in public_agents}
            
            # Query metrics for public agents
            query = session.query(AgentMetricsSession).filter(
                AgentMetricsSession.agent_id.in_(public_agent_ids)
            )
            
            if start_date:
                query = query.filter(AgentMetricsSession.started_at >= start_date)
            if end_date:
                query = query.filter(AgentMetricsSession.started_at <= end_date)
            
            total_sessions = query.count()
            
            # Get LLM metrics
            llm_query = session.query(AgentMetricsLLM).filter(
                AgentMetricsLLM.metrics_session_id.in_(
                    session.query(AgentMetricsSession.id).filter(
                        AgentMetricsSession.agent_id.in_(public_agent_ids)
                    )
                )
            )
            llm_metrics = llm_query.all()
            total_tokens = sum(m.total_tokens for m in llm_metrics)
            total_cost = sum(m.token_cost or 0 for m in llm_metrics)
            
            # Average latency
            durations = [s.total_duration_ms for s in query.all()]
            avg_latency = sum(durations) / len(durations) if durations else 0
            
            # Agent rankings
            agent_stats = {}
            for agent in public_agents:
                agent_query = session.query(AgentMetricsSession).filter(
                    AgentMetricsSession.agent_id == agent.id
                )
                if start_date:
                    agent_query = agent_query.filter(AgentMetricsSession.started_at >= start_date)
                if end_date:
                    agent_query = agent_query.filter(AgentMetricsSession.started_at <= end_date)
                
                agent_sessions = agent_query.all()
                agent_llm = session.query(AgentMetricsLLM).filter(
                    AgentMetricsLLM.metrics_session_id.in_(
                        [s.id for s in agent_sessions]
                    )
                ).all()
                
                agent_stats[str(agent.id)] = {
                    "agent_name": agent.name,
                    "session_count": len(agent_sessions),
                    "total_tokens": sum(m.total_tokens for m in agent_llm),
                    "total_cost": sum(m.token_cost or 0 for m in agent_llm),
                    "avg_latency_ms": sum(s.total_duration_ms for s in agent_sessions) / len(agent_sessions) if agent_sessions else 0
                }
            
            # Concurrent stats
            concurrent_query = session.query(AgentMetricsConcurrent).filter(
                AgentMetricsConcurrent.agent_id.in_(public_agent_ids)
            )
            if start_date:
                concurrent_query = concurrent_query.filter(AgentMetricsConcurrent.recorded_at >= start_date)
            if end_date:
                concurrent_query = concurrent_query.filter(AgentMetricsConcurrent.recorded_at <= end_date)
            
            concurrent_snapshots = concurrent_query.all()
            peak_concurrent = max(s.active_sessions for s in concurrent_snapshots) if concurrent_snapshots else 0
            peak_time = None
            if concurrent_snapshots:
                peak_record = max(concurrent_snapshots, key=lambda x: x.active_sessions)
                peak_time = peak_record.recorded_at
            
            return {
                "period": {
                    "start_date": start_date,
                    "end_date": end_date
                },
                "overview": {
                    "total_public_agents": len(public_agents),
                    "total_sessions": total_sessions,
                    "total_tokens": total_tokens,
                    "total_cost": total_cost,
                    "avg_latency_ms": avg_latency
                },
                "agent_rankings": sorted(
                    agent_stats.values(),
                    key=lambda x: x["session_count"],
                    reverse=True
                ),
                "concurrent_stats": {
                    "peak_concurrent_sessions": peak_concurrent,
                    "peak_time": peak_time
                }
            }
    
    async def get_concurrent_stats(
        self,
        agent_id: Optional[UUID] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict:
        """Get concurrent session statistics."""
        with self.session_maker() as session:
            # Current active sessions
            current_query = session.query(AgentMetricsSession).filter(
                AgentMetricsSession.status == "running"
            )
            if agent_id:
                current_query = current_query.filter(AgentMetricsSession.agent_id == agent_id)
            active_sessions = current_query.count()
            active_tasks = active_sessions  # Simplified
            
            # History
            history_query = session.query(AgentMetricsConcurrent)
            if agent_id:
                history_query = history_query.filter(AgentMetricsConcurrent.agent_id == agent_id)
            if start_time:
                history_query = history_query.filter(AgentMetricsConcurrent.recorded_at >= start_time)
            if end_time:
                history_query = history_query.filter(AgentMetricsConcurrent.recorded_at <= end_time)
            
            history = history_query.order_by(AgentMetricsConcurrent.recorded_at.desc()).limit(100).all()
            
            # Get agent names
            agent_ids = {h.agent_id for h in history}
            agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
            agent_map = {a.id: a.name for a in agents}
            
            history_items = []
            for h in history:
                history_items.append({
                    "agent_id": str(h.agent_id),
                    "agent_name": agent_map.get(h.agent_id),
                    "active_sessions": h.active_sessions,
                    "active_tasks": h.active_tasks,
                    "recorded_at": h.recorded_at
                })
            
            return {
                "current": {
                    "active_sessions": active_sessions,
                    "active_tasks": active_tasks
                },
                "history": history_items
            }
    
    async def get_daily_token_summary(
        self,
        agent_id: Optional[UUID] = None,
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Get daily token consumption summary."""
        with self.session_maker() as session:
            query = session.query(AgentMetricsTokenSummary)
            
            if agent_id:
                query = query.filter(AgentMetricsTokenSummary.agent_id == agent_id)
            if user_id:
                query = query.filter(AgentMetricsTokenSummary.user_id == user_id)
            if start_date:
                query = query.filter(AgentMetricsTokenSummary.date >= start_date)
            if end_date:
                query = query.filter(AgentMetricsTokenSummary.date <= end_date)
            
            summaries = query.order_by(AgentMetricsTokenSummary.date.desc()).all()
            
            # Get agent names
            agent_ids = {s.agent_id for s in summaries}
            agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
            agent_map = {a.id: a.name for a in agents}
            
            items = []
            total_input = 0
            total_output = 0
            total_tokens = 0
            total_cost = 0
            
            for s in summaries:
                items.append({
                    "agent_id": str(s.agent_id),
                    "agent_name": agent_map.get(s.agent_id),
                    "date": s.date,
                    "input_tokens": s.total_input_tokens,
                    "output_tokens": s.total_output_tokens,
                    "total_tokens": s.total_tokens,
                    "cost": s.total_cost,
                    "request_count": s.request_count
                })
                total_input += s.total_input_tokens
                total_output += s.total_output_tokens
                total_tokens += s.total_tokens
                total_cost += s.total_cost
            
            return {
                "items": items,
                "total": {
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                    "total_tokens": total_tokens,
                    "total_cost": total_cost
                }
            }
    
    async def get_token_allocation(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        group_by: str = "agent"
    ) -> Dict:
        """Get token cost allocation by agent or user."""
        with self.session_maker() as session:
            query = session.query(AgentMetricsTokenSummary)
            
            if start_date:
                query = query.filter(AgentMetricsTokenSummary.date >= start_date)
            if end_date:
                query = query.filter(AgentMetricsTokenSummary.date <= end_date)
            
            summaries = query.all()
            
            if group_by == "agent":
                allocations = {}
                for s in summaries:
                    key = str(s.agent_id)
                    if key not in allocations:
                        agent = session.get(Agent, s.agent_id)
                        allocations[key] = {
                            "dimension": "agent",
                            "dimension_id": key,
                            "dimension_name": agent.name if agent else None,
                            "total_cost": 0,
                            "total_tokens": 0
                        }
                    allocations[key]["total_cost"] += s.total_cost
                    allocations[key]["total_tokens"] += s.total_tokens
            else:
                allocations = {}
                for s in summaries:
                    key = str(s.user_id)
                    if key not in allocations:
                        user = session.get(User, s.user_id)
                        allocations[key] = {
                            "dimension": "user",
                            "dimension_id": key,
                            "dimension_name": user.username if user else None,
                            "total_cost": 0,
                            "total_tokens": 0
                        }
                    allocations[key]["total_cost"] += s.total_cost
                    allocations[key]["total_tokens"] += s.total_tokens
            
            total_cost = sum(a["total_cost"] for a in allocations.values())
            
            for a in allocations.values():
                a["cost_ratio"] = a["total_cost"] / total_cost if total_cost > 0 else 0
            
            return {
                "total_cost": total_cost,
                "allocations": sorted(
                    allocations.values(),
                    key=lambda x: x["total_cost"],
                    reverse=True
                )
            }
    
    async def get_agent_ranking(
        self,
        sort_by: str = "sessions",
        order: str = "desc",
        limit: int = 10
    ) -> Dict:
        """Get agent performance ranking."""
        with self.session_maker() as session:
            # Get all agents with metrics
            agents = session.query(Agent).all()
            
            rankings = []
            for agent in agents:
                # Session count
                session_count = session.query(AgentMetricsSession).filter(
                    AgentMetricsSession.agent_id == agent.id
                ).count()
                
                # Total tokens
                llm_metrics = session.query(AgentMetricsLLM).filter(
                    AgentMetricsLLM.metrics_session_id.in_(
                        session.query(AgentMetricsSession.id).filter(
                            AgentMetricsSession.agent_id == agent.id
                        )
                    )
                ).all()
                total_tokens = sum(m.total_tokens for m in llm_metrics)
                total_cost = sum(m.token_cost or 0 for m in llm_metrics)
                
                # Average latency
                durations = [
                    s.total_duration_ms for s in session.query(AgentMetricsSession).filter(
                        AgentMetricsSession.agent_id == agent.id,
                        AgentMetricsSession.status == "success"
                    ).all()
                ]
                avg_latency = sum(durations) / len(durations) if durations else 0
                
                # Success rate
                total_sessions = session.query(AgentMetricsSession).filter(
                    AgentMetricsSession.agent_id == agent.id
                ).count()
                success_sessions = session.query(AgentMetricsSession).filter(
                    AgentMetricsSession.agent_id == agent.id,
                    AgentMetricsSession.status == "success"
                ).count()
                success_rate = success_sessions / total_sessions if total_sessions > 0 else 0
                
                rankings.append({
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "total_sessions": session_count,
                    "total_tokens": total_tokens,
                    "total_cost": total_cost,
                    "avg_latency_ms": avg_latency,
                    "success_rate": success_rate
                })
            
            # Sort
            sort_key = {
                "sessions": "total_sessions",
                "tokens": "total_tokens",
                "cost": "total_cost",
                "latency": "avg_latency_ms"
            }.get(sort_by, "total_sessions")
            
            rankings.sort(
                key=lambda x: x[sort_key],
                reverse=(order == "desc")
            )
            
            # Add rank
            for i, r in enumerate(rankings[:limit], 1):
                r["rank"] = i
            
            return {
                "rankings": rankings[:limit]
            }
    
    async def get_user_ranking(
        self,
        sort_by: str = "tokens",
        order: str = "desc",
        limit: int = 10
    ) -> Dict:
        """Get user token consumption ranking."""
        with self.session_maker() as session:
            # Get all users with metrics
            users = session.query(User).all()
            
            rankings = []
            for user in users:
                # Session count
                session_count = session.query(AgentMetricsSession).filter(
                    AgentMetricsSession.user_id == user.id
                ).count()
                
                # Total tokens
                llm_metrics = session.query(AgentMetricsLLM).filter(
                    AgentMetricsLLM.metrics_session_id.in_(
                        session.query(AgentMetricsSession.id).filter(
                            AgentMetricsSession.user_id == user.id
                        )
                    )
                ).all()
                total_tokens = sum(m.total_tokens for m in llm_metrics)
                total_cost = sum(m.token_cost or 0 for m in llm_metrics)
                
                rankings.append({
                    "user_id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "total_sessions": session_count,
                    "total_tokens": total_tokens,
                    "total_cost": total_cost
                })
            
            # Sort
            sort_key = {
                "tokens": "total_tokens",
                "cost": "total_cost",
                "sessions": "total_sessions"
            }.get(sort_by, "total_tokens")
            
            rankings.sort(
                key=lambda x: x[sort_key],
                reverse=(order == "desc")
            )
            
            # Add rank
            for i, r in enumerate(rankings[:limit], 1):
                r["rank"] = i
            
            return {
                "rankings": rankings[:limit]
            }


# Global instance
metrics_service = MetricsService()