"""Schemas for public market API."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PublicAgentListItem(BaseModel):
    """Schema for public agent list item."""
    
    id: UUID = Field(description="Agent ID")
    name: str = Field(description="Agent name")
    description: Optional[str] = Field(None, description="Agent description")
    tool_count: int = Field(description="Number of tools")
    copy_count: int = Field(description="Copy count")
    session_count: int = Field(description="Session count")
    published_at: Optional[datetime] = Field(None, description="Published time")
    publisher_name: Optional[str] = Field(None, description="Publisher name")


class PublicAgentListResponse(BaseModel):
    """Schema for public agent list response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: dict = Field(description="Response data")


class PublicAgentDetail(BaseModel):
    """Schema for public agent detail."""
    
    id: UUID = Field(description="Agent ID")
    name: str = Field(description="Agent name")
    description: Optional[str] = Field(None, description="Agent description")
    graph_config: Optional[dict] = Field(None, description="Graph config")
    tools: List[dict] = Field(default=[], description="Associated tools")
    copy_count: int = Field(description="Copy count")
    session_count: int = Field(description="Session count")
    published_at: Optional[datetime] = Field(None, description="Published time")
    publisher_name: Optional[str] = Field(None, description="Publisher name")


class PublicAgentDetailResponse(BaseModel):
    """Schema for public agent detail response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: PublicAgentDetail = Field(description="Response data")


class CopyAgentRequest(BaseModel):
    """Schema for copy agent request."""
    
    new_name: Optional[str] = Field(None, description="New agent name")


class CopyAgentResponse(BaseModel):
    """Schema for copy agent response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="复制成功", description="Response message")
    data: dict = Field(description="Response data")


class CreateSessionRequest(BaseModel):
    """Schema for create session request."""
    
    name: Optional[str] = Field(None, description="Session name")


class CreateSessionResponse(BaseModel):
    """Schema for create session response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: dict = Field(description="Response data")


class WorkflowResponse(BaseModel):
    """Schema for workflow response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: dict = Field(description="Response data")