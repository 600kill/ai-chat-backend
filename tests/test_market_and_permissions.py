"""Integration tests for MarketService and permission utilities using real database."""

import pytest
import uuid

from app.services.market_service import MarketService
from app.utils.permissions import (
    check_agent_permission,
    check_tool_permission,
    require_admin,
    require_owner_or_admin,
    require_public_agent,
    require_private_agent,
    PermissionError,
    ValidationError,
)
from app.models.agent import Agent, Tool


class TestMarketService:
    """Test cases for MarketService with real database."""

    def test_get_public_agents(self, test_public_agent):
        """Test get_public_agents returns paginated list."""
        service = MarketService()
        
        result = service.get_public_agents(page=1, size=20)
        
        assert "items" in result
        assert "total" in result
        assert "page" in result
        assert "size" in result
        assert result["total"] >= 1

    def test_get_public_agents_with_search(self, test_public_agent):
        """Test get_public_agents with search keyword."""
        service = MarketService()
        
        result = service.get_public_agents(search="Public")
        
        assert result["total"] >= 1

    def test_get_public_agent_detail(self, test_public_agent):
        """Test get_public_agent_detail returns agent detail."""
        service = MarketService()
        
        result = service.get_public_agent_detail(test_public_agent.id)
        
        assert result is not None
        assert result["id"] == test_public_agent.id
        assert result["name"] == test_public_agent.name

    def test_get_public_agent_detail_not_public(self, test_agent):
        """Test get_public_agent_detail returns None for private agent."""
        service = MarketService()
        
        result = service.get_public_agent_detail(test_agent.id)
        
        assert result is None

    def test_get_public_agent_detail_not_found(self):
        """Test get_public_agent_detail returns None for non-existent agent."""
        service = MarketService()
        
        result = service.get_public_agent_detail(uuid.uuid4())
        
        assert result is None

    def test_copy_agent_to_private(self, test_public_agent, test_user):
        """Test copy_agent_to_private copies public agent to user's private library."""
        service = MarketService()
        
        result = service.copy_agent_to_private(test_public_agent.id, test_user, "My Copied Agent")
        
        assert "new_agent_id" in result
        assert "new_agent_name" in result
        assert result["new_agent_name"] == "My Copied Agent"

    def test_copy_agent_to_private_not_public(self, test_agent, test_user):
        """Test copy_agent_to_private raises ValueError for private agent."""
        service = MarketService()
        
        with pytest.raises(ValueError):
            service.copy_agent_to_private(test_agent.id, test_user)

    def test_copy_agent_to_private_not_found(self, test_user):
        """Test copy_agent_to_private raises ValueError for non-existent agent."""
        service = MarketService()
        
        with pytest.raises(ValueError):
            service.copy_agent_to_private(uuid.uuid4(), test_user)

    def test_create_test_session(self, test_public_agent, test_user):
        """Test create_test_session creates session for public agent."""
        service = MarketService()
        
        result = service.create_test_session(test_public_agent.id, test_user)
        
        assert "session_id" in result
        assert "agent_id" in result
        assert "access_token" in result
        assert result["agent_id"] == test_public_agent.id

    def test_create_test_session_not_public(self, test_agent, test_user):
        """Test create_test_session raises ValueError for private agent."""
        service = MarketService()
        
        with pytest.raises(ValueError):
            service.create_test_session(test_agent.id, test_user)


class TestPermissionUtils:
    """Test cases for permission utilities."""

    def test_check_agent_permission_public_read(self, test_public_agent, test_user):
        """Test check_agent_permission allows everyone to read public agent."""
        result = check_agent_permission(test_public_agent, test_user, "read")
        
        assert result is True

    def test_check_agent_permission_public_update_admin(self, test_public_agent, test_admin_user):
        """Test check_agent_permission allows admin to update public agent."""
        result = check_agent_permission(test_public_agent, test_admin_user, "update")
        
        assert result is True

    def test_check_agent_permission_public_update_user(self, test_public_agent, test_user):
        """Test check_agent_permission denies user from updating public agent."""
        result = check_agent_permission(test_public_agent, test_user, "update")
        
        assert result is False

    def test_check_agent_permission_private_read_owner(self, test_agent, test_user):
        """Test check_agent_permission allows owner to read private agent."""
        result = check_agent_permission(test_agent, test_user, "read")
        
        assert result is True

    def test_check_agent_permission_private_read_admin(self, test_agent, test_admin_user):
        """Test check_agent_permission allows admin to read private agent."""
        result = check_agent_permission(test_agent, test_admin_user, "read")
        
        assert result is True

    def test_check_agent_permission_private_read_other_user(self, test_agent, test_admin_user):
        """Test check_agent_permission denies other users from reading private agent."""
        test_admin_user.id = 999
        test_admin_user.role = "user"
        
        result = check_agent_permission(test_agent, test_admin_user, "read")
        
        assert result is False

    def test_check_agent_permission_private_update_owner(self, test_agent, test_user):
        """Test check_agent_permission allows owner to update private agent."""
        result = check_agent_permission(test_agent, test_user, "update")
        
        assert result is True

    def test_check_agent_permission_private_update_admin(self, test_agent, test_admin_user):
        """Test check_agent_permission denies admin from updating private agent."""
        test_admin_user.id = 999
        
        result = check_agent_permission(test_agent, test_admin_user, "update")
        
        assert result is False

    def test_check_tool_permission_public_read(self, db_session, test_user):
        """Test check_tool_permission allows everyone to read public tool."""
        tool = Tool(
            id=uuid.uuid4(),
            name="Test Tool",
            description="Test tool",
            function_name="test_func",
            is_public=True
        )
        db_session.add(tool)
        db_session.commit()
        
        result = check_tool_permission(tool, test_user, "read")
        
        assert result is True
        
        db_session.delete(tool)
        db_session.commit()

    def test_check_tool_permission_private_read_owner(self, db_session, test_user):
        """Test check_tool_permission allows owner to read private tool."""
        tool = Tool(
            id=uuid.uuid4(),
            name="Test Tool",
            description="Test tool",
            function_name="test_func",
            is_public=False,
            owner_id=test_user.id
        )
        db_session.add(tool)
        db_session.commit()
        
        result = check_tool_permission(tool, test_user, "read")
        
        assert result is True
        
        db_session.delete(tool)
        db_session.commit()

    def test_check_tool_permission_private_read_other_user(self, db_session, test_user, test_admin_user):
        """Test check_tool_permission denies other users from reading private tool."""
        tool = Tool(
            id=uuid.uuid4(),
            name="Test Tool",
            description="Test tool",
            function_name="test_func",
            is_public=False,
            owner_id=test_admin_user.id
        )
        db_session.add(tool)
        db_session.commit()
        
        result = check_tool_permission(tool, test_user, "read")
        
        assert result is False
        
        db_session.delete(tool)
        db_session.commit()

    def test_require_admin_success(self, test_admin_user):
        """Test require_admin does not raise for admin."""
        require_admin(test_admin_user)

    def test_require_admin_failure(self, test_user):
        """Test require_admin raises for non-admin."""
        with pytest.raises(PermissionError):
            require_admin(test_user)

    def test_require_owner_or_admin_owner(self, test_user):
        """Test require_owner_or_admin allows owner."""
        require_owner_or_admin(resource_owner_id=test_user.id, user=test_user)

    def test_require_owner_or_admin_admin(self, test_admin_user):
        """Test require_owner_or_admin allows admin."""
        require_owner_or_admin(resource_owner_id=999, user=test_admin_user)

    def test_require_owner_or_admin_other_user(self, test_user):
        """Test require_owner_or_admin denies other users."""
        with pytest.raises(PermissionError):
            require_owner_or_admin(resource_owner_id=999, user=test_user)

    def test_require_public_agent_success(self, test_public_agent):
        """Test require_public_agent does not raise for public agent."""
        require_public_agent(test_public_agent)

    def test_require_public_agent_failure(self, test_agent):
        """Test require_public_agent raises for private agent."""
        with pytest.raises(ValidationError):
            require_public_agent(test_agent)

    def test_require_private_agent_success(self, test_agent):
        """Test require_private_agent does not raise for private agent."""
        require_private_agent(test_agent)

    def test_require_private_agent_failure(self, test_public_agent):
        """Test require_private_agent raises for public agent."""
        with pytest.raises(ValidationError):
            require_private_agent(test_public_agent)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])