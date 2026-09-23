"""
【文件功能总结】长时记忆服务核心文件
基于 mem0 + pgvector 实现AI对话长时记忆存储与检索
集成缓存层优化性能，支持：记忆初始化、检索、添加、缓存加速
使用PostgreSQL+向量数据库持久化存储用户记忆，是AI长时记忆的核心服务
"""

# 导入异步记忆管理库
from mem0 import AsyncMemory

# 导入缓存工具与服务
from app.core.cache import (
    cache_key,
    cache_service,
)
# 导入全局配置
from app.core.config import settings
# 导入日志工具
from app.core.logging import logger


class MemoryService:
    """基于 mem0 和 pgvector 的长时记忆管理服务类"""

    def __init__(self):
        """初始化记忆服务，设置记忆实例为空"""
        # 异步记忆实例，初始化为None
        self._memory: AsyncMemory | None = None

    def _get_memory(self) -> AsyncMemory:
        """单例模式获取异步记忆实例（同步初始化）"""
        if self._memory is None:
            self._memory = AsyncMemory.from_config(
                config_dict={
                    "vector_store": {
                        "provider": "pgvector",
                        "config": {
                            "collection_name": settings.LONG_TERM_MEMORY_COLLECTION_NAME,
                            "dbname": settings.POSTGRES_DB,
                            "user": settings.POSTGRES_USER,
                            "password": settings.POSTGRES_PASSWORD,
                            "host": settings.POSTGRES_HOST,
                            "port": settings.POSTGRES_PORT,
                            "embedding_model_dims": settings.LONG_TERM_MEMORY_EMBEDDING_DIMS,
                        },
                    },
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": settings.LONG_TERM_MEMORY_MODEL,  # 本地网关模型
                            "api_key": settings.GATEWAY_API_KEY,
                            "openai_base_url": settings.GATEWAY_BASE_URL,  # ✅ 不是 base_url！
                        },
                    },
                    "embedder": {
                        # 本地 bge 模型，与 RAG 共用缓存，避免依赖欠费的 DashScope embedding
                        "provider": "huggingface",
                        "config": {
                            "model": settings.LONG_TERM_MEMORY_EMBEDDER_MODEL,
                            "model_kwargs": {"local_files_only": True},  # 避免运行时联网校验被代理拦截
                            "embedding_dims": settings.LONG_TERM_MEMORY_EMBEDDING_DIMS,
                        },
                    },
                }
            )
        return self._memory

    async def initialize(self) -> None:
        """预热记忆服务（仅日志，不阻塞）"""
        self._get_memory()
        logger.info("memory_service_initialized")

    async def search(self, user_id: str, query: str) -> str:
        # 尝试从缓存中获取与当前用户和查询相关的记忆结果
        try:
            # 构造缓存键，包含用户ID和查询内容的哈希值
            key = cache_key("memory", str(user_id), query)
            # 异步从缓存服务中读取数据
            cached = await cache_service.get(key)
            # 如果缓存命中，直接返回缓存内容
            if cached is not None:
                # 记录缓存命中的调试日志
                logger.debug("memory_search_cache_hit", user_id=user_id)
                return cached

            # 获取 mem0 异步记忆实例（单例）
            memory =  self._get_memory()
            # 调用 mem0 的搜索接口，传入用户ID和查询语句（注意：此处 user_id 用法可能已过时）
            results = await memory.search(
                query=query,
                filters={"user_id": str(user_id)},
                top_k=5,
            )

            # 将搜索结果列表拼接成字符串，每条记忆前加星号
            result = "\n".join([f"* {r['memory']}" for r in results["results"]])
            # 如果有结果，则存入缓存以便下次快速读取
            if result:
                await cache_service.set(key, result)
            # 返回最终的记忆字符串
            return result
        # 捕获所有异常，防止单个查询失败导致整体崩溃
        except Exception as e:
            # 记录搜索失败的详细错误信息
            logger.error("failed_to_get_relevant_memory", error=str(e), user_id=user_id, query=query)
            # 出错时返回空字符串，不影响主流程
            return ""

    async def add(self, user_id: str, messages: list[dict], metadata: dict = None) -> None:
        # 将新的对话消息作为长期记忆存储到 mem0 中
        try:
            # 获取 mem0 记忆实例（同步获取，无需 await）
            memory = self._get_memory()
            # 调用 mem0 的添加接口，传入消息列表、用户ID和元数据
            await memory.add(messages, user_id=str(user_id), metadata=metadata)
            # 记录记忆更新成功的日志
            logger.info("long_term_memory_updated_successfully", user_id=user_id)
        # 捕获存储过程中的所有异常
        except Exception as e:
            # 记录详细的异常堆栈信息，便于排查问题
            logger.exception("failed_to_update_long_term_memory", user_id=user_id, error=str(e))

    async def reset(
            self,
            user_id: str | None = None,
            *,
            confirm: bool = False,
    ) -> None:
        """
        清空长期记忆（pgvector + mem0）。

        参数：
            user_id: 只清空指定用户；None 表示清空全部
            confirm: 必须显式传 True，防止误删
        """
        if not confirm:
            raise ValueError("reset() 必须显式传入 confirm=True")

        try:
            memory = self._get_memory()

            # ✅ 1️⃣ 清 mem0 / pgvector
            if user_id is not None:
                await memory.delete_all(user_id=str(user_id))
                logger.warning(
                    "long_term_memory_deleted_for_user",
                    user_id=user_id,
                )
            else:
                await memory.reset()
                logger.warning(
                    "long_term_memory_full_reset",
                    environment=settings.ENVIRONMENT.value,
                )

            # ✅ 2️⃣ 清缓存（不强依赖 delete_pattern）
            pattern = f"memory:*:{user_id or '*'}"
            try:
                if hasattr(cache_service, "delete_pattern"):
                    await cache_service.delete_pattern(pattern)
                elif hasattr(cache_service, "delete"):
                    await cache_service.delete(pattern)
                else:
                    logger.debug(
                        "cache_delete_not_supported",
                        cache_type=cache_service.__class__.__name__,
                    )
            except Exception as cache_err:
                logger.warning(
                    "long_term_memory_cache_clear_failed",
                    error=str(cache_err),
                )

        except Exception as e:
            logger.exception(
                "long_term_memory_reset_failed",
                user_id=user_id,
                error=str(e),
            )
            raise


# 创建全局单例长时记忆服务，全项目共用
memory_service = MemoryService()
