"""Agent Runtime 配置组装服务。

职责：按 agent_id / version_id / version_no 从数据库还原出 graph.run() 所需的 AgentConfig，
不负责执行；执行由 LangGraphAgent.run() 完成。

注意：沿用本项目既有风格——方法声明为 async，内部使用同步 SQLAlchemy Session。
"""

from typing import Optional
from uuid import UUID

from app.core.langgraph.graph import AgentConfig
from app.core.logging import logger
from app.models.agent import Agent, AgentTool, Tool
from app.models.rag import AgentKnowledgeBase, KnowledgeBase
from app.models.version import AgentVersion
from app.services.database import database_service


class AgentVersionNotFoundError(Exception):
    """指定的版本快照不存在。"""


class AgentRuntimeService:
    """从 DB 组装 Agent 运行配置。"""

    def __init__(self):
        self.session_maker = database_service.get_session_maker()

    async def build_config(
        self,
        agent_id: str | UUID,
        version_id: Optional[str] = None,
        version_no: Optional[int] = None,
    ) -> Optional[AgentConfig]:
        """组装指定 Agent 的运行配置。

        Args:
            agent_id: Agent ID
            version_id: 版本快照 ID（优先于 version_no）
            version_no: Agent 内版本号（人读的 v1/v2/v3）

        Returns:
            AgentConfig；Agent 不存在时返回 None。
            指定版本时按快照还原（不依赖 Agent 当前配置）；快照中已删除的
            知识库跳过并记入 config.warnings，不报错。

        Raises:
            AgentVersionNotFoundError: 指定的版本不存在。
        """
        with self.session_maker() as session:
            agent = session.get(Agent, UUID(str(agent_id)))
            if agent is None:
                logger.warning("agent_runtime_config_agent_not_found", agent_id=str(agent_id))
                return None

            if version_id or version_no:
                return self._build_config_from_snapshot(session, agent, version_id, version_no)

            # 按绑定优先级取已启用工具的 function_name（即 LangChain 工具名）
            rows = (
                session.query(Tool.function_name)
                .join(AgentTool, AgentTool.tool_id == Tool.id)
                .filter(AgentTool.agent_id == agent.id, Tool.status == "enabled")
                .order_by(AgentTool.priority)
                .all()
            )
            tool_names = [row[0] for row in rows]

            kb_rows = (
                session.query(AgentKnowledgeBase.kb_id)
                .filter(AgentKnowledgeBase.agent_id == agent.id)
                .all()
            )
            kb_ids = [str(row[0]) for row in kb_rows]

            config = AgentConfig(
                system_prompt=agent.system_prompt,
                model_name=agent.model_name,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
                tool_names=tool_names,
                kb_ids=kb_ids or None,
            )
            logger.info(
                "agent_runtime_config_built",
                agent_id=str(agent.id),
                model_name=config.model_name,
                tools=tool_names,
                kb_count=len(kb_ids),
                version_id=version_id,
            )
            return config

    def _build_config_from_snapshot(
        self,
        session,
        agent: Agent,
        version_id: Optional[str],
        version_no: Optional[int],
    ) -> AgentConfig:
        """从版本快照还原配置（自包含，不读 Agent 当前工具/KB 绑定表）。"""
        query = session.query(AgentVersion).filter(AgentVersion.agent_id == agent.id)
        if version_id:
            version = query.filter(AgentVersion.id == UUID(str(version_id))).first()
        else:
            version = query.filter(AgentVersion.version_no == int(version_no)).first()
        if version is None:
            raise AgentVersionNotFoundError(
                f"版本不存在：agent={agent.id} version_id={version_id} version_no={version_no}"
            )

        snapshot = version.snapshot or {}
        warnings: list[str] = []

        # 工具：快照自含完整定义；执行器按 function_name 在运行时注册表匹配
        # （graph._chat 对缺失执行器自动跳过），此处仅收集禁用项警告
        tool_names: list[str] = []
        for t in snapshot.get("tools") or []:
            if t.get("status") != "enabled":
                warnings.append(f"工具 {t.get('name')} 在快照中为禁用状态，已跳过")
                continue
            tool_names.append(t["function_name"])

        # 知识库：校验当前仍存在，已删除的跳过并记警告
        kb_ids: list[str] = []
        for kb_ref in snapshot.get("kb_ids") or []:
            kb = session.get(KnowledgeBase, UUID(kb_ref["id"]))
            if kb is None:
                warnings.append(f"知识库 {kb_ref.get('name')}（{kb_ref['id']}）已删除，本次运行不检索该库")
                continue
            kb_ids.append(str(kb.id))

        config = AgentConfig(
            system_prompt=snapshot.get("system_prompt"),
            model_name=snapshot.get("model_name"),
            temperature=snapshot.get("temperature"),
            max_tokens=snapshot.get("max_tokens"),
            tool_names=tool_names,
            kb_ids=kb_ids or None,
            version_snapshot=snapshot,
            warnings=warnings or None,
        )
        logger.info(
            "agent_runtime_config_built_from_snapshot",
            agent_id=str(agent.id),
            version_no=version.version_no,
            model_name=config.model_name,
            tools=tool_names,
            kb_count=len(kb_ids),
            warnings=warnings,
        )
        return config


agent_runtime_service = AgentRuntimeService()
