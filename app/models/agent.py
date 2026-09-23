"""Agent and Tool models for the application."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel, Relationship, JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


class AgentTool(SQLModel, table=True):
    """Association table for Agent-Tool relationships."""

    agent_id: UUID = Field(foreign_key="agent.id", primary_key=True)
    tool_id: UUID = Field(foreign_key="tool.id", primary_key=True)
    priority: int = Field(default=1)
    is_public_binding: bool = Field(default=False)


class Tool(BaseModel, table=True):
    """Tool model for storing available tools."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    function_name: str = Field(index=True)
    input_schema: Optional[dict] = Field(default=None, sa_type=JSON)
    output_schema: Optional[dict] = Field(default=None, sa_type=JSON)
    example: Optional[str] = None
    status: str = Field(default="enabled")
    
    is_public: bool = Field(default=False, index=True)
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    copy_count: int = Field(default=0)
    source_tool_id: Optional[UUID] = Field(default=None, foreign_key="tool.id")
    
    agents: List["Agent"] = Relationship(
        back_populates="tools",
        link_model=AgentTool
    )


class Agent(BaseModel, table=True):
    """Agent model for storing AI agents."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    graph_config: Optional[dict] = Field(default=None, sa_type=JSON)
    status: str = Field(default="draft")

    # ===== Runtime 运行时配置（Agent 级别覆盖全局默认）=====
    system_prompt: Optional[str] = Field(default=None)
    model_name: Optional[str] = Field(default=None, index=True)
    temperature: Optional[float] = Field(default=None)
    max_tokens: Optional[int] = Field(default=None)
    
    is_public: bool = Field(default=False, index=True)
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    copy_count: int = Field(default=0)
    session_count: int = Field(default=0)
    published_at: Optional[datetime] = None
    published_by: Optional[int] = Field(default=None, foreign_key="user.id")
    source_agent_id: Optional[UUID] = Field(default=None, foreign_key="agent.id")
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    
    sessions: List["Session"] = Relationship(back_populates="agent")
    tools: List["Tool"] = Relationship(
        back_populates="agents",
        link_model=AgentTool
    )
    versions: List["AgentVersion"] = Relationship(back_populates="agent")


from app.models.session import Session  # noqa: E402
from app.models.version import AgentVersion  # noqa: E402