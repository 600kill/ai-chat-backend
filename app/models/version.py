"""Agent 版本快照模型。

快照为完整自包含配置（工具存完整定义而非仅 id），保证工具表/知识库绑定
后续变更后，历史版本仍可精确复现；回滚为软回滚（新建版本，不覆盖历史）。
"""

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models.base import BaseModel


class AgentVersion(BaseModel, table=True):
    """Agent 版本快照。version_no 在 Agent 内从 1 递增。"""

    __tablename__ = "agent_version"
    __table_args__ = (UniqueConstraint("agent_id", "version_no", name="uq_agent_version_no"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    agent_id: UUID = Field(foreign_key="agent.id", index=True)
    version_no: int = Field(index=True)

    # 完整快照：基础配置 + tools 完整定义数组 + kb_ids（含 name 供展示）
    snapshot: dict = Field(sa_type=JSON, nullable=False)

    note: Optional[str] = None
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")

    agent: Optional["Agent"] = Relationship(back_populates="versions")
