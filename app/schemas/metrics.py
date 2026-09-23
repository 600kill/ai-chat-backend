"""Pydantic schemas for metrics API."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class MetricsSessionDetailResponse(BaseModel):
    """Response schema for session performance detail."""
    
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[dict] = None


class MetricsAgentStatsResponse(BaseModel):
    """Response schema for agent statistics."""
    
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[dict] = None


class MetricsSessionListResponse(BaseModel):
    """Response schema for session list."""
    
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[dict] = None


class MetricsMarketStatsResponse(BaseModel):
    """Response schema for market statistics."""
    
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[dict] = None


class MetricsConcurrentResponse(BaseModel):
    """Response schema for concurrent statistics."""
    
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[dict] = None


class MetricsTokenDailyResponse(BaseModel):
    """Response schema for daily token consumption."""
    
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[dict] = None


class MetricsTokenAllocationResponse(BaseModel):
    """Response schema for token cost allocation."""
    
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[dict] = None


class MetricsAgentRankingResponse(BaseModel):
    """Response schema for agent ranking."""
    
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[dict] = None


class MetricsUserRankingResponse(BaseModel):
    """Response schema for user ranking."""
    
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[dict] = None