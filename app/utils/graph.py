"""
【文件功能总结】应用LangGraph工具函数核心文件
提供AI对话消息处理的通用工具：
1. 基于tiktoken本地计算消息Token数（无API调用）
2. 消息裁剪、格式转换、文本内容提取
3. 标准化LLM响应内容格式
4. 预处理对话消息（拼接系统提示词+裁剪超长消息）
保障对话消息合规、格式统一，适配各类大模型输入要求
"""

# Token计算库
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import tiktoken
# LangChain消息基类
from langchain_core.messages import BaseMessage
# LangChain消息裁剪工具
from langchain_core.messages import trim_messages as _trim_messages

# 全局配置
from app.core.config import settings
# 日志工具
from app.core.logging import logger
# 消息Schema模型
from app.schemas import Message

# 模块级缓存tiktoken编码器：线程安全、可复用。
# tiktoken 首次使用会从 openaipublic.blob.core.windows.net 下载 BPE 词表，
# 网络不通时 requests 无超时会永久卡死并阻塞整个应用启动，
# 因此限时 10 秒初始化，失败则降级为启发式 token 估算。
_TIKTOKEN_ENCODING = None
_TIKTOKEN_INIT_DONE = False


def _init_encoding():
    try:
        return tiktoken.encoding_for_model(settings.DEFAULT_LLM_MODEL)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _ensure_encoding():
    """限时初始化 tiktoken 编码器；超时/失败返回 None（调用方降级估算）。"""
    global _TIKTOKEN_ENCODING, _TIKTOKEN_INIT_DONE
    if _TIKTOKEN_INIT_DONE:
        return _TIKTOKEN_ENCODING
    _TIKTOKEN_INIT_DONE = True
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tiktoken-init")
    try:
        _TIKTOKEN_ENCODING = executor.submit(_init_encoding).result(timeout=10)
        logger.info("tiktoken_encoding_ready", encoding=_TIKTOKEN_ENCODING.name)
    except (FuturesTimeoutError, Exception) as e:
        logger.warning(
            "tiktoken_encoding_unavailable_use_heuristic",
            error=str(e),
        )
        _TIKTOKEN_ENCODING = None
    finally:
        # 不等待可能仍挂起的下载线程，避免阻塞事件循环/启动
        executor.shutdown(wait=False, cancel_futures=True)
    return _TIKTOKEN_ENCODING


def _token_len(text: str) -> int:
    """计算单段文本 token 数；tiktoken 不可用时用中英文混合启发式估算。"""
    if not text:
        return 0
    encoding = _ensure_encoding()
    if encoding is not None:
        return len(encoding.encode(text))
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + math.ceil(other / 4)


def _count_tokens_tiktoken(messages: list) -> int:
    """
    本地使用tiktoken计算Token数量，无需调用API
    支持字典格式、BaseMessage格式的消息
    返回总Token数
    """
    num_tokens = 0
    for message in messages:
        # 每条消息固定 overhead 4个Token
        num_tokens += 4
        # 处理字典格式消息
        if isinstance(message, dict):
            for _, value in message.items():
                if isinstance(value, str):
                    num_tokens += _token_len(value)
        # 处理LangChain BaseMessage格式消息
        elif isinstance(message, BaseMessage):
            content = message.content
            # 字符串内容
            if isinstance(content, str):
                num_tokens += _token_len(content)
            # 列表格式内容（多块文本）
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, str):
                        num_tokens += _token_len(block)
                    elif isinstance(block, dict) and "text" in block:
                        num_tokens += _token_len(block["text"])
    # 每条回复固定增加2个Token（assistant前缀）
    num_tokens += 2
    return num_tokens


def dump_messages(messages: list[Message]) -> list[dict]:
    """
    将Message模型列表转换为字典列表
    用于适配LangChain消息处理函数
    """
    return [message.model_dump() for message in messages]


def extract_text_content(content: str | list) -> str:
    """
    从LLM返回的原始内容中提取纯文本
    兼容两种格式：
    1. 简单字符串
    2. GPT-5等返回的结构化块列表（text/reasoning块）
    返回纯文本字符串，无内容则返回空
    """
    # 字符串直接返回
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            # 提取text类型块的内容
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            # 记录推理块日志
            elif block.get("type") == "reasoning":
                logger.debug(
                    "reasoning_block_received",
                    reasoning_id=block.get("id"),
                    has_summary=bool(block.get("summary")),
                )
    return "".join(parts)


def process_llm_response(response: BaseMessage) -> BaseMessage:
    """
    标准化LLM原始响应：将content统一转为纯字符串
    适配不同厂商的返回格式，保证content始终为字符串
    返回原BaseMessage实例（仅修改content）
    """
    # 列表格式内容提取纯文本
    if isinstance(response.content, list):
        response.content = extract_text_content(response.content)
        logger.debug(
            "processed_structured_content",
            content_block_count=len(response.content),
            extracted_length=len(response.content),
        )
    return response


def prepare_messages(messages: list[Message], system_prompt: str) -> list[Message]:
    """
    为LLM预处理对话消息：
    1. 裁剪超长消息（保留最新消息）
    2. 拼接系统提示词
    返回预处理后的消息列表
    """
    try:
        # 裁剪消息：保留最新消息，不包含系统提示，严格限制最大Token
        trimmed_messages = _trim_messages(
            dump_messages(messages),
            strategy="last",
            token_counter=_count_tokens_tiktoken,
            max_tokens=settings.MAX_TOKENS,
            start_on="human",
            include_system=False,
            allow_partial=False,
        )
    except ValueError as e:
        # 捕获不支持的内容块异常（如GPT-5推理块）
        if "Unrecognized content block type" in str(e):
            logger.warning(
                "token_counting_failed_skipping_trim",
                error=str(e),
                message_count=len(messages),
            )
            # 跳过裁剪，直接使用原始消息
            trimmed_messages = messages
        else:
            raise

    # 拼接系统提示词 + 裁剪后的对话消息
    return [Message(role="system", content=system_prompt)] + trimmed_messages