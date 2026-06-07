"""
【文件功能总结】应用数据安全清洗工具核心文件
提供全场景数据清洗与安全校验功能：
1. 字符串清洗：防XSS攻击、过滤恶意脚本、清除空字节
2. 邮箱格式校验与清洗
3. 递归清洗字典/列表中的所有字符串
4. 密码强度合规校验
是应用安全防护、防止注入攻击的基础工具类
"""

import html
import re
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
)


def sanitize_string(value: str) -> str:
    """
    字符串安全清洗，防止XSS跨站脚本和注入攻击
    Args:
        value: 待清洗的原始字符串
    Returns:
        安全清洗后的字符串
    """
    # 非字符串类型强制转换为字符串
    if not isinstance(value, str):
        value = str(value)

    # HTML转义，核心XSS防护
    value = html.escape(value)

    # 过滤转义后的脚本标签，双重防护
    value = re.sub(r"&lt;script.*?&gt;.*?&lt;/script&gt;", "", value, flags=re.DOTALL)

    # 移除空字节，防止截断攻击
    value = value.replace("\0", "")

    return value


def sanitize_email(email: str) -> str:
    """
    邮箱地址安全清洗与格式校验
    Args:
        email: 原始邮箱地址
    Returns:
        清洗并标准化的小写邮箱
    Raises:
        ValueError: 邮箱格式非法时抛出
    """
    # 基础字符串清洗
    email = sanitize_string(email)

    # 基础邮箱格式校验
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise ValueError("Invalid email format")

    # 统一转为小写，标准化格式
    return email.lower()


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    递归清洗字典中所有字符串类型的值
    支持嵌套字典、列表的深度清洗
    Args:
        data: 待清洗的原始字典
    Returns:
        安全清洗后的字典
    """
    sanitized = {}
    for key, value in data.items():
        # 字符串直接清洗
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        # 嵌套字典递归清洗
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        # 列表调用列表清洗函数
        elif isinstance(value, list):
            sanitized[key] = sanitize_list(value)
        # 其他类型直接保留
        else:
            sanitized[key] = value
    return sanitized


def sanitize_list(data: List[Any]) -> List[Any]:
    """
    递归清洗列表中所有字符串类型的值
    支持嵌套列表、字典的深度清洗
    Args:
        data: 待清洗的原始列表
    Returns:
        安全清洗后的列表
    """
    sanitized = []
    for item in data:
        # 字符串直接清洗
        if isinstance(item, str):
            sanitized.append(sanitize_string(item))
        # 嵌套字典递归清洗
        elif isinstance(item, dict):
            sanitized.append(sanitize_dict(item))
        # 嵌套列表递归清洗
        elif isinstance(item, list):
            sanitized.append(sanitize_list(item))
        # 其他类型直接保留
        else:
            sanitized.append(item)
    return sanitized


def validate_password_strength(password: str) -> bool:
    """
    密码强度合规校验
    Args:
        password: 待校验的密码
    Returns:
        密码强度合格返回True
    Raises:
        ValueError: 密码不满足强度要求时抛出对应原因
    """
    # 密码长度至少8位
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    # 必须包含大写字母
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")

    # 必须包含小写字母
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")

    # 必须包含数字
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one number")

    # 必须包含特殊字符
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValueError("Password must contain at least one special character")

    return True