"""Dynamic Model Adapter

Provides a unified interface for invoking different LLM providers
(Gemini, Claude, etc.) with automatic fallback on failure.
Tracks token usage for cost monitoring.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types as genai_types
import anthropic

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token usage tracking
# ---------------------------------------------------------------------------

@dataclass
class UsageRecord:
    """Single model invocation usage record."""

    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    cost_usd: float


@dataclass
class UsageTracker:
    """Accumulates token usage across all invocations."""

    records: list[UsageRecord] = field(default_factory=list)

    def record(self, rec: UsageRecord) -> None:
        self.records.append(rec)
        logger.info(
            "Token usage — model=%s in=%d out=%d latency=%.0fms cost=$%.5f",
            rec.model, rec.tokens_in, rec.tokens_out, rec.latency_ms, rec.cost_usd,
        )

    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self.records)

    @property
    def total_tokens(self) -> tuple[int, int]:
        return (
            sum(r.tokens_in for r in self.records),
            sum(r.tokens_out for r in self.records),
        )


usage_tracker = UsageTracker()

# Approximate pricing per 1M tokens (input, output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gemini-1.5-pro": (3.50, 10.50),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "claude-3.7-sonnet": (3.00, 15.00),
}


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = MODEL_PRICING.get(model, (1.0, 3.0))
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


# ---------------------------------------------------------------------------
# Base client
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Gemini client (google-genai SDK)
# ---------------------------------------------------------------------------

class GeminiClient(BaseModelClient):
    """Google Gemini API client using the new google-genai SDK."""

    def __init__(self, model_name: str = "gemini-1.5-pro"):
        self.model_name = model_name
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set — Gemini calls will fail.")
        self._client = genai.Client(api_key=api_key or "")

    async def invoke(self, prompt: str, **kwargs: Any) -> str:
        system_prompt = kwargs.get("system_prompt")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)

        config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_prompt if system_prompt else None,
        )

        t0 = time.monotonic()
        response = await self._client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        text = response.text or ""
        tokens_in = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        tokens_out = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

        usage_tracker.record(UsageRecord(
            model=self.model_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_usd=_estimate_cost(self.model_name, tokens_in, tokens_out),
        ))
        return text

    async def invoke_with_images(
        self, prompt: str, images: list[str], **kwargs: Any
    ) -> str:
        parts: list[Any] = []
        for img_path in images:
            with open(img_path, "rb") as f:
                img_data = f.read()
            mime = "image/png" if img_path.endswith(".png") else "image/jpeg"
            parts.append(genai_types.Part.from_bytes(data=img_data, mime_type=mime))
        parts.append(genai_types.Part.from_text(text=prompt))

        t0 = time.monotonic()
        response = await self._client.aio.models.generate_content(
            model=self.model_name,
            contents=parts,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        text = response.text or ""
        tokens_in = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        tokens_out = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

        usage_tracker.record(UsageRecord(
            model=self.model_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_usd=_estimate_cost(self.model_name, tokens_in, tokens_out),
        ))
        return text


# ---------------------------------------------------------------------------
# Claude client (anthropic SDK)
# ---------------------------------------------------------------------------

class ClaudeClient(BaseModelClient):
    """Anthropic Claude API client using the official SDK."""

    def __init__(self, model_name: str = "claude-3.7-sonnet"):
        self.model_name = model_name
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — Claude calls will fail.")
        self._client = anthropic.AsyncAnthropic(api_key=api_key or "")

    async def invoke(self, prompt: str, **kwargs: Any) -> str:
        system_prompt = kwargs.get("system_prompt", "")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)

        t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - t0) * 1000

        text = response.content[0].text if response.content else ""
        tokens_in = response.usage.input_tokens if response.usage else 0
        tokens_out = response.usage.output_tokens if response.usage else 0

        usage_tracker.record(UsageRecord(
            model=self.model_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_usd=_estimate_cost(self.model_name, tokens_in, tokens_out),
        ))
        return text

    async def invoke_with_images(
        self, prompt: str, images: list[str], **kwargs: Any
    ) -> str:
        system_prompt = kwargs.get("system_prompt", "")
        max_tokens = kwargs.get("max_tokens", 4096)

        content: list[dict] = []
        for img_path in images:
            with open(img_path, "rb") as f:
                img_data = base64.standard_b64encode(f.read()).decode()
            mime = "image/png" if img_path.endswith(".png") else "image/jpeg"
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": img_data},
            })
        content.append({"type": "text", "text": prompt})

        t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )
        latency_ms = (time.monotonic() - t0) * 1000

        text = response.content[0].text if response.content else ""
        tokens_in = response.usage.input_tokens if response.usage else 0
        tokens_out = response.usage.output_tokens if response.usage else 0

        usage_tracker.record(UsageRecord(
            model=self.model_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_usd=_estimate_cost(self.model_name, tokens_in, tokens_out),
        ))
        return text


# ---------------------------------------------------------------------------
# Model Adapter (unified interface)
# ---------------------------------------------------------------------------

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
    async def invoke_with_images(
        cls, model_name: str, prompt: str, images: list[str], **kwargs: Any
    ) -> str:
        client = cls.get(model_name)
        return await client.invoke_with_images(prompt, images, **kwargs)

    @classmethod
    async def invoke_with_fallback(
        cls,
        primary: str,
        fallback: str,
        prompt: str,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> str:
        """Invoke primary model with exponential backoff, fall back on exhaustion."""
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await cls.invoke(primary, prompt, **kwargs)
            except Exception as e:
                last_error = e
                wait = min(2 ** attempt, 30)  # 1s, 2s, 4s … cap 30s
                logger.warning(
                    "Model %s failed (attempt %d/%d): %s — retrying in %ds",
                    primary, attempt + 1, max_retries, e, wait,
                )
                await asyncio.sleep(wait)

        logger.warning(
            "Primary model %s exhausted retries. Falling back to %s. Last error: %s",
            primary, fallback, last_error,
        )
        return await cls.invoke(fallback, prompt, **kwargs)


def init_models() -> None:
    """Register all available model clients. Called at startup."""
    ModelAdapter.register("gemini-1.5-pro", GeminiClient("gemini-1.5-pro"))
    ModelAdapter.register("gemini-1.5-flash", GeminiClient("gemini-1.5-flash"))
    ModelAdapter.register("gemini-2.0-flash", GeminiClient("gemini-2.0-flash"))
    ModelAdapter.register("claude-3.7-sonnet", ClaudeClient("claude-sonnet-4-20250514"))
    logger.info("All models registered.")
