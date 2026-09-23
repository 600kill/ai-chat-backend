"""Schemas for Agent test session management."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse


class AgentSessionCreate(BaseModel):
    """Schema for creating an agent test session."""
    
    agent_id: UUID = Field(description="Agent ID")
    user_id: int = Field(description="用户 ID")


class AgentSessionResponse(BaseModel):
    """Schema for agent session response."""
    
    id: str = Field(description="会话 ID")
    agent_id: UUID = Field(description="Agent ID")
    agent_name: Optional[str] = Field(None, description="Agent 名称")
    user_id: int = Field(description="用户 ID")
    status: str = Field(description="会话状态")
    created_at: datetime = Field(description="创建时间")


class ChatMessage(BaseModel):
    """Schema for chat message."""
    
    role: str = Field(description="角色: user/assistant/tool")
    content: str = Field(description="消息内容")
    tool_calls: Optional[List[dict]] = Field(None, description="工具调用记录")
    node_name: Optional[str] = Field(None, description="执行的节点名称")


class ChatRequest(BaseModel):
    """Schema for chat request."""

    message: str = Field(description="用户消息")
    stream: bool = Field(default=False, description="是否流式响应")
    # 可选：按版本快照运行（阶段 6）。version_id 优先；两者都不传则用 Agent 当前配置
    version_id: Optional[str] = Field(default=None, description="版本快照 ID")
    version_no: Optional[int] = Field(default=None, ge=1, description="Agent 内版本号（v1/v2/v3）")


class ChatResponse(BaseModel):
    """Schema for chat response."""
    
    role: str = Field(description="角色")
    content: str = Field(description="回复内容")
    tool_calls: Optional[List[dict]] = Field(None, description="工具调用")
    node_name: Optional[str] = Field(None, description="当前节点")


class AgentSessionListResponse(BaseResponse):
    """Schema for agent session list response."""
    
    data: dict = Field(description="响应数据")