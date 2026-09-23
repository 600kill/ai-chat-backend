"""知识库模块 Pydantic schemas。"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="知识库名称")
    description: Optional[str] = Field(None, description="描述")
    is_public: bool = Field(False, description="是否公开")
    chunk_size: Optional[int] = Field(None, ge=100, le=5000, description="切片大小（默认跟随全局 600）")
    chunk_overlap: Optional[int] = Field(None, ge=0, le=500, description="切片重叠（默认 80）")
    top_k: Optional[int] = Field(None, ge=1, le=20, description="召回条数（默认跟随全局 4）")


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    is_public: Optional[bool] = None
    chunk_size: Optional[int] = Field(None, ge=100, le=5000)
    chunk_overlap: Optional[int] = Field(None, ge=0, le=500)
    top_k: Optional[int] = Field(None, ge=1, le=20)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="检索问题")
    top_k: Optional[int] = Field(None, ge=1, le=20, description="召回条数")
    score_threshold: float = Field(0.0, ge=0.0, le=1.0, description="相似度阈值（0 不过滤）")


class AgentKbBindRequest(BaseModel):
    kb_ids: list[UUID] = Field(description="要绑定的知识库 ID 列表（全量覆盖）")
