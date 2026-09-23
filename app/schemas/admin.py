"""Schemas for admin API."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PrivateAgentListItem(BaseModel):
    """Schema for private agent list item."""
    
    id: UUID = Field(description="Agent ID")
    name: str = Field(description="Agent name")
    description: Optional[str] = Field(None, description="Agent description")
    owner_id: Optional[int] = Field(None, description="Owner ID")
    owner_name: Optional[str] = Field(None, description="Owner name")
    status: str = Field(description="Agent status")
    is_public: bool = Field(description="Is public")
    created_at: datetime = Field(description="Created time")


class PrivateAgentListResponse(BaseModel):
    """Schema for private agent list response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: dict = Field(description="Response data")


class PublishAgentRequest(BaseModel):
    """Schema for publish agent request."""
    
    publish_note: Optional[str] = Field(None, description="Publish note")


class PublishAgentResponse(BaseModel):
    """Schema for publish agent response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="收录成功", description="Response message")
    data: dict = Field(description="Response data")


class UnpublishAgentRequest(BaseModel):
    """Schema for unpublish agent request."""
    
    unpublish_reason: Optional[str] = Field(None, description="Unpublish reason")


class UnpublishAgentResponse(BaseModel):
    """Schema for unpublish agent response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="下架成功", description="Response message")
    data: dict = Field(description="Response data")


class AgentStatsResponse(BaseModel):
    """Schema for agent stats response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: dict = Field(description="Response data")


class MarketStatsResponse(BaseModel):
    """Schema for market stats response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: dict = Field(description="Response data")