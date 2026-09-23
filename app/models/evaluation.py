"""评测模块模型：测试集 / 用例 / 运行批次 / 用例结果。"""

from datetime import datetime, UTC
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Text, UniqueConstraint
from sqlalchemy import DateTime
from sqlmodel import Field

from app.models.base import BaseModel


def _json_column() -> Any:
    return Field(sa_type=JSON, nullable=True)


class EvaluationTestSet(BaseModel, table=True):
    """评测测试集。"""

    __tablename__ = "evaluation_test_set"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    owner_id: int = Field(foreign_key="user.id", index=True)
    case_count: int = Field(default=0)


class EvaluationCase(BaseModel, table=True):
    """评测用例。type: answer / tool / rag"""

    __tablename__ = "evaluation_case"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    testset_id: UUID = Field(foreign_key="evaluation_test_set.id", index=True)
    type: str = Field(default="answer")  # answer / tool / rag
    question: str = Field(sa_type=Text)
    expected_answer: Optional[str] = Field(default=None, sa_type=Text)
    expected_tool: Optional[str] = None  # 工具名（function_name）
    expected_arguments: Optional[dict] = _json_column()  # 关键参数（子集匹配）
    expected_document_ids: Optional[list] = _json_column()  # RAG 期望命中文档
    order: int = Field(default=0)


class EvaluationRun(BaseModel, table=True):
    """一次评测运行批次。version_id 指定快照——Runner 必须按快照配置执行。"""

    __tablename__ = "evaluation_run"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    testset_id: UUID = Field(foreign_key="evaluation_test_set.id", index=True)
    agent_id: UUID = Field(foreign_key="agent.id", index=True)
    version_id: UUID = Field(foreign_key="agent_version.id")
    judge_model: Optional[str] = None
    status: str = Field(default="pending", index=True)  # pending/running/completed/failed
    stats: Optional[dict] = _json_column()
    total: int = Field(default=0)
    success: int = Field(default=0)
    failed: int = Field(default=0)
    started_at: Optional[datetime] = Field(default=None, sa_column=DateTime(timezone=True))
    ended_at: Optional[datetime] = Field(default=None, sa_column=DateTime(timezone=True))
    error: Optional[str] = Field(default=None, sa_type=Text)
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")


class EvaluationCaseResult(BaseModel, table=True):
    """run 内单 case 执行结果与判分。"""

    __tablename__ = "evaluation_case_result"
    __table_args__ = (UniqueConstraint("run_id", "case_id", name="uq_eval_result_case"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="evaluation_run.id", index=True)
    case_id: UUID = Field(foreign_key="evaluation_case.id", index=True)
    status: str = Field(default="pending", index=True)  # pending/running/completed/failed
    agent_answer: Optional[str] = Field(default=None, sa_type=Text)
    actual_tool_calls: Optional[list] = _json_column()
    actual_document_ids: Optional[list] = _json_column()
    # scores: {factuality, instruction, completeness, tool: exact|partial|miss,
    #          tool_score: 0|0.5|1, rag_recall, rationale}
    scores: Optional[dict] = _json_column()
    overall_score: Optional[float] = None
    latency_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    error: Optional[str] = Field(default=None, sa_type=Text)
    judged_at: Optional[datetime] = Field(default=None, sa_column=DateTime(timezone=True))
