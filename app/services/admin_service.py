"""Admin service for managing agents and tools."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from app.models.agent import Agent, Tool, AgentTool
from app.models.user import User
from app.models.session import Session
from app.services.database import database_service
from app.core.logging import logger


class AdminService:
    """Service for admin operations."""
    
    def __init__(self):
        self.session_maker = database_service.get_session_maker()
    
    def get_private_agents(
        self,
        page: int = 1,
        size: int = 20,
        owner_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> Dict:
        """Get all private agents (admin only).
        
        Args:
            page: Page number
            size: Page size
            owner_id: Filter by owner
            status: Filter by status
        
        Returns:
            Dict: Agents list with pagination
        """
        with self.session_maker() as session:
            # Query private agents
            query = session.query(Agent).filter(Agent.is_public == False)
            
            # Filter by owner
            if owner_id:
                query = query.filter(Agent.owner_id == owner_id)
            
            # Filter by status
            if status:
                query = query.filter(Agent.status == status)
            
            # Count total
            total = query.count()
            
            # Pagination
            agents = query.offset((page - 1) * size).limit(size).all()
            
            # Build response
            items = []
            for agent in agents:
                # Get owner name
                owner = session.get(User, agent.owner_id) if agent.owner_id else None
                
                items.append({
                    "id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                    "owner_id": agent.owner_id,
                    "owner_name": owner.username if owner else None,
                    "status": agent.status,
                    "is_public": agent.is_public,
                    "created_at": agent.created_at
                })
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "size": size
            }
    
    def publish_agent(
        self,
        agent_id: UUID,
        admin_user: User,
        publish_note: Optional[str] = None
    ) -> Dict:
        """Publish private agent to public market.
        
        Args:
            agent_id: Agent ID
            admin_user: Admin user
            publish_note: Publish note
        
        Returns:
            Dict: Publish result
        """
        with self.session_maker() as session:
            # Get agent
            agent = session.get(Agent, agent_id)
            
            if not agent:
                raise ValueError("Agent not found")
            
            if agent.is_public:
                raise ValueError("Agent already published")
            
            # Update agent
            agent.is_public = True
            agent.published_at = datetime.utcnow()
            agent.published_by = admin_user.id
            
            # Get associated tools
            agent_tools = session.query(AgentTool).filter(
                AgentTool.agent_id == agent.id
            ).all()
            
            published_tools_count = 0
            for at in agent_tools:
                tool = session.get(Tool, at.tool_id)
                if tool and not tool.is_public:
                    tool.is_public = True
                    published_tools_count += 1
                at.is_public_binding = True
            
            session.commit()
            
            logger.info(
                "agent_published",
                agent_id=str(agent_id),
                admin_id=admin_user.id,
                tools_count=published_tools_count
            )
            
            return {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "published_at": agent.published_at,
                "published_tools_count": published_tools_count
            }
    
    def unpublish_agent(
        self,
        agent_id: UUID,
        admin_user: User,
        unpublish_reason: Optional[str] = None
    ) -> Dict:
        """Unpublish agent from public market.
        
        Args:
            agent_id: Agent ID
            admin_user: Admin user
            unpublish_reason: Unpublish reason
        
        Returns:
            Dict: Unpublish result
        """
        with self.session_maker() as session:
            # Get agent
            agent = session.get(Agent, agent_id)
            
            if not agent:
                raise ValueError("Agent not found")
            
            if not agent.is_public:
                raise ValueError("Agent not published")
            
            # Update agent
            agent.is_public = False
            agent.published_at = None
            agent.published_by = None
            
            # Get associated tools
            agent_tools = session.query(AgentTool).filter(
                AgentTool.agent_id == agent.id
            ).all()
            
            for at in agent_tools:
                tool = session.get(Tool, at.tool_id)
                if tool and tool.is_public:
                    tool.is_public = False
                at.is_public_binding = False
            
            session.commit()
            
            logger.info(
                "agent_unpublished",
                agent_id=str(agent_id),
                admin_id=admin_user.id,
                reason=unpublish_reason
            )
            
            return {
                "agent_id": agent.id,
                "agent_name": agent.name
            }
    
    def get_agent_stats(self, agent_id: UUID) -> Dict:
        """Get agent statistics.
        
        Args:
            agent_id: Agent ID
        
        Returns:
            Dict: Agent stats
        """
        with self.session_maker() as session:
            # Get agent
            agent = session.get(Agent, agent_id)
            
            if not agent:
                raise ValueError("Agent not found")
            
            # Get copied agents (from source_agent_id)
            copied_agents = session.query(Agent).filter(
                Agent.source_agent_id == agent_id
            ).all()
            
            copy_users = []
            for copied in copied_agents:
                owner = session.get(User, copied.owner_id) if copied.owner_id else None
                copy_users.append({
                    "user_id": copied.owner_id,
                    "user_name": owner.username if owner else None,
                    "copied_at": copied.created_at
                })
            
            # Get recent sessions
            recent_sessions = session.query(Session).filter(
                Session.agent_id == agent_id
            ).order_by(Session.created_at.desc()).limit(10).all()
            
            session_list = []
            for s in recent_sessions:
                user = session.get(User, s.user_id)
                session_list.append({
                    "session_id": s.id,
                    "user_id": s.user_id,
                    "user_name": user.username if user else None,
                    "created_at": s.created_at
                })
            
            return {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "copy_count": agent.copy_count,
                "session_count": agent.session_count,
                "copy_users": copy_users,
                "recent_sessions": session_list
            }
    
    def get_market_stats(self) -> Dict:
        """Get public market overall statistics.
        
        Returns:
            Dict: Market stats
        """
        with self.session_maker() as session:
            # Count public agents
            total_public_agents = session.query(Agent).filter(
                Agent.is_public == True
            ).count()
            
            # Count private agents
            total_private_agents = session.query(Agent).filter(
                Agent.is_public == False
            ).count()
            
            # Count total copies
            total_copies = session.query(Agent).filter(
                Agent.source_agent_id != None
            ).count()
            
            # Count total sessions on public agents
            public_agent_ids = session.query(Agent.id).filter(
                Agent.is_public == True
            ).all()
            
            total_sessions = session.query(Session).filter(
                Session.agent_id.in_([a[0] for a in public_agent_ids])
            ).count()
            
            # Get top agents
            top_agents = session.query(Agent).filter(
                Agent.is_public == True
            ).order_by(Agent.session_count.desc()).limit(10).all()
            
            top_agents_list = []
            for agent in top_agents:
                top_agents_list.append({
                    "agent_name": agent.name,
                    "copy_count": agent.copy_count,
                    "session_count": agent.session_count
                })
            
            return {
                "total_public_agents": total_public_agents,
                "total_private_agents": total_private_agents,
                "total_copies": total_copies,
                "total_sessions": total_sessions,
                "top_agents": top_agents_list
            }


# Global instance
admin_service = AdminService()