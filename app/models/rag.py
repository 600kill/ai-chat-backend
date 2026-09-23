"""RAG 知识库相关模型：知识库 / 文档 / 文档分片（pgvector）/ Agent-知识库 关联。"""

from typing import List, Optional
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship, SQLModel

from app.core.config import settings
from app.models.base import BaseModel


class KnowledgeBase(BaseModel, table=True):
    """知识库。一个知识库含多个文档，文档切分为向量分片。"""

    __tablename__ = "knowledge_base"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, max_length=200)
    description: Optional[str] = None
    is_public: bool = Field(default=False, index=True)
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    # 切片/召回参数：NULL 表示跟随全局 settings（让 KB 设置真正驱动检索行为）
    chunk_size: Optional[int] = Field(default=None)
    chunk_overlap: Optional[int] = Field(default=None)
    top_k: Optional[int] = Field(default=None)

    documents: List["KnowledgeDocument"] = Relationship(
        back_populates="knowledge_base",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class KnowledgeDocument(BaseModel, table=True):
    """知识库文档（上传的原始文件）。"""

    __tablename__ = "knowledge_document"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kb_id: UUID = Field(foreign_key="knowledge_base.id", index=True)
    filename: str = Field(max_length=500)
    # sha256，同知识库内去重
    file_hash: str = Field(index=True, max_length=64)
    # processing -> ready / failed
    status: str = Field(default="processing", index=True)
    chunk_count: int = Field(default=0)
    char_count: int = Field(default=0)
    error: Optional[str] = None

    knowledge_base: "KnowledgeBase" = Relationship(back_populates="documents")
    chunks: List["KnowledgeChunk"] = Relationship(
        back_populates="document",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class KnowledgeChunk(SQLModel, table=True):
    """文档分片：原文 + embedding（维度由 RAG_EMBEDDING_DIM 决定，换模型需重建表）。"""

    __tablename__ = "knowledge_chunk"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_id: UUID = Field(foreign_key="knowledge_document.id", index=True)
    kb_id: UUID = Field(foreign_key="knowledge_base.id", index=True)
    chunk_index: int = Field(default=0)
    content: str = Field(sa_column=Column(Text, nullable=False))
    embedding: list[float] = Field(
        sa_column=Column(Vector(settings.RAG_EMBEDDING_DIM), nullable=False)
    )

    document: "KnowledgeDocument" = Relationship(back_populates="chunks")


class AgentKnowledgeBase(SQLModel, table=True):
    """Agent 与知识库的多对多关联。"""

    __tablename__ = "agent_knowledge_base"

    agent_id: UUID = Field(foreign_key="agent.id", primary_key=True)
    kb_id: UUID = Field(foreign_key="knowledge_base.id", primary_key=True)
