"""Langfuse 追踪的唯一入口（可开关，关闭时对业务零影响）。

用法（LangGraph 一次执行 = 一棵 trace）：

    handler = make_callback_handler()
    config = {
        "callbacks": [handler] if handler else [],
        "metadata": trace_metadata(session_id=..., user_id=..., trace_name=...),
    }
    await graph.ainvoke(input, config)

LLM / Tool / Retriever 子调用由 LangChain callback 机制自动挂到同一棵 trace，
业务代码不需要手动埋点。trace 的名称/用户/会话通过 metadata 中的
langfuse_* 键传递（langfuse SDK v4 约定）。
"""

from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import logger

# 全局 client：init_langfuse() 后就绪；None 表示未启用
_client = None


def is_enabled() -> bool:
    """配置开关 + Key 齐全才算启用。"""
    return bool(
        settings.LANGFUSE_TRACING_ENABLED
        and settings.LANGFUSE_HOST
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
    )


def init_langfuse():
    """应用启动时调用一次，显式初始化全局 Langfuse client。

    与进程环境变量解耦，全部走 settings；失败不阻断启动。
    """
    global _client
    if not is_enabled():
        logger.info("langfuse_disabled")
        return None
    if _client is not None:
        return _client
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            environment=settings.ENVIRONMENT.value,
        )
        logger.info("langfuse_initialized", host=settings.LANGFUSE_HOST)
    except Exception as e:
        _client = None
        logger.warning("langfuse_init_failed", error=str(e))
    return _client


def make_callback_handler():
    """为单次 graph 运行创建一个 CallbackHandler；未启用返回 None。

    注意：必须每次 run 新建实例，不能跨 run 复用（否则 trace 会串）。
    """
    if _client is None:
        if not is_enabled():
            return None
        # 未走启动初始化（如 RQ worker / 脚本）时懒加载
        init_langfuse()
    if _client is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception as e:
        logger.warning("langfuse_handler_failed", error=str(e))
        return None


def trace_metadata(
    *,
    trace_name: str,
    session_id: Optional[str] = None,
    user_id: Optional[Any] = None,
    tags: Optional[List[str]] = None,
    **business_metadata: Any,
) -> Dict[str, Any]:
    """组装 graph metadata：langfuse_* 键描述 trace，其余键成为 trace 的 metadata。

    Langfuse SDK 会自动识别并剥离 langfuse_* 键，其余 metadata 原样展示。
    """
    meta: Dict[str, Any] = {k: v for k, v in business_metadata.items() if v is not None}
    meta["langfuse_trace_name"] = trace_name
    if session_id:
        # 同一会话的多轮 run 在 Langfuse UI 中聚合成一个 session
        meta["langfuse_session_id"] = str(session_id)
    if user_id is not None:
        meta["langfuse_user_id"] = str(user_id)
    if tags:
        meta["langfuse_tags"] = [str(t) for t in tags]
    return meta


def flush_langfuse() -> None:
    """强制把暂存事件发出。短任务（评测/RQ worker）结束、smoke 验证后调用。"""
    if _client is None:
        return
    try:
        _client.flush()
    except Exception as e:
        logger.warning("langfuse_flush_failed", error=str(e))


def shutdown_langfuse() -> None:
    """进程退出时调用：flush 并关闭后台线程。"""
    global _client
    if _client is None:
        return
    try:
        _client.flush()
        _client.shutdown()
    except Exception as e:
        logger.warning("langfuse_shutdown_failed", error=str(e))
    finally:
        _client = None
