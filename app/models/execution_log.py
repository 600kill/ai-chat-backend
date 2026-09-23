"""Execution log model for tracking agent execution."""

from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel, Relationship, JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


class ExecutionLog(BaseModel, table=True):
    """Execution log model for tracking agent execution.

    Attributes:
        id: The primary key (UUID)
        session_id: The session ID
        node_name: The name of the executed node
        node_type: The type of node (think/action/tool/decision)
        input_data: Input data for the node
        output_data: Output data from the node
        tool_calls: Tool calls made during execution
        status: Execution status (success/failed/running)
        error_message: Error message if failed
        execution_time: Execution time in milliseconds
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    node_name: str = Field(index=True)
    node_type: str = Field(index=True)
    input_data: Optional[dict] = Field(default=None, sa_type=JSON)
    output_data: Optional[dict] = Field(default=None, sa_type=JSON)
    tool_calls: Optional[list] = Field(default=None, sa_type=JSON)
    status: str = Field(default="running")
    error_message: Optional[str] = None
    execution_time: Optional[int] = None  # milliseconds