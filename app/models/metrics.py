"""Metrics models for tracking agent execution performance."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel, Relationship, JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session
    from app.models.agent import Agent, Tool
    from app.models.user import User


class AgentMetricsSession(BaseModel, table=True):
    """Session-level performance metrics for agent execution."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    agent_id: UUID = Field(foreign_key="agent.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    started_at: Optional[datetime] = Field(default=None)
    ended_at: Optional[datetime] = Field(default=None)
    total_duration_ms: int = Field(default=0)
    status: str = Field(default="running")
    error_message: Optional[str] = None
    
    # Relationships
    session: "Session" = Relationship(back_populates="metrics")
    agent: "Agent" = Relationship()
    user: "User" = Relationship()
    
    llm_metrics: List["AgentMetricsLLM"] = Relationship(back_populates="metrics_session")
    vector_metrics: List["AgentMetricsVector"] = Relationship(back_populates="metrics_session")
    tool_metrics: List["AgentMetricsTool"] = Relationship(back_populates="metrics_session")
    node_metrics: List["AgentMetricsNode"] = Relationship(back_populates="metrics_session")


class AgentMetricsLLM(BaseModel, table=True):
    """LLM inference performance metrics."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    metrics_session_id: UUID = Field(foreign_key="agentmetricssession.id", index=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    llm_model: str = Field(nullable=False)
    inference_duration_ms: int = Field(default=0)
    ttft_ms: Optional[int] = Field(default=None)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    token_cost: Optional[float] = Field(default=None)
    status: str = Field(default="success")
    error_message: Optional[str] = None
    
    metrics_session: "AgentMetricsSession" = Relationship(back_populates="llm_metrics")


class AgentMetricsVector(BaseModel, table=True):
    """Vector search performance metrics."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    metrics_session_id: UUID = Field(foreign_key="agentmetricssession.id", index=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    search_duration_ms: int = Field(default=0)
    results_count: int = Field(default=0)
    query_length: Optional[int] = Field(default=None)
    memory_type: Optional[str] = Field(default=None)
    status: str = Field(default="success")
    
    metrics_session: "AgentMetricsSession" = Relationship(back_populates="vector_metrics")


class AgentMetricsTool(BaseModel, table=True):
    """Tool call performance metrics."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    metrics_session_id: UUID = Field(foreign_key="agentmetricssession.id", index=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    tool_name: str = Field(nullable=False)
    tool_id: Optional[UUID] = Field(default=None, foreign_key="tool.id")
    call_duration_ms: int = Field(default=0)
    input_params: Optional[dict] = Field(default=None, sa_type=JSON)
    output_result: Optional[str] = Field(default=None)
    status: str = Field(default="success")
    error_message: Optional[str] = None
    
    metrics_session: "AgentMetricsSession" = Relationship(back_populates="tool_metrics")
    tool: Optional["Tool"] = Relationship()


class AgentMetricsNode(BaseModel, table=True):
    """LangGraph node execution metrics."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    metrics_session_id: UUID = Field(foreign_key="agentmetricssession.id", index=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    node_name: str = Field(nullable=False)
    node_type: str = Field(nullable=False)
    execution_order: int = Field(default=0)
    duration_ms: int = Field(default=0)
    input_snapshot: Optional[dict] = Field(default=None, sa_type=JSON)
    output_snapshot: Optional[dict] = Field(default=None, sa_type=JSON)
    status: str = Field(default="success")
    
    metrics_session: "AgentMetricsSession" = Relationship(back_populates="node_metrics")


class AgentMetricsConcurrent(BaseModel, table=True):
    """Concurrent monitoring snapshot."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    agent_id: UUID = Field(foreign_key="agent.id", index=True)
    active_sessions: int = Field(default=0)
    active_tasks: int = Field(default=0)
    recorded_at: datetime = Field(nullable=False)
    
    agent: "Agent" = Relationship()


class AgentMetricsTokenSummary(BaseModel, table=True):
    """Daily token consumption summary."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    agent_id: UUID = Field(foreign_key="agent.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    date: datetime = Field(nullable=False, index=True)
    total_input_tokens: int = Field(default=0)
    total_output_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    total_cost: float = Field(default=0.0)
    request_count: int = Field(default=0)
    
    agent: "Agent" = Relationship()
    user: "User" = Relationship()