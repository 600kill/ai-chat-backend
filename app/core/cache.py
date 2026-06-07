"""
【文件功能】缓存服务核心文件
支持两种缓存模式：
1. 配置 Valkey/Redis 时使用分布式缓存
2. 未配置时自动降级为内存缓存
统一提供 get/set/delete 接口，业务层无需关心底层实现
"""
import hashlib
import time
from typing import Optional

# 导入项目配置
from app.core.config import settings
# 导入日志工具
from app.core.logging import logger

# 尝试异步导入 Redis（可选依赖）
try:
    from redis.asyncio import Redis
    # 标记 Redis 客户端可用
    REDIS_AVAILABLE = True
except ImportError:
    # 导入失败则打印调试日志
    logger.debug("redis_not_available")
    # 标记 Redis 不可用
    REDIS_AVAILABLE = False

class InMemoryCacheService:
    """
    内存缓存类（降级方案）
    当没有配置 Valkey/Redis 时自动使用
    带 TTL 过期机制，进程内有效
    """
    def __init__(self, default_ttl: int = 60):
        """
        初始化内存缓存
        default_ttl：默认过期时间（秒）
        """
        # 内部存储结构：{ key: (过期时间戳, 值) }
        self._cache: dict[str, tuple[float, str]] = {}
        # 设置默认 TTL
        self._default_ttl = default_ttl

    async def initialize(self) -> None:
        """内存缓存无需初始化，空实现"""
        logger.info("cache_initialized", backend="in_memory", ttl=self._default_ttl)

    async def get(self, key: str) -> Optional[str]:
        """根据 key 获取缓存值"""
        # 从内存字典读取数据
        entry = self._cache.get(key)
        # 不存在直接返回 None
        if entry is None:
            return None

        # 解析出过期时间和值
        expires_at, value = entry
        # 当前时间超过过期时间则删除数据
        if time.monotonic() > expires_at:
            del self._cache[key]
            return None

        # 有效则返回值
        return value

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """写入缓存，带过期时间"""
        # 计算过期时间点
        expires_at = time.monotonic() + (ttl or self._default_ttl)
        # 存入内存
        self._cache[key] = (expires_at, value)

    async def delete(self, key: str) -> None:
        """根据 key 删除缓存"""
        self._cache.pop(key, None)

    async def close(self) -> None:
        """关闭：清空内存缓存"""
        self._cache.clear()

class ValkeyCacheService:
    """Valkey/Redis 分布式缓存实现"""
    def __init__(self, default_ttl: int = 60):
        """初始化客户端连接"""
        # Redis 客户端实例，初始为空
        self._client: Optional[Redis] = None
        # 默认 TTL
        self._default_ttl = default_ttl

    async def initialize(self) -> None:
        """初始化并连接 Redis/Valkey"""
        # 创建异步 Redis 客户端
        self._client = Redis(
            host=settings.VALKEY_HOST,
            port=settings.VALKEY_PORT,
            db=settings.VALKEY_DB,
            password=settings.VALKEY_PASSWORD or None,
            max_connections=settings.VALKEY_MAX_CONNECTIONS,
            decode_responses=True,
        )
        # 测试连接是否正常
        await self._client.ping()
        # 打印初始化日志
        logger.info(
            "cache_initialized",
            backend="redis",
            host=settings.VALKEY_HOST,
            port=settings.VALKEY_PORT,
            ttl=self._default_ttl,
        )

    async def get(self, key: str) -> Optional[str]:
        """从 Valkey 获取值"""
        if not self._client:
            return None
        try:
            return await self._client.get(key)
        except Exception as e:
            logger.warning("cache_get_failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """写入 Valkey，自动设置过期时间"""
        if not self._client:
            return
        try:
            await self._client.set(key, value, ex=(ttl or self._default_ttl))
        except Exception as e:
            logger.warning("cache_set_failed", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        """删除 Valkey 中的键"""
        if not self._client:
            return
        try:
            await self._client.delete(key)
        except Exception as e:
            logger.warning("cache_delete_failed", key=key, error=str(e))

    async def close(self) -> None:
        """关闭 Valkey 连接"""
        if self._client:
            await self._client.aclose()
            logger.info("cache_connection_closed")

def _create_cache_service() -> InMemoryCacheService | ValkeyCacheService:
    """
    自动根据配置创建合适的缓存实例
    配置了 VALKEY_HOST 且安装了 redis → 使用 Valkey
    否则 → 使用内存缓存
    """
    # 从配置读取默认 TTL
    ttl = settings.CACHE_TTL_SECONDS

    # 启用 Valkey 条件：配置了 host + 依赖可用
    if settings.VALKEY_HOST and REDIS_AVAILABLE:
        return ValkeyCacheService(default_ttl=ttl)

    # 配置了 host 但没装依赖 → 警告日志
    if settings.VALKEY_HOST and not REDIS_AVAILABLE:
        logger.warning(
            "redis_client_not_installed",
            hint="install with: uv add redis --optional cache",
        )

    # 默认返回内存缓存
    return InMemoryCacheService(default_ttl=ttl)

def cache_key(prefix: str, *parts: str) -> str:
    """
    构造标准缓存键
    prefix：前缀，如 user/session/memory
    parts：参与哈希的字符串（如用户ID、会话ID）
    返回：prefix:哈希值 格式的唯一键
    """
    # 把所有部分用冒号拼接成原始字符串
    raw = ":".join(parts)
    # SHA256 哈希，取前 16 位
    hashed = hashlib.sha256(raw.encode()).hexdigest()[:16]
    # 返回最终缓存键
    return f"{prefix}:{hashed}"

# 创建全局单例缓存实例
cache_service = _create_cache_service()