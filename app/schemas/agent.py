"""Schemas for Agent and Tool management."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse


# ==================== Tool Schemas ====================

class ToolBase(BaseModel):
    """Base schema for tool data."""
    
    name: str = Field(description="工具名称")
    description: Optional[str] = Field(None, description="功能说明")
    function_name: str = Field(description="Python 函数名")
    input_schema: Optional[dict] = Field(None, description="入参定义 JSON Schema")
    output_schema: Optional[dict] = Field(None, description="出参定义 JSON Schema")
    example: Optional[str] = Field(None, description="调用示例")
    status: str = Field(default="enabled", description="状态: enabled/disabled")


class ToolCreate(ToolBase):
    """Schema for creating a new tool."""
    pass


class ToolUpdate(BaseModel):
    """Schema for updating tool information."""
    
    name: Optional[str] = Field(None, description="工具名称")
    description: Optional[str] = Field(None, description="功能说明")
    input_schema: Optional[dict] = Field(None, description="入参定义")
    output_schema: Optional[dict] = Field(None, description="出参定义")
    example: Optional[str] = Field(None, description="调用示例")
    status: Optional[str] = Field(None, description="状态")


class ToolResponse(BaseModel):
    """Schema for tool response."""
    
    id: UUID = Field(description="工具 ID")
    name: str = Field(description="工具名称")
    description: Optional[str] = Field(description="功能说明")
    function_name: str = Field(description="Python 函数名")
    input_schema: Optional[dict] = Field(description="入参定义")
    output_schema: Optional[dict] = Field(description="出参定义")
    example: Optional[str] = Field(description="调用示例")
    status: str = Field(description="状态")
    created_at: datetime = Field(description="创建时间")


class ToolListResponse(BaseResponse):
    """Schema for tool list response."""
    
    data: dict = Field(description="响应数据")


# ==================== Agent Schemas ====================

class AgentBase(BaseModel):
    """Base schema for agent data."""

    name: str = Field(description="Agent 名称")
    description: Optional[str] = Field(None, description="功能描述")
    graph_config: Optional[dict] = Field(None, description="LangGraph 配置")
    status: str = Field(default="draft", description="状态: active/inactive/draft")
    system_prompt: Optional[str] = Field(None, description="系统提示词（覆盖默认模板）")
    model_name: Optional[str] = Field(None, description="绑定模型名称（None 用平台首选模型）")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="采样温度")
    max_tokens: Optional[int] = Field(None, ge=1, description="最大输出 token 数")


class AgentCreate(AgentBase):
    """Schema for creating a new agent."""

    tool_ids: Optional[List[UUID]] = Field([], description="关联的工具 ID 列表")
    kb_ids: Optional[List[UUID]] = Field([], description="绑定的知识库 ID 列表")


class AgentUpdate(BaseModel):
    """Schema for updating agent information."""

    name: Optional[str] = Field(None, description="Agent 名称")
    description: Optional[str] = Field(None, description="功能描述")
    graph_config: Optional[dict] = Field(None, description="LangGraph 配置")
    status: Optional[str] = Field(None, description="状态")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    model_name: Optional[str] = Field(None, description="绑定模型名称")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="采样温度")
    max_tokens: Optional[int] = Field(None, ge=1, description="最大输出 token 数")
    tool_ids: Optional[List[UUID]] = Field(None, description="关联的工具 ID 列表")
    # None=不修改绑定；传空列表=解绑全部
    kb_ids: Optional[List[UUID]] = Field(None, description="绑定的知识库 ID 列表")


class AgentResponse(BaseModel):
    """Schema for agent response."""

    id: UUID = Field(description="Agent ID")
    name: str = Field(description="Agent 名称")
    description: Optional[str] = Field(description="功能描述")
    graph_config: Optional[dict] = Field(description="LangGraph 配置")
    status: str = Field(description="状态")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    model_name: Optional[str] = Field(None, description="绑定模型名称")
    temperature: Optional[float] = Field(None, description="采样温度")
    max_tokens: Optional[int] = Field(None, description="最大输出 token 数")
    tool_count: int = Field(description="关联工具数量")
    created_at: datetime = Field(description="创建时间")
    updated_at: Optional[datetime] = Field(description="更新时间")


class AgentDetailResponse(AgentResponse):
    """Schema for detailed agent response."""
    
    tools: List[ToolResponse] = Field(description="关联的工具列表")


class AgentListResponse(BaseResponse):
    """Schema for agent list response."""
    
    data: dict = Field(description="响应数据")


# ==================== Batch Operation Schemas ====================

class BatchOperationRequest(BaseModel):
    """Schema for batch operations."""
    
    ids: List[UUID] = Field(description="要操作的 Agent ID 列表")
    action: str = Field(description="操作类型: enable/disable/delete")
    data: Optional[dict] = Field(None, description="批量更新时的数据")


class BatchOperationResponse(BaseResponse):
    """Schema for batch operation response."""
    
    success_count: int = Field(description="成功数量")
    failed_count: int = Field(description="失败数量")
    failed_ids: List[UUID] = Field(description="失败的 ID 列表")