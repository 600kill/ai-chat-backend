"""Test cases for public market API endpoints."""

import pytest
import uuid
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture
def test_user_data():
    """Create test user data."""
    return {
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "password": "test_password",
        "username": "Test User"
    }


@pytest.fixture
def test_admin_data():
    """Create test admin data."""
    return {
        "email": f"admin_{uuid.uuid4().hex[:8]}@example.com",
        "password": "admin_password",
        "username": "Admin User"
    }


@pytest.fixture
def test_agent_data():
    """Create test agent data."""
    return {
        "name": f"Test Agent {uuid.uuid4().hex[:8]}",
        "description": "Test agent for API testing",
        "graph_config": {"type": "state_graph"},
        "tool_ids": []
    }


def test_get_public_agents_list():
    """Test GET /api/v1/market/agents - Get public agents list."""
    response = client.get("/api/v1/market/agents")
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert "data" in data
    assert "items" in data["data"]
    assert "total" in data["data"]


def test_get_public_agents_with_search():
    """Test GET /api/v1/market/agents with search parameter."""
    response = client.get("/api/v1/market/agents?search=test")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200


def test_get_public_agents_with_pagination():
    """Test GET /api/v1/market/agents with pagination."""
    response = client.get("/api/v1/market/agents?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["page"] == 1
    assert data["data"]["size"] == 10


def test_get_public_agent_detail_not_found():
    """Test GET /api/v1/market/agents/{id} - Agent not found."""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/market/agents/{fake_id}")
    assert response.status_code == 404


def test_copy_agent_requires_auth():
    """Test POST /api/v1/market/agents/{id}/copy - Requires authentication."""
    fake_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/market/agents/{fake_id}/copy",
        json={"new_name": "Copy Agent"}
    )
    assert response.status_code == 401  # Unauthorized (no auth)


def test_create_session_requires_auth():
    """Test POST /api/v1/market/agents/{id}/sessions - Requires authentication."""
    fake_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/market/agents/{fake_id}/sessions",
        json={"name": "Test Session"}
    )
    assert response.status_code == 401  # Unauthorized (no auth)


def test_admin_private_agents_requires_admin():
    """Test GET /api/v1/admin/agents/private - Requires authentication."""
    response = client.get("/api/v1/admin/agents/private")
    assert response.status_code == 401  # Unauthorized (no auth)


def test_admin_publish_agent_requires_admin():
    """Test POST /api/v1/admin/agents/{id}/publish - Requires authentication."""
    fake_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/admin/agents/{fake_id}/publish",
        json={"publish_note": "Test publish"}
    )
    assert response.status_code == 401  # Unauthorized (no auth)


def test_admin_unpublish_agent_requires_admin():
    """Test POST /api/v1/admin/agents/{id}/unpublish - Requires authentication."""
    fake_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/admin/agents/{fake_id}/unpublish",
        json={"unpublish_reason": "Test unpublish"}
    )
    assert response.status_code == 401  # Unauthorized (no auth)


def test_admin_stats_requires_admin():
    """Test GET /api/v1/admin/agents/{id}/stats - Requires authentication."""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/admin/agents/{fake_id}/stats")
    assert response.status_code == 401  # Unauthorized (no auth)


def test_admin_market_stats_requires_admin():
    """Test GET /api/v1/admin/market/stats - Requires authentication."""
    response = client.get("/api/v1/admin/market/stats")
    assert response.status_code == 401  # Unauthorized (no auth)


def test_my_agents_requires_auth():
    """Test GET /api/v1/my/agents - Requires authentication."""
    response = client.get("/api/v1/my/agents")
    assert response.status_code == 401  # Unauthorized (no auth)


def test_create_my_agent_requires_auth():
    """Test POST /api/v1/my/agents - Requires authentication."""
    response = client.post(
        "/api/v1/my/agents",
        json={
            "name": "Test Agent",
            "description": "Test description",
            "tool_ids": []
        }
    )
    assert response.status_code == 401  # Unauthorized (no auth)


def test_my_tools_requires_auth():
    """Test GET /api/v1/my/tools - Requires authentication."""
    response = client.get("/api/v1/my/tools")
    assert response.status_code == 401  # Unauthorized (no auth)


def test_create_my_tool_requires_auth():
    """Test POST /api/v1/my/tools - Requires authentication."""
    response = client.post(
        "/api/v1/my/tools",
        json={
            "name": "Test Tool",
            "function_name": "test_function",
            "description": "Test description"
        }
    )
    assert response.status_code == 401  # Unauthorized (no auth)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])