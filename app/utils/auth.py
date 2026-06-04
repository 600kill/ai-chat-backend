"""
【文件功能总结】应用认证工具核心文件
提供JWT令牌的创建、验证核心功能：
1. 基于会话ID生成带过期时间的JWT访问令牌
2. 验证JWT令牌合法性，提取会话ID
3. 包含令牌格式校验、异常捕获、日志记录
是应用身份认证、会话鉴权的基础工具类
"""

import re
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from typing import Optional

# JWT认证核心库
from jose import (
    JWTError,
    jwt,
)

# 全局配置
from app.core.config import settings
# 日志工具
from app.core.logging import logger
# 令牌响应模型
from app.schemas.auth import Token
# 字符串清洗工具
from app.utils.sanitization import sanitize_string


def create_access_token(thread_id: str, expires_delta: Optional[timedelta] = None) -> Token:
    """
    为会话创建JWT访问令牌
    Args:
        thread_id: 对话唯一会话ID
        expires_delta: 可选的令牌过期时间
    Returns:
        生成的令牌对象
    """
    # 计算令牌过期时间
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        # 使用配置中的默认过期天数
        expire = datetime.now(UTC) + timedelta(days=settings.JWT_ACCESS_TOKEN_EXPIRE_DAYS)

    # 构造JWT载荷数据
    to_encode = {
        "sub": thread_id,                # 主题：会话ID
        "exp": expire,                   # 过期时间
        "iat": datetime.now(UTC),        # 签发时间
        # 唯一令牌标识，清洗字符串防止注入
        "jti": sanitize_string(f"{thread_id}-{datetime.now(UTC).timestamp()}"),
    }

    # 使用密钥和算法生成JWT令牌
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    # 记录令牌创建日志
    logger.info("token_created", thread_id=thread_id, expires_at=expire.isoformat())

    # 返回令牌对象
    return Token(access_token=encoded_jwt, expires_at=expire)


def verify_token(token: str) -> Optional[str]:
    """
    验证JWT令牌，提取并返回会话ID
    Args:
        token: 待验证的JWT令牌
    Returns:
        验证成功返回会话ID，失败返回None
    Raises:
        ValueError: 令牌格式非法时抛出
    """
    # 基础校验：令牌非空且为字符串
    if not token or not isinstance(token, str):
        logger.warning("token_invalid_format")
        raise ValueError("Token must be a non-empty string")

    # JWT格式校验：标准JWT为3段base64url编码，用.分隔
    if not re.match(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$", token):
        logger.warning("token_suspicious_format")
        raise ValueError("Token format is invalid - expected JWT format")

    try:
        # 解码并验证JWT令牌
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        # 从载荷中提取会话ID
        thread_id: str = payload.get("sub")
        if thread_id is None:
            logger.warning("token_missing_thread_id")
            return None

        # 验证成功，记录日志
        logger.info("token_verified", thread_id=thread_id)
        return thread_id

    # 捕获JWT验证异常
    except JWTError as e:
        logger.error("token_verification_failed", error=str(e))
        return None