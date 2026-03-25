"""Node 2: Multi-VLM Research Engine

Dynamically selects models and data sources based on task type
and account configuration, then performs research & analysis.
"""

from __future__ import annotations

import logging

from src.graph.state import AgentState
from src.infra.model_adapter import ModelAdapter

logger = logging.getLogger(__name__)

# Task type → recommended model mapping
TASK_MODEL_MAP: dict[str, str] = {
    "policy_analysis": "gemini-1.5-pro",
    "market_analysis": "claude-3.7-sonnet",
    "trend_scan": "gemini-1.5-flash",
    "general": None,  # will use persona.primary_model
}


def _classify_task(task: str, track: str) -> str:
    """Classify the task to determine optimal model and data sources.

    TODO: Replace with LLM-based classification for better accuracy.
    """
    task_lower = task.lower()
    if any(kw in task_lower for kw in ["政策", "新规", "文件", "解读"]):
        return "policy_analysis"
    if any(kw in task_lower for kw in ["股票", "K线", "行情", "财报", "美股", "A股"]):
        return "market_analysis"
    if any(kw in task_lower for kw in ["热点", "趋势", "话题", "养生"]):
        return "trend_scan"
    return "general"


def _select_model(task_type: str, persona: dict) -> tuple[str, str]:
    """Return (primary_model, fallback_model) for the task."""
    models_cfg = persona.get("models", {})
    fallback = models_cfg.get("fallback", "gemini-1.5-flash")

    recommended = TASK_MODEL_MAP.get(task_type)
    primary = recommended or models_cfg.get("primary", "gemini-1.5-pro")

    return primary, fallback


async def multi_vlm_research(state: AgentState) -> dict:
    """Graph node: perform research using dynamically selected models."""
    task = state["task"]
    persona = state["persona"]
    track = persona.get("track", "")

    task_type = _classify_task(task, track)
    primary_model, fallback_model = _select_model(task_type, persona)

    logger.info(
        "[Node 2] Research — task_type=%s, model=%s, fallback=%s",
        task_type,
        primary_model,
        fallback_model,
    )

    # TODO: Implement actual research logic
    # 1. Build research prompt from task + persona context
    # 2. Call data source adapters (web search, PDF, yfinance, etc.)
    # 3. Invoke model with fallback
    # 4. Parse and structure results

    research_results: list[dict] = []
    data_sources: list[str] = []

    return {
        "research_results": research_results,
        "data_sources": data_sources,
    }
