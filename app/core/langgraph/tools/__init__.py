"""LangGraph tools for enhanced language model capabilities.

This package contains custom tools that can be used with LangGraph to extend
the capabilities of language models. Currently includes tools for web search
and other external integrations.
"""

from langchain_core.tools.base import BaseTool

from .ask_human import ask_human
from .calculator import calculator
from .document_search import document_search
from .duckduckgo_search import duckduckgo_search_tool
from .generate_chart import generate_chart
tools: list[BaseTool] = [
    duckduckgo_search_tool,
    ask_human,
    generate_chart,
    calculator,  # ast 白名单安全计算
    document_search,  # RAG 知识库检索（Agent 绑定 KB 后自动可用）
]