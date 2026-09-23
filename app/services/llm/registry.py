"""LLM model registry with pre-initialized instances.

模型来源分三类：
1. 本地 LLM 网关（LiteLLM Proxy，OpenAI 兼容协议）——首选
2. DashScope 通义千问直连（ChatTongyi）——降级
3. OpenAI 直连（ChatOpenAI）——保留扩展
"""

from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_community.chat_models.tongyi import ChatTongyi
from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger


def _build_gateway_llm(**kwargs) -> ChatOpenAI:
    """构造指向本地网关的 ChatOpenAI 实例。kwargs 可覆盖默认 max_tokens/temperature。

    可传 callbacks（如 Langfuse CallbackHandler）；graph 运行时由 config
    自动传播的 callback 无需在此重复传入。
    """
    options: Dict[str, Any] = {"max_tokens": settings.MAX_TOKENS}
    options.update(kwargs)
    return ChatOpenAI(
        model=settings.GATEWAY_MODEL,
        api_key=settings.GATEWAY_API_KEY,
        base_url=settings.GATEWAY_BASE_URL,
        **options,
    )


def _build_tongyi(model_name: str, **kwargs) -> ChatTongyi:
    """构造 DashScope 通义千问实例。kwargs 可覆盖默认 max_tokens/temperature/callbacks。"""
    options: Dict[str, Any] = {"max_tokens": settings.MAX_TOKENS}
    options.update(kwargs)
    return ChatTongyi(
        model_name=model_name,
        dashscope_api_key=settings.DASHSCOPE_API_KEY,
        **options,
    )


def _build_openai(model_name: str, **kwargs) -> ChatOpenAI:
    """构造 OpenAI 直连实例。kwargs 可覆盖默认 max_tokens/temperature/callbacks。"""
    options: Dict[str, Any] = {"max_tokens": settings.MAX_TOKENS}
    options.update(kwargs)
    return ChatOpenAI(
        model=model_name,
        api_key=settings.OPENAI_API_KEY,
        **options,
    )


class LLMRegistry:
    """Registry of available LLM models with pre-initialized instances.

    顺序即降级顺序：网关模型在前，DashScope 模型在后。
    """

    LLMS: List[Dict[str, Any]] = []

    @classmethod
    def _build_default_list(cls) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []

        # 1. 本地网关模型（配置了网关才注册）
        if settings.GATEWAY_BASE_URL and settings.GATEWAY_MODEL:
            entries.append(
                {
                    "name": settings.GATEWAY_MODEL,
                    "provider": "gateway",
                    "llm": _build_gateway_llm(),
                }
            )

        # 2. DashScope 通义千问（降级）—— 账户欠费失效（2026-09-22 实测 403/400 Arrearage），
        #    降级只会浪费 60s 超时预算并混淆错误，故不再注册；充值恢复后可重新启用
        # entries.extend(
        #     [
        #         {
        #             "name": "qwen-turbo",
        #             "provider": "tongyi",
        #             "llm": _build_tongyi("qwen-turbo"),
        #         },
        #         {
        #             "name": "qwen-plus",
        #             "provider": "tongyi",
        #             "llm": _build_tongyi("qwen-plus"),
        #         },
        #     ]
        # )
        return entries

    @classmethod
    def _ensure_initialized(cls) -> None:
        if not cls.LLMS:
            cls.LLMS = cls._build_default_list()

    @classmethod
    def _provider_of(cls, model_name: str) -> str:
        """根据模型名判断供应类型。"""
        cls._ensure_initialized()
        for entry in cls.LLMS:
            if entry["name"] == model_name:
                return entry.get("provider", "openai")
        # 未注册的模型名：含 / 的按网关处理（LiteLLM 通常为 provider/model 形式）
        if "/" in model_name:
            return "gateway"
        if model_name.startswith("qwen"):
            return "tongyi"
        return "openai"

    @classmethod
    def get(cls, model_name: str, **kwargs) -> BaseChatModel:
        """Get an LLM by name with optional argument overrides.

        传 kwargs 时返回全新实例（不影响共享注册表）；
        不传 kwargs 时返回预初始化的共享实例。

        Raises:
            ValueError: model_name 找不到且无法推断供应类型时。
        """
        cls._ensure_initialized()
        model_entry = next((e for e in cls.LLMS if e["name"] == model_name), None)

        # 需要自定义参数：按供应类型新建实例
        if kwargs:
            logger.debug("creating_llm_with_custom_args", model_name=model_name, custom_args=list(kwargs.keys()))
            provider = cls._provider_of(model_name) if model_entry else (
                "gateway" if "/" in model_name else "tongyi" if model_name.startswith("qwen") else "openai"
            )
            if provider == "gateway":
                # 一次性指定其它网关模型时也允许
                return _build_gateway_llm(**{**({"model": model_name} if model_name != settings.GATEWAY_MODEL else {}), **kwargs})
            if provider == "tongyi":
                return _build_tongyi(model_name, **kwargs)
            return _build_openai(model_name, **kwargs)

        if not model_entry:
            available = ", ".join(e["name"] for e in cls.LLMS)
            raise ValueError(f"model '{model_name}' not found in registry. available models: {available}")

        logger.debug("using_default_llm_instance", model_name=model_name)
        return model_entry["llm"]

    @classmethod
    def get_all_names(cls) -> List[str]:
        """Return all registered model names in order."""
        cls._ensure_initialized()
        return [e["name"] for e in cls.LLMS]

    @classmethod
    def get_model_at_index(cls, index: int) -> Dict[str, Any]:
        """Return the model entry at a specific index, wrapping to 0 if out of range."""
        cls._ensure_initialized()
        if 0 <= index < len(cls.LLMS):
            return cls.LLMS[index]
        return cls.LLMS[0]

    @classmethod
    def get_provider(cls, model_name: str) -> Optional[str]:
        """返回模型供应类型（gateway/tongyi/openai）。"""
        cls._ensure_initialized()
        entry = next((e for e in cls.LLMS if e["name"] == model_name), None)
        return entry.get("provider") if entry else None
