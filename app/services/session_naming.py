"""
【文件功能总结】会话自动命名功能核心模块
新会话首次发送消息时自动执行：
1. 通过PostgreSQL原子操作抢占会话，避免多进程/多实例重复调用LLM
2. 先生成占位名称，确保会话始终有合理名称
3. 后台异步调用轻量LLM生成正式标题并覆盖占位名
保证会话命名高效、安全、无重复调用
"""

import asyncio

# LangChain消息模型
from langchain_core.messages import HumanMessage, SystemMessage
# SQLModel数据库会话与更新语句
from sqlmodel import Session as DBSession
from sqlmodel import update

# 日志工具
from app.core.logging import logger
# 监控指标
#from app.core.metrics import session_names_generated_total
# 会话标题生成提示词
from app.core.prompts import SESSION_TITLE_PROMPT
# 会话数据库模型
from app.models.session import Session as ChatSession
# 会话标题Schema模型
from app.schemas.chat import SessionTitle
# 数据库服务
from app.services.database import database_service
# LLM大模型服务
from app.services.llm import llm_service

# 占位名称最大长度
_PLACEHOLDER_MAX = 40

# 存储后台任务，防止垃圾回收
_background_tasks: set[asyncio.Task] = set()


def _build_placeholder(user_message: str) -> str:
    """
    从用户消息生成会话占位名称
    清理空格并截取最大长度，无内容则返回默认名称
    """
    # 清理多余空格
    cleaned = " ".join(user_message.split())
    # 截取长度并返回，空内容则返回"New chat"
    return cleaned[:_PLACEHOLDER_MAX].rstrip() or "New chat"


def _claim_session(session_id: str, placeholder: str) -> bool:
    """
    PostgreSQL原子操作抢占会话命名权
    仅当会话名称为空时才更新，保证仅有一个调用者成功
    返回True：抢占成功；False：已被其他进程抢占
    """
    # 创建数据库会话
    with DBSession(database_service.engine) as db:
        # 构造更新语句：仅匹配ID且名称为空的会话
        stmt = update(ChatSession).where(ChatSession.id == session_id, ChatSession.name == "").values(name=placeholder)
        # 执行更新
        result = db.exec(stmt)
        db.commit()
        # 判断更新行数是否为1，是则抢占成功
        return (result.rowcount or 0) == 1


async def _persist_session_name(session_id: str, user_message: str) -> None:
    """
    后台异步任务：调用LLM生成正式会话标题并持久化
    成功则更新数据库，失败则记录监控指标
    """
    try:
        # 调用轻量LLM生成会话标题
        result = await llm_service.call(
            [
                SystemMessage(content=SESSION_TITLE_PROMPT),
                HumanMessage(content=user_message[:500]),
            ],
            model_name="gpt-5.4-nano",
            response_format=SessionTitle,
            reasoning={"effort": "low"},
            max_tokens=32,
            temperature=0.3,
        )
        # 更新数据库中的会话名称
        await database_service.update_session_name(session_id, result.title)

        # 👇 只注释这一行（监控计数）
        # session_names_generated_total.labels(status="success").inc()

        # 👇 只注释这一行（日志）
        # logger.info("session_name_generated", session_id=session_id, name=result.title)

    except Exception:
        pass
    # 👇 只注释这一行（监控计数）
    # session_names_generated_total.labels(status="error").inc()
    # 👇 只注释这一行（日志）
    # logger.exception("session_name_generation_failed", session_id=session_id)

def maybe_name_session(session_id: str, session_name: str, messages: list) -> None:
    """
    外部调用入口：判断是否需要自动命名会话
    安全可在任意聊天接口调用，并发会被数据库原子操作去重
    """
    # 会话已有名称，直接返回
    if session_name:
        return
    # 获取第一条用户消息
    first_user_msg = next((m.content for m in messages if m.role == "user"), None)
    # 无用户消息，直接返回
    if not first_user_msg:
        return
    # 抢占会话命名权，成功则创建后台任务生成正式标题
    if _claim_session(session_id, _build_placeholder(first_user_msg)):
        task = asyncio.create_task(_persist_session_name(session_id, first_user_msg))
        _background_tasks.add(task)
        # 任务完成后从集合中移除
        task.add_done_callback(_background_tasks.discard)