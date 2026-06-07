"""
【文件功能总结】应用配置管理核心文件
负责：环境检测、加载对应.env配置文件、解析环境变量、统一管理全项目所有配置
包含：运行环境、应用基础配置、数据库、缓存、限流、日志、AI模型、JWT等所有配置项
"""

import json
import os
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
)

# 导入dotenv库，用于加载.env环境变量文件
from dotenv import load_dotenv


# 定义应用运行环境类型
class Environment(str, Enum):
    """
    应用运行环境枚举
    定义应用可运行的所有环境：开发、测试、预发布、生产
    """

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


# 获取当前应用运行环境
def get_environment() -> Environment:
    """
    获取当前运行环境
    返回：枚举类型的环境对象
    """
    # 读取系统环境变量APP_ENV，默认值development
    match os.getenv("APP_ENV", "development").lower():
        case "production" | "prod":
            return Environment.PRODUCTION
        case "staging" | "stage":
            return Environment.STAGING
        case "test":
            return Environment.TEST
        case _:
            return Environment.DEVELOPMENT


# 根据当前环境加载对应的.env配置文件
def load_env_file():
    """加载指定环境的.env配置文件"""
    # 获取当前运行环境
    env = get_environment()
    # 打印当前加载的环境
    print(f"Loading environment: {env}")
    # 获取项目根目录
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # 定义.env文件加载优先级（优先级从高到低）
    env_files = [
        os.path.join(base_dir, f".env.{env.value}.local"),
        os.path.join(base_dir, f".env.{env.value}"),
        os.path.join(base_dir, ".env.local"),
        os.path.join(base_dir, ".env"),
    ]

    # 遍历文件列表，加载第一个存在的配置文件
    for env_file in env_files:
        if os.path.isfile(env_file):
            load_dotenv(dotenv_path=env_file)
            print(f"Loaded environment from {env_file}")
            return env_file

    # 无配置文件时返回空
    return None


# 执行配置文件加载
ENV_FILE = load_env_file()


# 从环境变量解析逗号分隔的列表
def parse_list_from_env(env_key, default=None):
    """从环境变量解析逗号分隔的列表数据"""
    # 获取环境变量值
    value = os.getenv(env_key)
    # 无值则返回默认空列表
    if not value:
        return default or []

    # 去除字符串首尾引号
    value = value.strip("\"'")
    # 无逗号，直接返回单元素列表
    if "," not in value:
        return [value]
    # 按逗号分割并去除空格，返回列表
    return [item.strip() for item in value.split(",") if item.strip()]


# 从带前缀的环境变量解析字典列表
def parse_dict_of_lists_from_env(prefix, default_dict=None):
    """解析带统一前缀的环境变量，生成字典格式配置"""
    # 初始化结果字典
    result = default_dict or {}

    # 遍历所有系统环境变量
    for key, value in os.environ.items():
        # 匹配指定前缀的环境变量
        if key.startswith(prefix):
            # 提取前缀后的名称作为key
            endpoint = key[len(prefix) :].lower()
            # 解析变量值为列表
            if value:
                value = value.strip("\"'")
                if "," in value:
                    result[endpoint] = [item.strip() for item in value.split(",") if item.strip()]
                else:
                    result[endpoint] = [value]

    return result


# 应用配置类，管理所有配置项
class Settings:
    """应用配置类（不依赖pydantic）"""

    def __init__(self):
        """
        初始化应用所有配置
        从环境变量加载配置，设置默认值，应用环境专属配置
        """
        # 设置当前运行环境
        self.ENVIRONMENT = get_environment()

        # 应用基础配置
        self.PROJECT_NAME = os.getenv("PROJECT_NAME", "FastAPI LangGraph Template")
        self.VERSION = os.getenv("VERSION", "1.0.0")
        self.DESCRIPTION = os.getenv(
            "DESCRIPTION", "A production-ready FastAPI template with LangGraph and Langfuse integration"
        )
        self.API_V1_STR = os.getenv("API_V1_STR", "/api/v1")
        # 解析DEBUG布尔值
        self.DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "t", "yes")

        # 跨域CORS配置
        self.ALLOWED_ORIGINS = parse_list_from_env("ALLOWED_ORIGINS", ["*"])

        # Langfuse 追踪配置
        self.LANGFUSE_TRACING_ENABLED = os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() in (
            "true",
            "1",
            "t",
            "yes",
        )
        self.LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        self.LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
        self.LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

        # LangGraph AI大模型配置
        self.DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "qwen-turbo")
        self.SESSION_NAMING_ENABLED = os.getenv("SESSION_NAMING_ENABLED", "true").lower() == "true"
        self.DEFAULT_LLM_TEMPERATURE = float(os.getenv("DEFAULT_LLM_TEMPERATURE", "0.2"))
        self.MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))
        self.MAX_LLM_CALL_RETRIES = int(os.getenv("MAX_LLM_CALL_RETRIES", "3"))
        self.LLM_TOTAL_TIMEOUT = int(os.getenv("LLM_TOTAL_TIMEOUT", "60"))

        # 长时记忆AI模型配置
        self.LONG_TERM_MEMORY_MODEL = os.getenv("LONG_TERM_MEMORY_MODEL", "gpt-5-nano")
        self.LONG_TERM_MEMORY_EMBEDDER_MODEL = os.getenv("LONG_TERM_MEMORY_EMBEDDER_MODEL", "text-embedding-3-small")
        self.LONG_TERM_MEMORY_COLLECTION_NAME = os.getenv("LONG_TERM_MEMORY_COLLECTION_NAME", "longterm_memory")
        # ✅ 新增：国内 embedding 配置
        self.EMBEDDER_API_KEY = os.getenv("EMBEDDER_API_KEY", "")
        self.EMBEDDER_BASE_URL = os.getenv("EMBEDDER_BASE_URL", "")

        # JWT身份认证配置
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_DAYS", "30"))

        # 日志配置
        self.LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # json格式/控制台格式

        # 性能分析配置（仅DEBUG模式生效）
        self.PROFILING_DIR = Path(os.getenv("PROFILING_DIR", "/tmp/fastapi_profiles"))
        self.PROFILING_THRESHOLD_SECONDS = float(os.getenv("PROFILING_THRESHOLD_SECONDS", "2.0"))

        # PostgreSQL数据库配置
        self.POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
        self.POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
        self.POSTGRES_DB = os.getenv("POSTGRES_DB", "app_db")
        self.POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
        self.POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
        self.POSTGRES_POOL_SIZE = int(os.getenv("POSTGRES_POOL_SIZE", "20"))
        self.POSTGRES_MAX_OVERFLOW = int(os.getenv("POSTGRES_MAX_OVERFLOW", "10"))
        self.CHECKPOINT_TABLES = ["checkpoint_blobs", "checkpoint_writes", "checkpoints"]

        # Valkey/Redis缓存配置
        self.VALKEY_HOST = os.getenv("VALKEY_HOST", "")
        self.VALKEY_PORT = int(os.getenv("VALKEY_PORT", "6379"))
        self.VALKEY_DB = int(os.getenv("VALKEY_DB", "0"))
        self.VALKEY_PASSWORD = os.getenv("VALKEY_PASSWORD", "")
        self.VALKEY_MAX_CONNECTIONS = int(os.getenv("VALKEY_MAX_CONNECTIONS", "20"))
        self.CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))

        # 接口限流默认配置
        self.RATE_LIMIT_DEFAULT = parse_list_from_env("RATE_LIMIT_DEFAULT", ["200 per day", "50 per hour"])

        # 各接口默认限流规则
        default_endpoints = {
            "chat": ["30 per minute"],
            "chat_stream": ["20 per minute"],
            "messages": ["50 per minute"],
            "register": ["10 per hour"],
            "login": ["20 per minute"],
            "root": ["10 per minute"],
            "health": ["20 per minute"],
        }

        # 从环境变量覆盖默认限流配置
        self.RATE_LIMIT_ENDPOINTS = default_endpoints.copy()
        for endpoint in default_endpoints:
            env_key = f"RATE_LIMIT_{endpoint.upper()}"
            value = parse_list_from_env(env_key)
            if value:
                self.RATE_LIMIT_ENDPOINTS[endpoint] = value

        # AI评估模型配置
        self.EVALUATION_LLM = os.getenv("EVALUATION_LLM", "gpt-5")
        self.EVALUATION_BASE_URL = os.getenv("EVALUATION_BASE_URL", "https://api.openai.com/v1")
        self.EVALUATION_API_KEY = os.getenv("EVALUATION_API_KEY", self.OPENAI_API_KEY)
        self.EVALUATION_SLEEP_TIME = int(os.getenv("EVALUATION_SLEEP_TIME", "10"))

        # 应用环境专属配置
        self.apply_environment_settings()

    def apply_environment_settings(self):
        """根据当前运行环境，应用专属配置覆盖"""
        # 定义各环境的专属配置
        env_settings = {
            Environment.DEVELOPMENT: {
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
                "RATE_LIMIT_DEFAULT": ["1000 per day", "200 per hour"],
            },
            Environment.STAGING: {
                "DEBUG": False,
                "LOG_LEVEL": "INFO",
                "RATE_LIMIT_DEFAULT": ["500 per day", "100 per hour"],
            },
            Environment.PRODUCTION: {
                "DEBUG": False,
                "LOG_LEVEL": "WARNING",
                "RATE_LIMIT_DEFAULT": ["200 per day", "50 per hour"],
            },
            Environment.TEST: {
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
                "RATE_LIMIT_DEFAULT": ["1000 per day", "1000 per hour"],  # 测试环境放宽限流
            },
        }

        # 获取当前环境的专属配置
        current_env_settings = env_settings.get(self.ENVIRONMENT, {})

        # 仅当环境变量未显式设置时，应用环境默认配置
        for key, value in current_env_settings.items():
            env_var_name = key.upper()
            if env_var_name not in os.environ:
                setattr(self, key, value)


# 创建全局唯一的配置实例，全项目共用
settings = Settings()