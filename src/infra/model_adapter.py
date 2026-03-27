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
import openai

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
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.0-flash": (0.10, 0.40),
    "claude-3.7-sonnet": (3.00, 15.00),
    "claude-3.7-opus": (15.00, 75.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}

# ---------------------------------------------------------------------------
# Per-role model routing
# ---------------------------------------------------------------------------

# Four roles map to workflow nodes:
#   data_collector  → Node 2 (research data extraction)
#   logic_analyst   → Node 2 (deep analysis)
#   copywriter      → Node 3 (creative writing)
#   strategist      → Node 4/8 (safety + feedback)
MODEL_ROLES = ("data_collector", "logic_analyst", "copywriter", "strategist")

ROLE_DEFAULTS: dict[str, str] = {
    "data_collector": "gemini-2.5-pro",
    "logic_analyst": "claude-3.7-opus",
    "copywriter": "claude-3.7-sonnet",
    "strategist": "gpt-4o",
}


def get_role_model(persona: dict, role: str) -> str:
    """Resolve the model for a given role from persona config.

    Lookup order:
    1. models.<role>        (new per-role field)
    2. models.primary       (legacy fallback)
    3. ROLE_DEFAULTS[role]  (built-in default)
    """
    models_cfg = persona.get("models", {})
    return (
        models_cfg.get(role)
        or models_cfg.get("primary")
        or ROLE_DEFAULTS.get(role, "gemini-2.5-flash")
    )


def get_fallback_model(persona: dict) -> str:
    """Resolve the fallback model from persona config."""
    return persona.get("models", {}).get("fallback", "gemini-2.5-flash")


# ---------------------------------------------------------------------------
# ModelRouter — centralized track-aware routing
# ---------------------------------------------------------------------------

@dataclass
class RouteConfig:
    """Resolved routing decision for a single role invocation."""

    model: str
    fallback: str
    temperature: float
    max_tokens: int
    system_prompt_suffix: str = ""


@dataclass
class TrackRule:
    """A track-based routing override.  Applied when *track_pattern* is a
    substring of the persona's ``track`` field."""

    track_pattern: str
    role: str | None = None         # None → applies to every role
    task_type: str | None = None    # None → any task type
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt_suffix: str = ""

    def matches(self, track: str, role: str, ctx: dict) -> bool:
        if self.track_pattern not in track:
            return False
        if self.role and self.role != role:
            return False
        if self.task_type and ctx.get("task_type") != self.task_type:
            return False
        return True


# Role-level base parameters (before track adjustment)
_ROLE_BASE_PARAMS: dict[str, dict[str, Any]] = {
    "data_collector": {"temperature": 0.2, "max_tokens": 4096},
    "logic_analyst":  {"temperature": 0.3, "max_tokens": 4096},
    "copywriter":     {"temperature": 0.8, "max_tokens": 4096},
    "strategist":     {"temperature": 0.3, "max_tokens": 1024},
}

# Track-specific overrides — add a TrackRule to extend.
_TRACK_RULES: list[TrackRule] = [
    # ── 上海中考: Gemini excels at policy document reading ──
    TrackRule(
        track_pattern="中考",
        role="data_collector",
        task_type="policy_analysis",
        temperature=0.15,
        system_prompt_suffix="重点关注政策条文原文和数据变化，保留完整数字和日期。",
    ),
    TrackRule(
        track_pattern="中考",
        role="logic_analyst",
        temperature=0.25,
        system_prompt_suffix="分析需紧扣上海中考政策背景，使用家长能理解的语言。",
    ),
    # ── 老年生活: warmer, simpler language ──
    TrackRule(
        track_pattern="老年",
        role="copywriter",
        temperature=0.9,
        system_prompt_suffix=(
            "请用温暖亲切、朴实的语气，像子女跟父母聊天一样。"
            "避免专业术语，多用短句。"
        ),
    ),
    TrackRule(
        track_pattern="老年",
        role="logic_analyst",
        temperature=0.4,
        system_prompt_suffix="分析角度应侧重实用性和安全性，重点考虑中老年人的理解能力。",
    ),
    # ── 金融: conservative, fact-based ──
    TrackRule(
        track_pattern="finance",
        role="logic_analyst",
        temperature=0.2,
        system_prompt_suffix="所有分析必须基于公开数据和技术指标，不做任何收益承诺或预测。",
    ),
    TrackRule(
        track_pattern="finance",
        role="copywriter",
        temperature=0.6,
        system_prompt_suffix="行文必须客观审慎，避免情绪化表述，结尾附免责声明。",
    ),
]


class ModelRouter:
    """Track-aware model routing with parameter tuning.

    Usage in any LangGraph node::

        router = ModelRouter(persona)
        text = await router.invoke("copywriter", prompt, system_prompt=sp)

    Adding a new track rule is one ``TrackRule(...)`` append to ``_TRACK_RULES``.
    """

    def __init__(self, persona: dict) -> None:
        self._persona = persona
        self._track = persona.get("track", "")
        self._models_cfg = persona.get("models", {})

    # -- public API ---------------------------------------------------------

    def route(self, role: str, context: dict | None = None) -> RouteConfig:
        """Resolve model + tuned parameters for *role*."""
        ctx = context or {}

        # 1. Model: YAML per-role → legacy primary → built-in default
        model = get_role_model(self._persona, role)
        fallback = get_fallback_model(self._persona)

        # 2. Base params for the role
        base = _ROLE_BASE_PARAMS.get(
            role, {"temperature": 0.7, "max_tokens": 4096},
        )
        temperature: float = base["temperature"]
        max_tokens: int = base["max_tokens"]
        suffix_parts: list[str] = []

        # 3. Apply matching track rules (in declaration order)
        for rule in _TRACK_RULES:
            if rule.matches(self._track, role, ctx):
                if rule.model:
                    model = rule.model
                if rule.temperature is not None:
                    temperature = rule.temperature
                if rule.max_tokens is not None:
                    max_tokens = rule.max_tokens
                if rule.system_prompt_suffix:
                    suffix_parts.append(rule.system_prompt_suffix)

        return RouteConfig(
            model=model,
            fallback=fallback,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt_suffix="\n".join(suffix_parts),
        )

    async def invoke(
        self,
        role: str,
        prompt: str,
        context: dict | None = None,
        **overrides: Any,
    ) -> str:
        """Route, tune, and invoke in one call.

        *overrides* (e.g. ``system_prompt``, ``temperature``) take highest
        priority, followed by track rules, then role base params.
        """
        rc = self.route(role, context)

        # Merge system_prompt: caller value + track suffix
        caller_sp: str = overrides.pop("system_prompt", "")
        if rc.system_prompt_suffix:
            sp = (
                f"{caller_sp}\n\n{rc.system_prompt_suffix}"
                if caller_sp
                else rc.system_prompt_suffix
            )
        else:
            sp = caller_sp

        kwargs: dict[str, Any] = {
            "system_prompt": sp,
            "temperature": overrides.pop("temperature", rc.temperature),
            "max_tokens": overrides.pop("max_tokens", rc.max_tokens),
            **overrides,
        }

        logger.info(
            "ModelRouter → role=%s model=%s fallback=%s temp=%.2f tokens=%d",
            role, rc.model, rc.fallback, kwargs["temperature"], kwargs["max_tokens"],
        )

        return await ModelAdapter.invoke_with_fallback(
            rc.model, rc.fallback, prompt, **kwargs,
        )


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

    def __init__(self, model_name: str = "gemini-2.5-pro"):
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
# OpenAI client
# ---------------------------------------------------------------------------

class OpenAIClient(BaseModelClient):
    """OpenAI GPT API client using the official SDK."""

    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — GPT calls will fail.")
        self._client = openai.AsyncOpenAI(api_key=api_key or "")

    async def invoke(self, prompt: str, **kwargs: Any) -> str:
        system_prompt = kwargs.get("system_prompt", "")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        text = response.choices[0].message.content or "" if response.choices else ""
        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0

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
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{img_data}"},
            })
        content.append({"type": "text", "text": prompt})

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})

        t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=max_tokens,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        text = response.choices[0].message.content or "" if response.choices else ""
        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0

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
    # Gemini
    ModelAdapter.register("gemini-2.5-pro", GeminiClient("gemini-2.5-pro"))
    ModelAdapter.register("gemini-2.5-flash", GeminiClient("gemini-2.5-flash"))
    ModelAdapter.register("gemini-2.0-flash", GeminiClient("gemini-2.0-flash"))
    # Claude
    ModelAdapter.register("claude-3.7-sonnet", ClaudeClient("claude-sonnet-4-20250514"))
    ModelAdapter.register("claude-3.7-opus", ClaudeClient("claude-3-opus-20240229"))
    # OpenAI
    if os.getenv("OPENAI_API_KEY"):
        ModelAdapter.register("gpt-4o", OpenAIClient("gpt-4o"))
        ModelAdapter.register("gpt-4o-mini", OpenAIClient("gpt-4o-mini"))
    else:
        logger.info("OPENAI_API_KEY not set — skipping GPT model registration.")
    logger.info("All models registered.")
