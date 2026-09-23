import os
os.environ['APP_ENV'] = 'test'

from sqlmodel import Session, delete
from app.services.database import database_service
from app.models.user import User
from app.models.agent import Agent, AgentTool, Tool
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

with Session(database_service.engine) as session:
    session.execute(delete(AgentMetricsTokenSummary))
    session.execute(delete(AgentMetricsConcurrent))
    session.execute(delete(AgentMetricsNode))
    session.execute(delete(AgentMetricsTool))
    session.execute(delete(AgentMetricsVector))
    session.execute(delete(AgentMetricsLLM))
    session.execute(delete(AgentMetricsSession))
    session.execute(delete(ChatSession))
    session.execute(delete(AgentTool))
    session.execute(delete(Tool))
    session.execute(delete(Agent))
    session.execute(delete(User))
    session.commit()
    print('Cleanup done')