"""
【文件功能总结】应用可观测性模块核心文件
集成 Langfuse 实现 AI 大模型交互全链路追踪、监控与调试
负责 Langfuse 初始化、认证校验、回调处理器创建，为 LLM 调用提供可观测能力
"""
'''
# 导入Langfuse核心客户端
#from langfuse import Langfuse
# 导入Langfuse与LangChain集成的回调处理器
#from langfuse.langchain import CallbackHandler

# 导入全局配置
from app.core.config import settings
# 导入日志工具
from app.core.logging import logger


def langfuse_init():
    """初始化Langfuse可观测性服务"""
    # 创建Langfuse客户端实例，加载配置文件中的参数
    langfuse = Langfuse(
        # 是否开启追踪功能
        tracing_enabled=settings.LANGFUSE_TRACING_ENABLED,
        # Langfuse公钥
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        # Langfuse密钥
        secret_key=settings.LANGFUSE_SECRET_KEY,
        # Langfuse服务地址
        host=settings.LANGFUSE_HOST,
        # 当前运行环境
        environment=settings.ENVIRONMENT.value,
        # 是否开启调试模式
        debug=settings.DEBUG,
    )

    # 校验Langfuse认证是否成功
    if langfuse.auth_check():
        # 认证成功，打印调试日志
        logger.debug("langfuse_auth_success")
    else:
        # 认证失败，打印调试日志
        logger.debug("langfuse_auth_failure")


def get_langfuse_callback_handler() -> CallbackHandler:
    """
    创建Langfuse回调处理器，用于追踪LLM大模型的交互过程
    Returns:
        配置完成的Langfuse回调处理器
    """
    # 返回Langfuse回调处理器实例
    return CallbackHandler()


# 创建全局单例的Langfuse回调处理器，全项目共用
langfuse_callback_handler = get_langfuse_callback_handler()'''