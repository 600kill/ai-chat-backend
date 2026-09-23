"""Agent 版本快照服务。

设计要点（按评审反馈）：
- 快照完整自包含：工具存完整定义（name/description/function_name/input_schema 等），
  不只存 tool_id——工具表后续变更不影响历史版本的精确复现。
- 软回滚：不覆盖/删除任何历史版本，从目标版本拷贝快照新建版本
  （note="Rollback from vN"），并同步应用到 Agent 当前配置，全程留审计。
- 边界降级：快照中引用的知识库已被删除时跳过并收集 warnings，不报错。

沿用项目既有风格：同步 SQLAlchemy（API 层用 asyncio.to_thread 调用）。
"""

import copy
from typing import Any, Optional
from uuid import UUID

from app.core.logging import logger
from app.models.agent import Agent, AgentTool, Tool
from app.models.rag import AgentKnowledgeBase, KnowledgeBase
from app.models.version import AgentVersion
from app.services.database import database_service


class VersionNotFoundError(Exception):
    """版本不存在。"""


class VersionService:
    """Agent 版本快照：发布 / 列表 / 详情 / 软回滚。"""

    def __init__(self):
        self.session_maker = database_service.get_session_maker()

    # ------------------------------------------------------------------
    # snapshot 构造
    # ------------------------------------------------------------------
    def _build_snapshot(self, session, agent: Agent) -> dict[str, Any]:
        """从 Agent 当前配置构造完整快照（工具取 DB 完整定义）。"""
        tool_rows = (
            session.query(Tool)
            .join(AgentTool, AgentTool.tool_id == Tool.id)
            .filter(AgentTool.agent_id == agent.id)
            .order_by(AgentTool.priority)
            .all()
        )
        kb_rows = (
            session.query(KnowledgeBase)
            .join(AgentKnowledgeBase, AgentKnowledgeBase.kb_id == KnowledgeBase.id)
            .filter(AgentKnowledgeBase.agent_id == agent.id)
            .all()
        )
        return {
            "name": agent.name,
            "description": agent.description,
            "system_prompt": agent.system_prompt,
            "model_name": agent.model_name,
            "temperature": agent.temperature,
            "max_tokens": agent.max_tokens,
            # 工具完整定义：回滚/复现不依赖 tool 表当前状态
            "tools": [
                {
                    "tool_id": str(t.id),
                    "name": t.name,
                    "function_name": t.function_name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                    "status": t.status,
                }
                for t in tool_rows
            ],
            # 知识库绑定（附 name 供展示；内容本身不在快照内，检索时按当前库数据）
            "kb_ids": [{"id": str(kb.id), "name": kb.name} for kb in kb_rows],
        }

    def _next_version_no(self, session, agent_id: UUID) -> int:
        last = (
            session.query(AgentVersion.version_no)
            .filter(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version_no.desc())
            .first()
        )
        return (last[0] if last else 0) + 1

    # ------------------------------------------------------------------
    # 发布 / 查询
    # ------------------------------------------------------------------
    def publish_version(self, agent_id: str | UUID, note: Optional[str], user_id: Optional[int]) -> dict:
        """把 Agent 当前配置固化为一个新版本。"""
        with self.session_maker() as session:
            agent = session.get(Agent, UUID(str(agent_id)))
            if agent is None:
                raise ValueError("AGENT_NOT_FOUND")

            snapshot = self._build_snapshot(session, agent)
            version = AgentVersion(
                agent_id=agent.id,
                version_no=self._next_version_no(session, agent.id),
                snapshot=snapshot,
                note=note,
                created_by=user_id,
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            logger.info(
                "agent_version_published",
                agent_id=str(agent.id),
                version_no=version.version_no,
                tools=len(snapshot["tools"]),
                kbs=len(snapshot["kb_ids"]),
            )
            return self._to_dict(version, include_snapshot=True)

    def list_versions(self, agent_id: str | UUID) -> list[dict]:
        """版本列表（不含 snapshot 明细）。"""
        with self.session_maker() as session:
            rows = (
                session.query(AgentVersion)
                .filter(AgentVersion.agent_id == UUID(str(agent_id)))
                .order_by(AgentVersion.version_no.desc())
                .all()
            )
            return [self._to_dict(v, include_snapshot=False) for v in rows]

    def get_version(self, agent_id: str | UUID, version_no: int) -> dict:
        """按 version_no 取版本详情（含 snapshot）。"""
        with self.session_maker() as session:
            version = self._get_by_no(session, agent_id, version_no)
            return self._to_dict(version, include_snapshot=True)

    # ------------------------------------------------------------------
    # 软回滚
    # ------------------------------------------------------------------
    def rollback(self, agent_id: str | UUID, version_no: int, user_id: Optional[int]) -> dict:
        """软回滚：拷贝目标版本快照新建版本并应用到当前配置，历史版本原样保留。

        Returns:
            {"version": 新版本 dict, "warnings": [str, ...]}
        """
        with self.session_maker() as session:
            agent = session.get(Agent, UUID(str(agent_id)))
            if agent is None:
                raise ValueError("AGENT_NOT_FOUND")
            target = self._get_by_no(session, agent_id, version_no)
            snapshot = copy.deepcopy(target.snapshot)

            # 应用到当前配置；KB 绑定做存在性校验，缺失跳过并记警告
            warnings: list[str] = []
            agent.name = snapshot.get("name") or agent.name
            agent.description = snapshot.get("description")
            agent.system_prompt = snapshot.get("system_prompt")
            agent.model_name = snapshot.get("model_name")
            agent.temperature = snapshot.get("temperature")
            agent.max_tokens = snapshot.get("max_tokens")

            session.query(AgentTool).filter(AgentTool.agent_id == agent.id).delete()
            for idx, t in enumerate(snapshot.get("tools") or []):
                tool = session.get(Tool, UUID(t["tool_id"]))
                if tool is None:
                    warnings.append(f"工具 {t.get('name')}（{t['tool_id']}）已不存在，绑定已跳过")
                    continue
                session.add(
                    AgentTool(
                        agent_id=agent.id,
                        tool_id=tool.id,
                        priority=idx + 1,
                        is_public_binding=bool(tool.is_public),
                    )
                )

            session.query(AgentKnowledgeBase).filter(AgentKnowledgeBase.agent_id == agent.id).delete()
            bound_kb_ids = []
            for kb_ref in snapshot.get("kb_ids") or []:
                kb = session.get(KnowledgeBase, UUID(kb_ref["id"]))
                if kb is None:
                    warnings.append(f"知识库 {kb_ref.get('name')}（{kb_ref['id']}）已删除，绑定已跳过")
                    continue
                session.add(AgentKnowledgeBase(agent_id=agent.id, kb_id=kb.id))
                bound_kb_ids.append(str(kb.id))

            version = AgentVersion(
                agent_id=agent.id,
                version_no=self._next_version_no(session, agent.id),
                snapshot=snapshot,
                note=f"Rollback from v{target.version_no}",
                created_by=user_id,
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            logger.info(
                "agent_version_rollback",
                agent_id=str(agent.id),
                from_version_no=target.version_no,
                new_version_no=version.version_no,
                warnings=warnings,
            )
            return {
                "version": self._to_dict(version, include_snapshot=True),
                "warnings": warnings,
            }

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _get_by_no(self, session, agent_id: str | UUID, version_no: int) -> AgentVersion:
        version = (
            session.query(AgentVersion)
            .filter(
                AgentVersion.agent_id == UUID(str(agent_id)),
                AgentVersion.version_no == int(version_no),
            )
            .first()
        )
        if version is None:
            raise VersionNotFoundError(f"版本 v{version_no} 不存在")
        return version

    def _to_dict(self, version: AgentVersion, include_snapshot: bool) -> dict:
        data = {
            "id": str(version.id),
            "agent_id": str(version.agent_id),
            "version_no": version.version_no,
            "note": version.note,
            "created_by": version.created_by,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }
        if include_snapshot:
            data["snapshot"] = version.snapshot
        return data


version_service = VersionService()
