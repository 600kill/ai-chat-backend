"""
【文件功能总结】应用接口限流配置核心文件
基于 slowapi 实现接口限流防护，根据客户端IP地址限制请求频率
支持两种存储模式：
1. 配置 Valkey/Redis 时：使用分布式存储，多服务实例共享限流规则
2. 未配置时：使用本地内存存储，单实例限流
限流规则统一从配置文件读取
"""

# 导入slowapi限流核心类
from slowapi import Limiter
# 导入获取客户端远程IP的工具函数（作为限流唯一标识）
from slowapi.util import get_remote_address

# 导入项目全局配置
from app.core.config import settings
# 导入日志工具
from app.core.logging import logger

# 初始化存储地址为空
_storage_uri = None
# 判断是否配置了Valkey/Redis主机地址
if settings.VALKEY_HOST:
    # 拼接密码部分：有密码则带密码，无密码则为空
    _password_part = f":{settings.VALKEY_PASSWORD}@" if settings.VALKEY_PASSWORD else ""
    # 构造Valkey/Redis连接地址（redis协议）
    _storage_uri = f"redis://{_password_part}{settings.VALKEY_HOST}:{settings.VALKEY_PORT}/{settings.VALKEY_DB}"
    # 打印日志：限流服务使用Valkey作为分布式存储
    logger.info("rate_limiter_using_valkey", host=settings.VALKEY_HOST, port=settings.VALKEY_PORT)

# 初始化全局限流实例
limiter = Limiter(
    # 限流标识：使用客户端IP地址
    key_func=get_remote_address,
    # 默认限流规则：从全局配置读取
    default_limits=settings.RATE_LIMIT_DEFAULT,
    # 存储地址：配置Valkey则用分布式存储，否则用内存存储
    storage_uri=_storage_uri,
)