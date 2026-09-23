"""Test cases for Agent and Tool API endpoints."""

import pytest
import uuid
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture
def test_agent_data():
    """Create test agent data."""
    return {
        "name": f"Test Agent {uuid.uuid4().hex[:8]}",
        "description": "Test agent for API testing",
        "status": "active",
        "tool_ids": []
    }


@pytest.fixture
def test_tool_data():
    """Create test tool data."""
    return {
        "name": f"Test Tool {uuid.uuid4().hex[:8]}",
        "description": "Test tool for API testing",
        "function_name": "test_function",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
        "example": '{"query": "test"}',
        "status": "enabled"
    }


def test_get_agents_list():
    """Test GET /api/v1/agents - Get agents list."""
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert "data" in data
    assert "items" in data["data"]
    assert "total" in data["data"]


def test_create_and_get_agent(test_agent_data):
    """Test POST /api/v1/agents and GET /api/v1/agents/{id}."""
    # Create agent
    response = client.post("/api/v1/agents", json=test_agent_data)
    assert response.status_code == 200
    
    agent = response.json()
    assert "id" in agent
    assert agent["name"] == test_agent_data["name"]
    assert agent["description"] == test_agent_data["description"]
    assert agent["status"] == test_agent_data["status"]
    
    # Get agent detail
    response = client.get(f"/api/v1/agents/{agent['id']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == agent["id"]
    assert detail["name"] == test_agent_data["name"]


def test_update_agent(test_agent_data):
    """Test PUT /api/v1/agents/{id}."""
    # Create agent first
    response = client.post("/api/v1/agents", json=test_agent_data)
    agent = response.json()
    
    # Update agent
    update_data = {
        "name": "Updated Agent Name",
        "status": "inactive"
    }
    response = client.put(f"/api/v1/agents/{agent['id']}", json=update_data)
    assert response.status_code == 200
    
    updated_agent = response.json()
    assert updated_agent["name"] == "Updated Agent Name"
    assert updated_agent["status"] == "inactive"


def test_delete_agent(test_agent_data):
    """Test DELETE /api/v1/agents/{id}."""
    # Create agent first
    response = client.post("/api/v1/agents", json=test_agent_data)
    agent = response.json()
    
    # Delete agent
    response = client.delete(f"/api/v1/agents/{agent['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    
    # Verify deletion
    response = client.get(f"/api/v1/agents/{agent['id']}")
    assert response.status_code == 404


def test_get_tools_list():
    """Test GET /api/v1/agents/tools - Get tools list."""
    response = client.get("/api/v1/agents/tools")
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert "data" in data
    assert "items" in data["data"]


def test_create_and_get_tool(test_tool_data):
    """Test POST /api/v1/agents/tools and GET /api/v1/agents/tools/{id}."""
    # Create tool
    response = client.post("/api/v1/agents/tools", json=test_tool_data)
    assert response.status_code == 200
    
    tool = response.json()
    assert "id" in tool
    assert tool["name"] == test_tool_data["name"]
    assert tool["function_name"] == test_tool_data["function_name"]
    
    # Get tool detail
    response = client.get(f"/api/v1/agents/tools/{tool['id']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == tool["id"]


def test_batch_operation():
    """Test POST /api/v1/agents/batch."""
    # Create multiple agents
    agents = []
    for _ in range(2):
        response = client.post("/api/v1/agents", json={
            "name": f"Batch Agent {uuid.uuid4().hex[:8]}",
            "status": "active",
            "tool_ids": []
        })
        agents.append(response.json())
    
    # Batch disable
    response = client.post("/api/v1/agents/batch", json={
        "ids": [a["id"] for a in agents],
        "action": "disable"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success_count"] == 2
    assert data["failed_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])