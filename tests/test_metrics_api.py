"""API tests for metrics endpoints."""

import pytest
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi.testclient import TestClient
from main import app
from app.models.user import User

client = TestClient(app)


class TestMetricsAPI:
    """Test cases for metrics API endpoints."""

    def test_get_session_detail_requires_auth(self):
        """Test GET /metrics/sessions/{session_id} requires authentication."""
        session_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/metrics/sessions/{session_id}")
        
        assert response.status_code == 401

    def test_get_session_list_requires_auth(self):
        """Test GET /metrics/sessions requires authentication."""
        response = client.get("/api/v1/metrics/sessions")
        
        assert response.status_code == 401

    def test_get_agent_stats_requires_auth(self):
        """Test GET /metrics/agents/{agent_id}/stats requires authentication."""
        agent_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/metrics/agents/{agent_id}/stats")
        
        assert response.status_code == 401

    def test_get_market_stats_requires_auth(self):
        """Test GET /metrics/market/stats requires authentication."""
        response = client.get("/api/v1/metrics/market/stats")
        
        assert response.status_code == 401

    def test_get_concurrent_stats_requires_auth(self):
        """Test GET /metrics/concurrent requires authentication."""
        response = client.get("/api/v1/metrics/concurrent")
        
        assert response.status_code == 401

    def test_get_token_daily_requires_auth(self):
        """Test GET /metrics/token/daily requires authentication."""
        response = client.get("/api/v1/metrics/token/daily")
        
        assert response.status_code == 401

    def test_get_token_allocation_requires_auth(self):
        """Test GET /metrics/token/allocation requires authentication."""
        response = client.get("/api/v1/metrics/token/allocation")
        
        assert response.status_code == 401

    def test_get_agent_ranking_requires_auth(self):
        """Test GET /metrics/admin/agents/ranking requires authentication."""
        response = client.get("/api/v1/metrics/admin/agents/ranking")
        
        assert response.status_code == 401

    def test_get_user_ranking_requires_auth(self):
        """Test GET /metrics/admin/users/ranking requires authentication."""
        response = client.get("/api/v1/metrics/admin/users/ranking")
        
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_check_metrics_permission_admin(self):
        """Test check_metrics_permission returns True for admin."""
        from app.api.v1.metrics import check_metrics_permission
        
        admin_user = User(id=1, email="admin@example.com", role="admin")
        
        result = await check_metrics_permission(uuid.uuid4(), admin_user)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_check_metrics_permission_public_agent(self):
        """Test check_metrics_permission returns True for public agent."""
        from app.api.v1.metrics import check_metrics_permission
        
        user = User(id=1, email="user@example.com", role="user")
        agent_id = uuid.uuid4()
        
        mock_agent = MagicMock()
        mock_agent.is_public = True
        
        with patch('app.services.database.database_service') as mock_db:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_agent
            mock_context = MagicMock()
            mock_context.__enter__.return_value = mock_session
            mock_db.get_session_maker.return_value = mock_context
            
            result = await check_metrics_permission(agent_id, user)
            
            assert result is True

    @pytest.mark.asyncio
    async def test_check_metrics_permission_own_private_agent(self):
        """Test check_metrics_permission returns True for own private agent."""
        from app.api.v1.metrics import check_metrics_permission
        
        user = User(id=1, email="user@example.com", role="user")
        agent_id = uuid.uuid4()
        
        mock_agent = MagicMock()
        mock_agent.is_public = False
        mock_agent.owner_id = 1
        
        with patch('app.services.database.database_service') as mock_db:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_agent
            mock_context = MagicMock()
            mock_context.__enter__.return_value = mock_session
            mock_db.get_session_maker.return_value = mock_context
            
            result = await check_metrics_permission(agent_id, user)
            
            assert result is True

    @pytest.mark.asyncio
    async def test_check_metrics_permission_other_private_agent(self):
        """Test check_metrics_permission returns False for other's private agent."""
        from app.api.v1.metrics import check_metrics_permission
        
        user = User(id=1, email="user@example.com", role="user")
        agent_id = uuid.uuid4()
        
        mock_agent = MagicMock()
        mock_agent.is_public = False
        mock_agent.owner_id = 2
        
        with patch('app.services.database.database_service') as mock_db:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_agent
            mock_context = MagicMock()
            mock_context.__enter__.return_value = mock_session
            mock_db.get_session_maker.return_value = mock_context
            
            result = await check_metrics_permission(agent_id, user)
            
            assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])