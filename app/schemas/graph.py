"""
【文件功能总结】应用LangGraph工作流状态Schema文件
定义LangGraph智能体/工作流的状态模型，统一管理对话流程中的状态数据
核心包含对话消息列表、长时记忆文本，是AI对话工作流的核心状态结构
"""

from typing import Annotated

# LangGraph消息追加处理器
from langgraph.graph.message import add_messages
# Pydantic数据校验核心库
from pydantic import (
    BaseModel,
    Field,
)


class GraphState(BaseModel):
    """LangGraph智能体/工作流的状态定义模型"""

    # 对话消息列表：使用Annotated绑定add_messages处理器，自动追加消息
    messages: Annotated[list, add_messages] = Field(
        default_factory=list, description="对话中的消息列表"
    )
    # 对话长时记忆内容，默认为空字符串
    long_term_memory: str = Field(default="", description="对话的长时记忆内容")