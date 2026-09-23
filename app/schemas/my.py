"""Schemas for private agent and tool management."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MyAgentCreate(BaseModel):
    """Schema for creating private agent."""

    name: str = Field(description="Agent name")
    description: Optional[str] = Field(None, description="Agent description")
    graph_config: Optional[dict] = Field(None, description="Graph config")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    model_name: Optional[str] = Field(None, description="绑定模型名称")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="采样温度")
    max_tokens: Optional[int] = Field(None, ge=1, description="最大输出 token 数")
    tool_ids: Optional[List[UUID]] = Field([], description="Tool IDs")
    kb_ids: Optional[List[UUID]] = Field([], description="绑定的知识库 ID 列表")


class MyAgentUpdate(BaseModel):
    """Schema for updating private agent."""

    name: Optional[str] = Field(None, description="Agent name")
    description: Optional[str] = Field(None, description="Agent description")
    graph_config: Optional[dict] = Field(None, description="Graph config")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    model_name: Optional[str] = Field(None, description="绑定模型名称")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="采样温度")
    max_tokens: Optional[int] = Field(None, ge=1, description="最大输出 token 数")
    status: Optional[str] = Field(None, description="Agent status")
    tool_ids: Optional[List[UUID]] = Field(None, description="Tool IDs")
    kb_ids: Optional[List[UUID]] = Field(None, description="绑定的知识库 ID 列表（全量覆盖，空列表=解绑全部）")


class MyAgentResponse(BaseModel):
    """Schema for private agent response."""
    
    id: UUID = Field(description="Agent ID")
    name: str = Field(description="Agent name")
    description: Optional[str] = Field(None, description="Agent description")
    status: str = Field(description="Agent status")
    tool_count: int = Field(description="Tool count")
    created_at: datetime = Field(description="Created time")


class MyAgentListResponse(BaseModel):
    """Schema for private agent list response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: dict = Field(description="Response data")


class MyToolCreate(BaseModel):
    """Schema for creating private tool."""
    
    name: str = Field(description="Tool name")
    description: Optional[str] = Field(None, description="Tool description")
    function_name: str = Field(description="Function name")
    input_schema: Optional[dict] = Field(None, description="Input schema")
    output_schema: Optional[dict] = Field(None, description="Output schema")
    example: Optional[str] = Field(None, description="Example")


class MyToolUpdate(BaseModel):
    """Schema for updating private tool."""
    
    name: Optional[str] = Field(None, description="Tool name")
    description: Optional[str] = Field(None, description="Tool description")
    input_schema: Optional[dict] = Field(None, description="Input schema")
    output_schema: Optional[dict] = Field(None, description="Output schema")
    example: Optional[str] = Field(None, description="Example")
    status: Optional[str] = Field(None, description="Tool status")


class MyToolResponse(BaseModel):
    """Schema for private tool response."""
    
    id: UUID = Field(description="Tool ID")
    name: str = Field(description="Tool name")
    description: Optional[str] = Field(None, description="Tool description")
    function_name: str = Field(description="Function name")
    status: str = Field(description="Tool status")
    created_at: datetime = Field(description="Created time")


class MyToolListResponse(BaseModel):
    """Schema for private tool list response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: dict = Field(description="Response data")


class BatchOperationRequest(BaseModel):
    """Schema for batch operation request."""
    
    ids: List[UUID] = Field(description="Agent IDs")
    action: str = Field(description="Action: enable/disable/delete")


class BatchOperationResponse(BaseModel):
    """Schema for batch operation response."""
    
    code: int = Field(default=200, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: dict = Field(description="Response data")