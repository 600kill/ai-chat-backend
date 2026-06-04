"""
【文件功能总结】应用日志系统核心配置文件
基于 structlog 实现结构化日志管理，支持环境差异化配置：
1. 开发/测试环境：控制台友好格式日志，带文件/行号调试信息
2. 生产/预发布环境：JSON 格式日志，便于日志收集分析
支持请求上下文绑定、请求 ID 追踪、日志文件持久化、日志分级管理
"""

import builtins
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import structlog
from asgi_correlation_id import correlation_id

from app.core.config import Environment, settings

# =========================
# 基础配置
# =========================

# 确保日志目录存在
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)


# =========================
# 请求上下文（ContextVar）
# =========================

_request_context: ContextVar[Dict[str, Any]] = ContextVar(
    "request_context", default={}
)


def bind_context(**kwargs: Any) -> None:
    """为当前请求绑定日志上下文变量"""
    current = _request_context.get() or {}
    _request_context.set({**current, **kwargs})


def clear_context() -> None:
    """清除当前请求的所有日志上下文变量"""
    _request_context.set({})


def get_context() -> Dict[str, Any]:
    """获取当前日志上下文"""
    return _request_context.get() or {}


# =========================
# structlog 处理器
# =========================


def add_context_to_event_dict(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """将上下文变量注入到每一条日志中"""
    context = get_context()
    if context:
        event_dict.update(context)
    return event_dict


def add_request_id_to_event_dict(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """将 ASGI Correlation ID 注入到日志中"""
    request_id = correlation_id.get()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def get_log_file_path() -> Path:
    """根据环境和日期生成日志文件路径"""
    env_prefix = settings.ENVIRONMENT.value
    return settings.LOG_DIR / f"{env_prefix}-{datetime.now().strftime('%Y-%m-%d')}.jsonl"


# =========================
# 自定义日志 Handler（✅ 已修复 open 报错）
# =========================


class JsonlFileHandler(logging.Handler):
    """
    自定义日志处理器：
    - 使用 builtins.open（彻底解决 NameError）
    - 不使用 logging 内部文件句柄
    """

    def __init__(self, file_path: Path):
        super().__init__()
        self.file_path = file_path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "filename": record.pathname,
                "line": record.lineno,
                "environment": settings.ENVIRONMENT.value,
            }

            if hasattr(record, "extra"):
                log_entry.update(record.extra)

            # ✅ 关键点：使用 builtins.open
            with builtins.open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """安全关闭，不做任何文件操作"""
        super().close()


# =========================
# structlog 配置
# =========================


def get_structlog_processors(
    include_file_info: bool = True,
) -> List[Any]:
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_context_to_event_dict,
        add_request_id_to_event_dict,
    ]

    if include_file_info:
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.PATHNAME,
                }
            )
        )

    processors.append(
        lambda _, __, event_dict: {
            **event_dict,
            "environment": settings.ENVIRONMENT.value,
        }
    )

    return processors


def setup_logging() -> None:
    """
    初始化全局日志系统
    - 开发环境：控制台美化输出
    - 生产环境：JSON 文件输出
    """
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    file_handler = JsonlFileHandler(get_log_file_path())
    file_handler.setLevel(log_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[file_handler, console_handler],
        force=True,  # ✅ 防止重复初始化
    )

    shared_processors = get_structlog_processors(
        include_file_info=settings.ENVIRONMENT
        in (Environment.DEVELOPMENT, Environment.TEST)
    )

    if settings.LOG_FORMAT == "console":
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )


# =========================
# 全局初始化
# =========================

setup_logging()

logger = structlog.get_logger()

logger.info(
    "logging_initialized",
    environment=settings.ENVIRONMENT.value,
    log_level="DEBUG" if settings.DEBUG else "INFO",
    log_format=settings.LOG_FORMAT,
    debug=settings.DEBUG,
)