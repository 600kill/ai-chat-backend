"""API v1 router configuration.

This module sets up the main API router and includes all sub-routers for different
endpoints like authentication, chatbot functionality, agent management, public market,
admin operations, private agent/tool management, and performance metrics.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chatbot import router as chatbot_router
from app.api.v1.agents import router as agent_router
from app.api.v1.agent_services import router as agent_session_router
from app.api.v1.market import router as market_router
from app.api.v1.admin import router as admin_router
from app.api.v1.my import router as my_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.evaluation import router as evaluation_router
from app.api.v1.versions import router as versions_router
from app.core.logging import logger

api_router = APIRouter()

# Include routers
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(agent_router, prefix="/agents", tags=["agents"])
api_router.include_router(agent_session_router, prefix="/agent-sessions", tags=["agent-sessions"])
api_router.include_router(market_router, prefix="/market", tags=["market"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(my_router, prefix="/my", tags=["my"])
api_router.include_router(metrics_router, prefix="/metrics", tags=["metrics"])
# 知识库路由内部已含全路径（/knowledge-bases/* 与 /agents/{id}/knowledge-bases），不加 prefix
api_router.include_router(knowledge_router)
# 版本路由内部已含全路径（/agents/{id}/versions/*），不加 prefix
api_router.include_router(versions_router)
# 评测路由（/evaluation/*）
api_router.include_router(evaluation_router)


@api_router.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        dict: Health status information.
    """
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}
