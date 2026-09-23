"""This file contains the session model for the application."""

from typing import (
    TYPE_CHECKING,
    List,
    Optional,
)
from uuid import UUID

from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.agent import Agent
    from app.models.metrics import AgentMetricsSession


class Session(BaseModel, table=True):
    """Session model for storing chat sessions.

    Attributes:
        id: The primary key
        user_id: Foreign key to the user
        agent_id: Foreign key to the agent (optional)
        name: Name of the session (defaults to empty string)
        username: Display name copied from the user at session creation
        created_at: When the session was created
        messages: Relationship to session messages
        user: Relationship to the session owner
        agent: Relationship to the associated agent
    """

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    agent_id: Optional[UUID] = Field(default=None, foreign_key="agent.id")
    name: str = Field(default="")
    username: Optional[str] = Field(default=None)
    user: "User" = Relationship(back_populates="sessions")
    agent: Optional["Agent"] = Relationship(back_populates="sessions")
    metrics: List["AgentMetricsSession"] = Relationship(back_populates="session")
