"""Test fixtures and configuration for integration tests using real database."""

import os
import uuid
import pytest
from sqlmodel import Session, create_engine, delete

os.environ["APP_ENV"] = "test"

from app.core.config import settings
from app.models.agent import Agent, Tool, AgentTool
from app.models.user import User
from app.models.session import Session as ChatSession
from app.models.metrics import (
    AgentMetricsSession,
    AgentMetricsLLM,
    AgentMetricsVector,
    AgentMetricsTool,
    AgentMetricsNode,
    AgentMetricsConcurrent,
    AgentMetricsTokenSummary,
)


@pytest.fixture(scope="session")
def db_engine():
    """Create database engine for testing."""
    connection_url = (
        f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
    engine = create_engine(connection_url, echo=False)
    yield engine


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for each test."""
    with Session(db_engine) as session:
        yield session


@pytest.fixture(scope="function")
def test_user(db_session):
    """Create and return a test user."""
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        username=f"testuser_{uuid.uuid4().hex[:8]}"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user


@pytest.fixture(scope="function")
def test_admin_user(db_session):
    """Create and return a test admin user."""
    user = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        username=f"adminuser_{uuid.uuid4().hex[:8]}",
        role="admin"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user


@pytest.fixture(scope="function")
def test_agent(db_session, test_user):
    """Create and return a private test agent."""
    agent = Agent(
        id=uuid.uuid4(),
        name="Test Agent",
        description="Test agent description",
        status="active",
        is_public=False,
        owner_id=test_user.id
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    yield agent


@pytest.fixture(scope="function")
def test_public_agent(db_session, test_admin_user):
    """Create and return a public test agent."""
    agent = Agent(
        id=uuid.uuid4(),
        name="Public Test Agent",
        description="Public test agent description",
        status="active",
        is_public=True,
        owner_id=test_admin_user.id,
        published_by=test_admin_user.id
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    yield agent


@pytest.fixture(scope="function")
def test_metrics_session(db_session, test_agent, test_user):
    """Create and return a test metrics session."""
    from datetime import datetime
    metrics_session = AgentMetricsSession(
        id=uuid.uuid4(),
        session_id=str(uuid.uuid4()),
        agent_id=test_agent.id,
        user_id=test_user.id,
        started_at=datetime.now(),
        status="running"
    )
    db_session.add(metrics_session)
    db_session.commit()
    db_session.refresh(metrics_session)
    yield metrics_session


@pytest.fixture(scope="function", autouse=True)
def cleanup_db(db_session):
    """Clean up database after each test."""
    yield
    try:
        db_session.rollback()
    except Exception:
        pass