"""
【文件功能总结】应用认证授权Schema模型文件
基于Pydantic定义认证相关的数据校验模型，包含：
1. JWT令牌模型、登录响应模型
2. 用户注册请求模型（带密码强度校验）
3. 用户/会话响应模型
4. 数据合法性校验（密码强度、会话名称清洗）
统一管理认证流程的入参/出参数据格式
"""

import re
from datetime import datetime

# Pydantic数据校验核心库
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)

# 基础响应模型基类
from app.schemas.base import BaseResponse


class Token(BaseModel):
    """认证令牌模型"""

    access_token: str = Field(..., description="JWT访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型，固定为bearer")
    expires_at: datetime = Field(..., description="令牌过期时间戳")


class TokenResponse(BaseResponse):
    """登录接口响应模型"""

    access_token: str = Field(..., description="JWT访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型，固定为bearer")
    expires_at: datetime = Field(..., description="令牌过期时间")


class UserCreate(BaseModel):
    """用户注册请求模型"""

    email: EmailStr = Field(..., description="用户邮箱地址")
    password: SecretStr = Field(..., description="用户密码", min_length=8, max_length=64)
    username: str | None = Field(default=None, description="可选的用户显示名称", max_length=50)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: SecretStr) -> SecretStr:
        """密码强度校验器"""
        # 获取明文密码
        password = v.get_secret_value()

        # 密码长度校验
        if len(password) < 8:
            raise ValueError("密码长度至少为8位")

        # 必须包含大写字母
        if not re.search(r"[A-Z]", password):
            raise ValueError("密码必须包含至少一个大写字母")

        # 必须包含小写字母
        if not re.search(r"[a-z]", password):
            raise ValueError("密码必须包含至少一个小写字母")

        # 必须包含数字
        if not re.search(r"[0-9]", password):
            raise ValueError("密码必须包含至少一个数字")

        # 必须包含特殊字符
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValueError("密码必须包含至少一个特殊字符")

        return v


class UserResponse(BaseResponse):
    """用户操作响应模型"""

    id: int = Field(..., description="用户ID")
    email: str = Field(..., description="用户邮箱地址")
    username: str | None = Field(default=None, description="可选的用户显示名称")
    token: Token = Field(..., description="认证令牌")


class SessionResponse(BaseResponse):
    """会话创建响应模型"""

    session_id: str = Field(..., description="聊天会话唯一标识")
    name: str = Field(default="", description="会话名称", max_length=100)
    token: Token = Field(..., description="会话认证令牌")

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """会话名称清洗校验器，过滤危险字符"""
        # 过滤可能造成安全风险的特殊字符
        sanitized = re.sub(r'[<>{}[\]()\'"`]', "", v)
        return sanitized