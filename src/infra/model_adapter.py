"""Dynamic Model Adapter

Provides a unified interface for invoking different LLM providers
(Gemini, Claude, etc.) with automatic fallback on failure.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseModelClient(ABC):
    """Abstract base class for model clients."""

    @abstractmethod
    async def invoke(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt and return the model response."""
        ...

    @abstractmethod
    async def invoke_with_images(
        self, prompt: str, images: list[str], **kwargs: Any
    ) -> str:
        """Send a prompt with images (multimodal) and return the response."""
        ...


class GeminiClient(BaseModelClient):
    """Google Gemini API client."""

    def __init__(self, model_name: str = "gemini-1.5-pro"):
        self.model_name = model_name
        # TODO: Initialize google.generativeai client

    async def invoke(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    async def invoke_with_images(
        self, prompt: str, images: list[str], **kwargs: Any
    ) -> str:
        raise NotImplementedError


class ClaudeClient(BaseModelClient):
    """Anthropic Claude API client."""

    def __init__(self, model_name: str = "claude-3.7-sonnet"):
        self.model_name = model_name
        # TODO: Initialize anthropic client

    async def invoke(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    async def invoke_with_images(
        self, prompt: str, images: list[str], **kwargs: Any
    ) -> str:
        raise NotImplementedError


class ModelAdapter:
    """Unified model invocation interface with fallback support."""

    _registry: dict[str, BaseModelClient] = {}

    @classmethod
    def register(cls, model_name: str, client: BaseModelClient) -> None:
        cls._registry[model_name] = client
        logger.info("Registered model: %s", model_name)

    @classmethod
    def get(cls, model_name: str) -> BaseModelClient:
        if model_name not in cls._registry:
            raise KeyError(f"Model not registered: {model_name}")
        return cls._registry[model_name]

    @classmethod
    async def invoke(cls, model_name: str, prompt: str, **kwargs: Any) -> str:
        client = cls.get(model_name)
        return await client.invoke(prompt, **kwargs)

    @classmethod
    async def invoke_with_fallback(
        cls,
        primary: str,
        fallback: str,
        prompt: str,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> str:
        """Invoke primary model, fall back to secondary on failure."""
        for attempt in range(max_retries):
            try:
                return await cls.invoke(primary, prompt, **kwargs)
            except Exception as e:
                logger.warning(
                    "Model %s failed (attempt %d/%d): %s",
                    primary,
                    attempt + 1,
                    max_retries,
                    e,
                )
        logger.warning("Falling back from %s to %s", primary, fallback)
        return await cls.invoke(fallback, prompt, **kwargs)


def init_models() -> None:
    """Register all available model clients. Called at startup."""
    ModelAdapter.register("gemini-1.5-pro", GeminiClient("gemini-1.5-pro"))
    ModelAdapter.register("gemini-1.5-flash", GeminiClient("gemini-1.5-flash"))
    ModelAdapter.register("claude-3.7-sonnet", ClaudeClient("claude-3.7-sonnet"))
    logger.info("All models registered.")
