"""Permission utilities for role-based access control."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.models.user import User
from app.models.agent import Agent, Tool
from app.services.database import database_service
from app.utils.auth import verify_token
from app.core.logging import logger


security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


class PermissionError(HTTPException):
    """Custom permission error."""
    
    def __init__(self, detail: str, error_code: int = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )
        self.error_code = error_code


class NotFoundError(HTTPException):
    """Custom not found error."""
    
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class ValidationError(HTTPException):
    """Custom validation error."""
    
    def __init__(self, detail: str, error_code: int = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
        self.error_code = error_code


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """Get current user from JWT token.
    
    Args:
        credentials: HTTP Bearer credentials
    
    Returns:
        User: Current user
    
    Raises:
        HTTPException: If token invalid or user not found
    """
    token = credentials.credentials

    # Verify token（JWT sub 为 user_id，登录接口 create_access_token(str(user.id))）
    subject = verify_token(token)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject"
        )

    # Get user
    user = await database_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> Optional[User]:
    """Get current user from JWT token (optional).
    
    Returns None if no token provided.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def check_agent_permission(
    agent: Agent,
    user: User,
    action: str
) -> bool:
    """Check if user has permission to perform action on agent.
    
    Args:
        agent: Agent object
        user: Current user
        action: Action type (read/update/delete)
    
    Returns:
        bool: True if has permission
    
    Permission rules:
        - Public agent: Everyone can read, only admin can modify
        - Private agent: Owner can read/modify, admin can read all
    """
    # Public agent
    if agent.is_public:
        if action == "read":
            return True
        elif action in ["update", "delete"]:
            return user.role == "admin"
    
    # Private agent
    if not agent.is_public:
        if action == "read":
            # Owner or admin can read
            return user.role == "admin" or agent.owner_id == user.id
        elif action in ["update", "delete"]:
            # Only owner can modify (admin cannot modify private agents)
            return agent.owner_id == user.id
    
    return False


def check_tool_permission(
    tool: Tool,
    user: User,
    action: str
) -> bool:
    """Check if user has permission to perform action on tool.
    
    Args:
        tool: Tool object
        user: Current user
        action: Action type (read/update/delete)
    
    Returns:
        bool: True if has permission
    """
    # Public tool
    if tool.is_public:
        if action == "read":
            return True
        elif action in ["update", "delete"]:
            return user.role == "admin"
    
    # Private tool
    if not tool.is_public:
        if action == "read":
            return user.role == "admin" or tool.owner_id == user.id
        elif action in ["update", "delete"]:
            return tool.owner_id == user.id
    
    return False


def require_admin(user: User) -> None:
    """Require user to be admin.
    
    Raises:
        PermissionError: If user is not admin
    """
    if user.role != "admin":
        raise PermissionError(
            detail="Only admin can perform this action",
            error_code=403003
        )


def require_owner_or_admin(
    resource_owner_id: Optional[int],
    user: User,
    resource_type: str = "resource"
) -> None:
    """Require user to be owner or admin.
    
    Raises:
        PermissionError: If user is not owner or admin
    """
    if user.role != "admin" and resource_owner_id != user.id:
        raise PermissionError(
            detail=f"You don't have permission to access this {resource_type}",
            error_code=403001
        )


def require_public_agent(agent: Agent) -> None:
    """Require agent to be public.
    
    Raises:
        ValidationError: If agent is not public
    """
    if not agent.is_public:
        raise ValidationError(
            detail="This agent is not published to public market",
            error_code=400002
        )


def require_private_agent(agent: Agent) -> None:
    """Require agent to be private.
    
    Raises:
        ValidationError: If agent is already public
    """
    if agent.is_public:
        raise ValidationError(
            detail="This agent is already in public market",
            error_code=400001
        )


def require_not_public_resource(resource: any, resource_type: str = "resource") -> None:
    """Require resource to be private.
    
    Raises:
        PermissionError: If resource is public
    """
    if hasattr(resource, 'is_public') and resource.is_public:
        raise PermissionError(
            detail=f"Public {resource_type} cannot be modified",
            error_code=403002
        )