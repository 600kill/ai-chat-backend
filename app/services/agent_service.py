"""Agent and Tool management service."""

from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException
from sqlmodel import Session, select, delete

from app.core.logging import logger
from app.models.agent import Agent, Tool, AgentTool
from app.models.rag import AgentKnowledgeBase
from app.models.user import User


class AgentService:
    """Service for managing Agents and Tools."""
    
    def __init__(self, session_maker):
        self.session_maker = session_maker
    
    # ==================== Tool Methods ====================
    
    async def create_tool(self, tool_data: dict) -> Tool:
        """Create a new tool."""
        with self.session_maker() as session:
            tool = Tool(**tool_data)
            session.add(tool)
            session.commit()
            session.refresh(tool)
            logger.info("tool_created", tool_id=str(tool.id), tool_name=tool.name)
            return tool
    
    async def get_tool(self, tool_id: UUID) -> Optional[Tool]:
        """Get a tool by ID."""
        with self.session_maker() as session:
            return session.get(Tool, tool_id)
    
    async def get_tool_by_name(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        with self.session_maker() as session:
            statement = select(Tool).where(Tool.name == name)
            return session.exec(statement).first()
    
    async def get_all_tools(self, status: Optional[str] = None) -> List[Tool]:
        """Get all tools, optionally filtered by status."""
        with self.session_maker() as session:
            statement = select(Tool)
            if status:
                statement = statement.where(Tool.status == status)
            statement = statement.order_by(Tool.created_at)
            return session.exec(statement).all()
    
    async def update_tool(self, tool_id: UUID, update_data: dict) -> Tool:
        """Update a tool."""
        with self.session_maker() as session:
            tool = session.get(Tool, tool_id)
            if not tool:
                raise HTTPException(status_code=404, detail="工具不存在")
            
            for key, value in update_data.items():
                if hasattr(tool, key):
                    setattr(tool, key, value)
            
            session.add(tool)
            session.commit()
            session.refresh(tool)
            logger.info("tool_updated", tool_id=str(tool_id))
            return tool
    
    async def delete_tool(self, tool_id: UUID) -> bool:
        """Delete a tool."""
        with self.session_maker() as session:
            tool = session.get(Tool, tool_id)
            if not tool:
                return False
            
            # Remove from agent_tool associations
            session.exec(delete(AgentTool).where(AgentTool.tool_id == tool_id))
            session.delete(tool)
            session.commit()
            logger.info("tool_deleted", tool_id=str(tool_id))
            return True
    
    # ==================== Agent Methods ====================
    
    async def create_agent(self, agent_data: dict, tool_ids: Optional[List[UUID]] = None) -> Agent:
        """Create a new agent with associated tools."""
        with self.session_maker() as session:
            # Remove tool_ids from agent_data if present
            data = agent_data.copy()
            data.pop('tool_ids', None)
            
            agent = Agent(**data)
            session.add(agent)
            session.flush()  # Get agent ID
            
            # Associate tools if provided
            if tool_ids:
                for idx, tool_id in enumerate(tool_ids):
                    agent_tool = AgentTool(
                        agent_id=agent.id,
                        tool_id=tool_id,
                        priority=idx + 1
                    )
                    session.add(agent_tool)
            
            session.commit()
            session.refresh(agent)
            logger.info("agent_created", agent_id=str(agent.id), agent_name=agent.name)
            return agent
    
    async def get_agent(self, agent_id: UUID) -> Optional[Agent]:
        """Get an agent by ID."""
        with self.session_maker() as session:
            return session.get(Agent, agent_id)
    
    async def get_agent_with_tools(self, agent_id: UUID) -> Optional[Agent]:
        """Get an agent with its associated tools."""
        with self.session_maker() as session:
            statement = select(Agent).where(Agent.id == agent_id)
            agent = session.exec(statement).first()
            if agent:
                # Load tools relationship
                _ = agent.tools
            return agent
    
    async def get_all_agents(
        self, 
        status: Optional[str] = None, 
        search: Optional[str] = None
    ) -> List[Agent]:
        """Get all agents, optionally filtered by status or search keyword."""
        with self.session_maker() as session:
            statement = select(Agent)
            
            if status:
                statement = statement.where(Agent.status == status)
            
            if search:
                search_lower = search.lower()
                statement = statement.where(
                    (Agent.name.ilike(f"%{search_lower}%")) |
                    (Agent.description.ilike(f"%{search_lower}%"))
                )
            
            statement = statement.order_by(Agent.created_at.desc())
            return session.exec(statement).all()
    
    async def update_agent(self, agent_id: UUID, update_data: dict) -> Agent:
        """Update an agent."""
        with self.session_maker() as session:
            agent = session.get(Agent, agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent 不存在")
            
            # Handle tool_ids separately
            tool_ids = update_data.pop('tool_ids', None)
            
            # Update basic fields
            for key, value in update_data.items():
                if hasattr(agent, key):
                    setattr(agent, key, value)
            
            # Update tool associations if provided
            if tool_ids is not None:
                # Remove existing associations
                session.exec(delete(AgentTool).where(AgentTool.agent_id == agent_id))
                
                # Add new associations
                for idx, tool_id in enumerate(tool_ids):
                    agent_tool = AgentTool(
                        agent_id=agent_id,
                        tool_id=tool_id,
                        priority=idx + 1
                    )
                    session.add(agent_tool)
            
            session.add(agent)
            session.commit()
            session.refresh(agent)
            logger.info("agent_updated", agent_id=str(agent_id))
            return agent
    
    async def delete_agent(self, agent_id: UUID) -> bool:
        """Delete an agent."""
        with self.session_maker() as session:
            agent = session.get(Agent, agent_id)
            if not agent:
                return False
            
            # Remove agent_tool and agent_knowledge_base associations
            session.exec(delete(AgentTool).where(AgentTool.agent_id == agent_id))
            session.exec(delete(AgentKnowledgeBase).where(AgentKnowledgeBase.agent_id == agent_id))
            session.delete(agent)
            session.commit()
            logger.info("agent_deleted", agent_id=str(agent_id))
            return True
    
    # ==================== Batch Operations ====================
    
    async def batch_operation(self, agent_ids: List[UUID], action: str, data: Optional[dict] = None) -> dict:
        """Perform batch operations on agents."""
        success_count = 0
        failed_ids = []
        
        with self.session_maker() as session:
            for agent_id in agent_ids:
                try:
                    agent = session.get(Agent, agent_id)
                    if not agent:
                        failed_ids.append(agent_id)
                        continue
                    
                    if action == "enable":
                        agent.status = "active"
                    elif action == "disable":
                        agent.status = "inactive"
                    elif action == "delete":
                        session.exec(delete(AgentTool).where(AgentTool.agent_id == agent_id))
                        session.exec(delete(AgentKnowledgeBase).where(AgentKnowledgeBase.agent_id == agent_id))
                        session.delete(agent)
                        session.flush()
                        success_count += 1
                        continue
                    elif action == "update" and data:
                        for key, value in data.items():
                            if hasattr(agent, key):
                                setattr(agent, key, value)
                    else:
                        failed_ids.append(agent_id)
                        continue
                    
                    session.add(agent)
                    session.flush()
                    success_count += 1
                except Exception as e:
                    logger.error("batch_operation_failed", agent_id=str(agent_id), error=str(e))
                    failed_ids.append(agent_id)
            
            session.commit()
        
        logger.info(
            "batch_operation_completed",
            action=action,
            success_count=success_count,
            failed_count=len(failed_ids)
        )
        
        return {
            "success_count": success_count,
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids
        }
    
    # ==================== Utility Methods ====================
    
    async def get_agent_tool_count(self, agent_id: UUID) -> int:
        """Get the number of tools associated with an agent."""
        with self.session_maker() as session:
            statement = select(AgentTool).where(AgentTool.agent_id == agent_id)
            return len(session.exec(statement).all())