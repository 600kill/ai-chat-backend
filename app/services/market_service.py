"""Public market service for agent management."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from app.models.agent import Agent, Tool, AgentTool
from app.models.user import User
from app.models.session import Session
from app.services.database import database_service
from app.services.workflow_service import workflow_service
from app.core.logging import logger


class MarketService:
    """Service for public market operations."""
    
    def __init__(self):
        self.session_maker = database_service.get_session_maker()
    
    def get_public_agents(
        self,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        order: Optional[str] = None
    ) -> Dict:
        """Get public agents list with pagination.
        
        Args:
            page: Page number
            size: Page size
            search: Search keyword
            sort_by: Sort field
            order: Sort order
        
        Returns:
            Dict: Agents list with pagination info
        """
        with self.session_maker() as session:
            # Query public agents
            query = session.query(Agent).filter(Agent.is_public == True)
            
            # Search
            if search:
                query = query.filter(
                    (Agent.name.ilike(f"%{search}%")) |
                    (Agent.description.ilike(f"%{search}%"))
                )
            
            # Sort
            if sort_by:
                sort_field = getattr(Agent, sort_by, None)
                if sort_field:
                    if order == "desc":
                        query = query.order_by(sort_field.desc())
                    else:
                        query = query.order_by(sort_field.asc())
            else:
                query = query.order_by(Agent.published_at.desc())
            
            # Count total
            total = query.count()
            
            # Pagination
            agents = query.offset((page - 1) * size).limit(size).all()
            
            # Build response
            items = []
            for agent in agents:
                # Get tool count
                tool_count = session.query(AgentTool).filter(
                    AgentTool.agent_id == agent.id
                ).count()
                
                # Get publisher name
                publisher = session.get(User, agent.published_by) if agent.published_by else None
                
                items.append({
                    "id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                    "tool_count": tool_count,
                    "copy_count": agent.copy_count,
                    "session_count": agent.session_count,
                    "published_at": agent.published_at,
                    "publisher_name": publisher.username if publisher else None
                })
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "size": size
            }
    
    def get_public_agent_detail(self, agent_id: UUID) -> Optional[Dict]:
        """Get public agent detail.
        
        Args:
            agent_id: Agent ID
        
        Returns:
            Dict: Agent detail or None
        """
        with self.session_maker() as session:
            agent = session.get(Agent, agent_id)
            
            if not agent or not agent.is_public:
                return None
            
            # Get tools
            agent_tools = session.query(AgentTool).filter(
                AgentTool.agent_id == agent.id
            ).all()
            
            tools = []
            for at in agent_tools:
                tool = session.get(Tool, at.tool_id)
                if tool:
                    tools.append({
                        "id": tool.id,
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "output_schema": tool.output_schema
                    })
            
            # Get publisher name
            publisher = session.get(User, agent.published_by) if agent.published_by else None
            
            return {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "graph_config": agent.graph_config,
                "tools": tools,
                "copy_count": agent.copy_count,
                "session_count": agent.session_count,
                "published_at": agent.published_at,
                "publisher_name": publisher.username if publisher else None
            }
    
    def copy_agent_to_private(
        self,
        agent_id: UUID,
        user: User,
        new_name: Optional[str] = None
    ) -> Dict:
        """Copy public agent to user's private library.
        
        Args:
            agent_id: Public agent ID
            user: Current user
            new_name: New agent name
        
        Returns:
            Dict: Copy result
        """
        with self.session_maker() as session:
            # Get original agent
            original_agent = session.get(Agent, agent_id)
            
            if not original_agent or not original_agent.is_public:
                raise ValueError("Agent not found or not public")
            
            # Create new agent
            new_agent = Agent(
                id=uuid4(),
                name=new_name or f"{original_agent.name} (副本)",
                description=original_agent.description,
                graph_config=original_agent.graph_config,
                status="draft",
                is_public=False,
                owner_id=user.id,
                copy_count=0,
                session_count=0,
                source_agent_id=original_agent.id
            )
            session.add(new_agent)
            session.flush()
            
            # Get original tools
            original_agent_tools = session.query(AgentTool).filter(
                AgentTool.agent_id == original_agent.id
            ).all()
            
            copied_tools_count = 0
            for at in original_agent_tools:
                original_tool = session.get(Tool, at.tool_id)
                if original_tool:
                    # Copy tool
                    new_tool = Tool(
                        id=uuid4(),
                        name=original_tool.name,
                        description=original_tool.description,
                        function_name=original_tool.function_name,
                        input_schema=original_tool.input_schema,
                        output_schema=original_tool.output_schema,
                        example=original_tool.example,
                        status=original_tool.status,
                        is_public=False,
                        owner_id=user.id,
                        copy_count=0,
                        source_tool_id=original_tool.id
                    )
                    session.add(new_tool)
                    session.flush()
                    
                    # Create new agent-tool binding
                    new_binding = AgentTool(
                        agent_id=new_agent.id,
                        tool_id=new_tool.id,
                        priority=at.priority,
                        is_public_binding=False
                    )
                    session.add(new_binding)
                    copied_tools_count += 1
            
            # Update original agent copy count
            original_agent.copy_count += 1
            
            session.commit()
            
            logger.info(
                "agent_copied",
                original_id=str(agent_id),
                new_id=str(new_agent.id),
                user_id=user.id,
                tools_count=copied_tools_count
            )
            
            return {
                "new_agent_id": new_agent.id,
                "new_agent_name": new_agent.name,
                "copied_tools_count": copied_tools_count
            }
    
    def create_test_session(
        self,
        agent_id: UUID,
        user: User,
        name: Optional[str] = None
    ) -> Dict:
        """Create test session for public agent.
        
        Args:
            agent_id: Public agent ID
            user: Current user
            name: Session name
        
        Returns:
            Dict: Session info with token
        """
        with self.session_maker() as session:
            # Get agent
            agent = session.get(Agent, agent_id)
            
            if not agent or not agent.is_public:
                raise ValueError("Agent not found or not public")
            
            # Create session
            session_id = str(uuid4())
            new_session = Session(
                id=session_id,
                user_id=user.id,
                agent_id=agent.id,
                name=name or f"测试 {agent.name}",
                username=user.username or "Test User"
            )
            session.add(new_session)
            
            # Update agent session count
            agent.session_count += 1
            
            session.commit()
            
            # Generate token
            from app.utils.auth import create_access_token
            token = create_access_token(session_id)
            
            logger.info(
                "test_session_created",
                session_id=session_id,
                agent_id=str(agent_id),
                user_id=user.id
            )
            
            return {
                "session_id": session_id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "access_token": token.access_token,
                "expires_at": token.expires_at
            }
    
    async def get_workflow_data(self, agent_id: UUID) -> Dict:
        """Get workflow data for public agent.
        
        Args:
            agent_id: Agent ID
        
        Returns:
            Dict: Workflow data
        """
        return await workflow_service.get_workflow_data(agent_id)


# Global instance
market_service = MarketService()