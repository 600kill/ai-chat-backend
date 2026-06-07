"""LLM model registry with pre-initialized instances."""

from typing import (
    Any,
    Dict,
    List,
)

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_community.chat_models.tongyi import ChatTongyi
from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger


class LLMRegistry:
    """Registry of available LLM models with pre-initialized instances.

    This class maintains a list of LLM configurations and provides
    methods to retrieve them by name with optional argument overrides.
    """
    # 原有GPT模型完整注释封存，后期想用直接取消注释
    '''
    LLMS: List[Dict[str, Any]] = [
        {
            "name": "gpt-5-mini",
            "llm": ChatOpenAI(
                model="gpt-5-mini",
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                reasoning={"effort": "low"},
            ),
        },
        {
            "name": "gpt-5.4",
            "llm": ChatOpenAI(
                model="gpt-5",
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                reasoning={"effort": "medium"},
            ),
        },
        {
            "name": "gpt-5.4-nano",
            "llm": ChatOpenAI(
                model="gpt-5.4-nano",
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                reasoning={"effort": "low"},
            ),
        },
        {
            "name": "gpt-5",
            "llm": ChatOpenAI(
                model="gpt-5",
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                top_p=0.95 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.8,
                presence_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
                frequency_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
            ),
        },
    ]
    '''
    # 新增通义千问模型列表
    LLMS: List[Dict[str, Any]] = [
        {
            "name": "qwen-turbo",
            "llm": ChatTongyi(
                model_name="qwen-turbo",
                dashscope_api_key=settings.DASHSCOPE_API_KEY,
                max_tokens=settings.MAX_TOKENS,
            ),
        },
        {
            "name": "qwen-plus",
            "llm": ChatTongyi(
                model_name="qwen-plus",
                dashscope_api_key=settings.DASHSCOPE_API_KEY,
                max_tokens=settings.MAX_TOKENS,
            ),
        }
    ]

    @classmethod
    def get(cls, model_name: str, **kwargs) -> BaseChatModel:
        """Get an LLM by name with optional argument overrides.

        When kwargs are provided a fresh ChatOpenAI instance is returned with
        those overrides applied, leaving the shared registry entry untouched.

        Args:
            model_name: Name of the model to retrieve.
            **kwargs: Optional arguments to override default model configuration.

        Returns:
            BaseChatModel instance.

        Raises:
            ValueError: If model_name is not found in LLMS.
        """
        model_entry = next((e for e in cls.LLMS if e["name"] == model_name), None)

        if not model_entry:
            available = ", ".join(e["name"] for e in cls.LLMS)
            raise ValueError(f"model '{model_name}' not found in registry. available models: {available}")

        if kwargs:
            logger.debug("creating_llm_with_custom_args", model_name=model_name, custom_args=list(kwargs.keys()))
            # 区分模型创建
            if model_name.startswith("qwen"):
                return ChatTongyi(model_name=model_name, dashscope_api_key=settings.DASHSCOPE_API_KEY, **kwargs)
            else:
                return ChatOpenAI(model=model_name, api_key=settings.OPENAI_API_KEY,** kwargs)

        logger.debug("using_default_llm_instance", model_name=model_name)
        return model_entry["llm"]

    @classmethod
    def get_all_names(cls) -> List[str]:
        """Return all registered model names in order.

        Returns:
            List of model name strings.
        """
        return [e["name"] for e in cls.LLMS]

    @classmethod
    def get_model_at_index(cls, index: int) -> Dict[str, Any]:
        """Return the model entry at a specific index, wrapping to 0 if out of range.

        Args:
            index: Index into LLMS.

        Returns:
            Model entry dict.
        """
        if 0 <= index < len(cls.LLMS):
            return cls.LLMS[index]
        return cls.LLMS[0]