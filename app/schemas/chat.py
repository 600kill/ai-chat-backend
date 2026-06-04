"""
【文件功能总结】应用聊天模块Schema数据模型文件
基于Pydantic定义聊天相关的所有数据校验结构，包含：
1. 聊天消息模型（角色+内容，带安全校验）
2. 聊天请求/响应模型
3. 流式聊天响应模型
4. 会话标题生成模型
统一管理聊天接口的入参、出参格式与数据合法性校验
"""

import re
from typing import (
    List,
    Literal,
)

# Pydantic数据校验核心库
from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

# 基础响应模型基类
from app.schemas.base import BaseResponse


class Message(BaseModel):
    """聊天接口消息模型"""

    # 配置：忽略未定义的额外字段
    model_config = {"extra": "ignore"}

    # 消息发送者角色：用户/助手/系统
    role: Literal["user", "assistant", "system"] = Field(..., description="消息发送者角色")
    # 消息内容，限制长度1-3000字符
    content: str = Field(..., description="消息内容", min_length=1, max_length=3000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """消息内容安全校验器，过滤恶意内容"""
        # 检测并禁止脚本标签（XSS攻击防护）
        if re.search(r"<script.*?>.*?</script>", v, re.IGNORECASE | re.DOTALL):
            raise ValueError("内容包含潜在有害的脚本标签")

        # 检测并禁止空字节
        if "\0" in v:
            raise ValueError("内容包含空字节")

        return v


class ChatRequest(BaseModel):
    """聊天接口请求模型"""

    # 对话消息列表，至少包含1条消息
    messages: List[Message] = Field(
        ...,
        description="对话消息列表",
        min_length=1,
    )


class ChatResponse(BaseResponse):
    """聊天接口响应模型"""

    # 完整对话消息列表
    messages: List[Message] = Field(..., description="对话消息列表")


class StreamResponse(BaseResponse):
    """流式聊天接口响应模型"""

    # 当前流式数据块内容
    content: str = Field(default="", description="当前数据块内容")
    # 流式传输是否完成
    done: bool = Field(default=False, description="流式传输是否完成")


class SessionTitle(BaseModel):
    """会话标题生成结构化输出模型"""

    # 会话标题，长度1-60字符
    title: str = Field(
        ...,
        min_length=1,
        max_length=60,
    )

    @field_validator("title")
    @classmethod
    def _normalize(cls, v: str) -> str:
        """标题格式化归一化处理"""
        # 去除多余空格、首尾符号和引号
        v = " ".join(v.split()).strip(" \"'`.,:;!?-")
        # 处理后为空则抛出异常
        if not v:
            raise ValueError("格式化后标题为空")
        return v