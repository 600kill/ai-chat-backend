"""Service for private agent and tool management."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from app.models.agent import Agent, Tool, AgentTool
from app.models.rag import AgentKnowledgeBase, KnowledgeBase
from app.models.user import User
from app.services.database import database_service
from app.core.logging import logger


def _bind_knowledge_bases(session, agent_id: UUID, kb_ids: List[UUID], user_id: int) -> None:
    """在当前 session 内重建 Agent-知识库绑定并校验归属（commit 由调用方负责）。"""
    session.query(AgentKnowledgeBase).filter(
        AgentKnowledgeBase.agent_id == agent_id
    ).delete()
    for kb_id in kb_ids:
        kb = session.get(KnowledgeBase, kb_id)
        if kb is None:
            raise ValueError(f"Knowledge base {kb_id} not found")
        if not kb.is_public and kb.owner_id != user_id:
            raise ValueError(f"Knowledge base {kb_id} not accessible")
        session.add(AgentKnowledgeBase(agent_id=agent_id, kb_id=kb_id))


class MyService:
    """Service for private agent and tool operations."""
    
    def __init__(self):
        self.session_maker = database_service.get_session_maker()
    
    def get_my_agents(
        self,
        user: User,
        page: int = 1,
        size: int = 20,
        status: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict:
        """Get user's private agents.
        
        Args:
            user: Current user
            page: Page number
            size: Page size
            status: Filter by status
            search: Search keyword
        
        Returns:
            Dict: Agents list
        """
        with self.session_maker() as session:
            # Query user's private agents
            query = session.query(Agent).filter(
                Agent.owner_id == user.id,
                Agent.is_public == False
            )
            
            # Filter by status
            if status:
                query = query.filter(Agent.status == status)
            
            # Search
            if search:
                query = query.filter(
                    (Agent.name.ilike(f"%{search}%")) |
                    (Agent.description.ilike(f"%{search}%"))
                )
            
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
                
                items.append({
                    "id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                    "status": agent.status,
                    "tool_count": tool_count,
                    "created_at": agent.created_at
                })
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "size": size
            }
    
    def create_my_agent(
        self,
        user: User,
        name: str,
        description: Optional[str] = None,
        graph_config: Optional[dict] = None,
        tool_ids: Optional[List[UUID]] = None,
        system_prompt: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        kb_ids: Optional[List[UUID]] = None,
    ) -> Agent:
        """Create private agent.

        Args:
            user: Current user
            name: Agent name
            description: Agent description
            graph_config: Graph config
            tool_ids: Tool IDs
            system_prompt: Agent 系统提示词
            model_name: 绑定模型
            temperature: 采样温度
            max_tokens: 最大输出 token
            kb_ids: 绑定的知识库 ID 列表

        Returns:
            Agent: Created agent
        """
        with self.session_maker() as session:
            # Create agent
            agent = Agent(
                id=uuid4(),
                name=name,
                description=description,
                graph_config=graph_config,
                status="draft",
                is_public=False,
                owner_id=user.id,
                copy_count=0,
                session_count=0,
                system_prompt=system_prompt,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            session.add(agent)
            session.flush()
            
            # Add tools
            if tool_ids:
                for idx, tool_id in enumerate(tool_ids):
                    # Check if tool belongs to user or is public
                    tool = session.get(Tool, tool_id)
                    if tool and (tool.owner_id == user.id or tool.is_public):
                        agent_tool = AgentTool(
                            agent_id=agent.id,
                            tool_id=tool_id,
                            priority=idx + 1,
                            is_public_binding=False
                        )
                        session.add(agent_tool)

            # 绑定知识库（校验失败整体回滚，Agent 不会创建）
            if kb_ids:
                _bind_knowledge_bases(session, agent.id, kb_ids, user.id)

            session.commit()
            session.refresh(agent)

            logger.info("agent_created", agent_id=str(agent.id), user_id=user.id)
            
            return agent
    
    def update_my_agent(
        self,
        agent_id: UUID,
        user: User,
        **kwargs
    ) -> Agent:
        """Update private agent.
        
        Args:
            agent_id: Agent ID
            user: Current user
            **kwargs: Update fields
        
        Returns:
            Agent: Updated agent
        """
        with self.session_maker() as session:
            agent = session.get(Agent, agent_id)
            
            if not agent:
                raise ValueError("Agent not found")
            
            if agent.is_public:
                raise ValueError("Cannot update public agent")
            
            if agent.owner_id != user.id:
                raise ValueError("Not authorized")
            
            # Update fields
            for key, value in kwargs.items():
                if value is not None and hasattr(agent, key):
                    setattr(agent, key, value)
            
            # Update tools
            if kwargs.get("tool_ids") is not None:
                # Remove old bindings
                session.query(AgentTool).filter(
                    AgentTool.agent_id == agent_id
                ).delete()
                
                # Add new bindings
                for idx, tool_id in enumerate(kwargs["tool_ids"]):
                    tool = session.get(Tool, tool_id)
                    if tool and (tool.owner_id == user.id or tool.is_public):
                        agent_tool = AgentTool(
                            agent_id=agent_id,
                            tool_id=tool_id,
                            priority=idx + 1,
                            is_public_binding=False
                        )
                        session.add(agent_tool)

            # 知识库绑定全量覆盖（None=不变；空列表=解绑全部）
            if kwargs.get("kb_ids") is not None:
                _bind_knowledge_bases(session, agent_id, kwargs["kb_ids"], user.id)

            session.commit()
            session.refresh(agent)

            logger.info("agent_updated", agent_id=str(agent_id), user_id=user.id)
            
            return agent
    
    def delete_my_agent(self, agent_id: UUID, user: User) -> bool:
        """Delete private agent.
        
        Args:
            agent_id: Agent ID
            user: Current user
        
        Returns:
            bool: Success
        """
        with self.session_maker() as session:
            agent = session.get(Agent, agent_id)
            
            if not agent:
                raise ValueError("Agent not found")
            
            if agent.is_public:
                raise ValueError("Cannot delete public agent")
            
            if agent.owner_id != user.id:
                raise ValueError("Not authorized")
            
            # Delete bindings
            session.query(AgentTool).filter(
                AgentTool.agent_id == agent_id
            ).delete()
            session.query(AgentKnowledgeBase).filter(
                AgentKnowledgeBase.agent_id == agent_id
            ).delete()

            # Delete agent
            session.delete(agent)
            session.commit()
            
            logger.info("agent_deleted", agent_id=str(agent_id), user_id=user.id)
            
            return True
    
    def batch_operation(
        self,
        ids: List[UUID],
        action: str,
        user: User
    ) -> Dict:
        """Batch operation on agents.
        
        Args:
            ids: Agent IDs
            action: Action type
            user: Current user
        
        Returns:
            Dict: Operation result
        """
        with self.session_maker() as session:
            success_count = 0
            failed_count = 0
            
            for agent_id in ids:
                agent = session.get(Agent, agent_id)
                
                if not agent or agent.is_public or agent.owner_id != user.id:
                    failed_count += 1
                    continue
                
                if action == "enable":
                    agent.status = "active"
                    success_count += 1
                elif action == "disable":
                    agent.status = "inactive"
                    success_count += 1
                elif action == "delete":
                    session.query(AgentTool).filter(
                        AgentTool.agent_id == agent_id
                    ).delete()
                    session.delete(agent)
                    success_count += 1
            
            session.commit()
            
            return {
                "success_count": success_count,
                "failed_count": failed_count
            }
    
    def get_my_tools(
        self,
        user: User,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None
    ) -> Dict:
        """Get user's tools (private + public).
        
        Args:
            user: Current user
            page: Page number
            size: Page size
            search: Search keyword
        
        Returns:
            Dict: Tools list
        """
        with self.session_maker() as session:
            # Query user's tools + public tools
            query = session.query(Tool).filter(
                (Tool.owner_id == user.id) | (Tool.is_public == True)
            )
            
            # Search
            if search:
                query = query.filter(
                    (Tool.name.ilike(f"%{search}%")) |
                    (Tool.description.ilike(f"%{search}%"))
                )
            
            # Count total
            total = query.count()
            
            # Pagination
            tools = query.offset((page - 1) * size).limit(size).all()
            
            # Build response
            items = []
            for tool in tools:
                items.append({
                    "id": tool.id,
                    "name": tool.name,
                    "description": tool.description,
                    "function_name": tool.function_name,
                    "status": tool.status,
                    "is_public": tool.is_public,
                    "created_at": tool.created_at
                })
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "size": size
            }
    
    def create_my_tool(
        self,
        user: User,
        **kwargs
    ) -> Tool:
        """Create private tool.
        
        Args:
            user: Current user
            **kwargs: Tool fields
        
        Returns:
            Tool: Created tool
        """
        with self.session_maker() as session:
            tool = Tool(
                id=uuid4(),
                is_public=False,
                owner_id=user.id,
                copy_count=0,
                **kwargs
            )
            session.add(tool)
            session.commit()
            session.refresh(tool)
            
            logger.info("tool_created", tool_id=str(tool.id), user_id=user.id)
            
            return tool
    
    def update_my_tool(
        self,
        tool_id: UUID,
        user: User,
        **kwargs
    ) -> Tool:
        """Update private tool.
        
        Args:
            tool_id: Tool ID
            user: Current user
            **kwargs: Update fields
        
        Returns:
            Tool: Updated tool
        """
        with self.session_maker() as session:
            tool = session.get(Tool, tool_id)
            
            if not tool:
                raise ValueError("Tool not found")
            
            if tool.is_public:
                raise ValueError("Cannot update public tool")
            
            if tool.owner_id != user.id:
                raise ValueError("Not authorized")
            
            for key, value in kwargs.items():
                if value is not None and hasattr(tool, key):
                    setattr(tool, key, value)
            
            session.commit()
            session.refresh(tool)
            
            logger.info("tool_updated", tool_id=str(tool_id), user_id=user.id)
            
            return tool
    
    def delete_my_tool(self, tool_id: UUID, user: User) -> bool:
        """Delete private tool.
        
        Args:
            tool_id: Tool ID
            user: Current user
        
        Returns:
            bool: Success
        """
        with self.session_maker() as session:
            tool = session.get(Tool, tool_id)
            
            if not tool:
                raise ValueError("Tool not found")
            
            if tool.is_public:
                raise ValueError("Cannot delete public tool")
            
            if tool.owner_id != user.id:
                raise ValueError("Not authorized")
            
            # Delete bindings
            session.query(AgentTool).filter(
                AgentTool.tool_id == tool_id
            ).delete()
            
            session.delete(tool)
            session.commit()
            
            logger.info("tool_deleted", tool_id=str(tool_id), user_id=user.id)
            
            return True


# Global instance
my_service = MyService()