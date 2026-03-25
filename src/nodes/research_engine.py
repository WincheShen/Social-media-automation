"""Node 2: Multi-VLM Research Engine

Dynamically selects models and data sources based on task type
and account configuration, then performs research & analysis.

Data sources:
- Tavily Web Search (general research)
- yfinance (market data)          — future
- PDF parser (policy documents)   — future
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from src.graph.state import AgentState
from src.infra.model_adapter import ModelAdapter
from src.infra.xhs_cli import XhsCliAdapter, get_adapter_for_account
from src.infra.xhs_cli_types import XhsCliError

logger = logging.getLogger(__name__)

# Task type → recommended model mapping
TASK_MODEL_MAP: dict[str, str] = {
    "policy_analysis": "gemini-1.5-pro",
    "market_analysis": "claude-3.7-sonnet",
    "trend_scan": "gemini-1.5-flash",
    "general": None,  # will use persona.primary_model
}


def _classify_task(task: str, track: str) -> str:
    """Classify the task to determine optimal model and data sources."""
    task_lower = task.lower()
    if any(kw in task_lower for kw in ["政策", "新规", "文件", "解读"]):
        return "policy_analysis"
    if any(kw in task_lower for kw in ["股票", "k线", "行情", "财报", "美股", "a股"]):
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


# ---------------------------------------------------------------------------
# Data-source adapters
# ---------------------------------------------------------------------------

async def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web via Tavily API and return structured results."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.warning("TAVILY_API_KEY not set — skipping web search.")
        return []

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_raw_content": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "score": item.get("score", 0),
        })
    logger.info("[Node 2] Tavily returned %d results for: %s", len(results), query)
    return results


def _build_search_queries(task: str, persona: dict) -> list[str]:
    """Generate search queries from task and persona keywords."""
    keywords = persona.get("keywords", [])
    queries = [task]
    # Add a keyword-enriched variant
    if keywords:
        top_kw = " ".join(keywords[:3])
        queries.append(f"{task} {top_kw}")
    return queries


# ---------------------------------------------------------------------------
# Analysis prompt
# ---------------------------------------------------------------------------

RESEARCH_PROMPT_TEMPLATE = """你是一位专业的内容研究员。请基于以下搜索结果，针对任务进行深入分析。

## 任务
{task}

## 目标受众
{audience}

## 搜索结果
{search_results}

## 要求
1. 提取与任务直接相关的关键信息和数据点
2. 识别目标受众最关心的核心痛点
3. 总结 3-5 个可用于内容创作的核心观点
4. 标注信息来源（URL）

请以 JSON 格式输出，结构如下：
```json
{{
  "key_facts": ["事实1", "事实2", ...],
  "pain_points": ["痛点1", "痛点2", ...],
  "content_angles": [
    {{"angle": "角度描述", "supporting_data": "支撑数据", "source_url": "来源URL"}},
    ...
  ],
  "summary": "一段话总结研究发现"
}}
```"""


def _format_search_results(results: list[dict]) -> str:
    """Format search results into a readable string for the LLM."""
    if not results:
        return "(无搜索结果)"
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"### 结果 {i}\n"
            f"**标题**: {r['title']}\n"
            f"**URL**: {r['url']}\n"
            f"**摘要**: {r['content']}\n"
        )
    return "\n".join(parts)


def _parse_research_response(text: str) -> dict:
    """Extract JSON from the LLM research response."""
    # Try to extract JSON block
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("[Node 2] Failed to parse research JSON, returning raw text.")
        return {
            "key_facts": [],
            "pain_points": [],
            "content_angles": [],
            "summary": text[:2000],
        }


# ---------------------------------------------------------------------------
# XHS site search (via xiaohongshu-skills CLI)
# ---------------------------------------------------------------------------

async def _xhs_search(
    adapter: XhsCliAdapter,
    keyword: str,
    sort_by: str = "最多点赞",
    note_type: str | None = "图文",
) -> list[dict]:
    """Search XHS in-app for competitor / trending notes."""
    try:
        feeds = await adapter.search_feeds(
            keyword=keyword, sort_by=sort_by, note_type=note_type,
        )
    except XhsCliError as e:
        logger.warning("[Node 2] XHS search failed: %s", e)
        return []

    results = []
    for f in feeds:
        results.append({
            "title": f.title,
            "url": f.url or f"xhs://feed/{f.feed_id}",
            "content": f"作者: {f.author}, 点赞: {f.likes}",
            "score": f.likes,
            "source": "xiaohongshu_search",
        })
    logger.info("[Node 2] XHS search returned %d results for: %s", len(results), keyword)
    return results


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

async def multi_vlm_research(state: AgentState) -> dict:
    """Graph node: perform research using dynamically selected models."""
    task = state["task"]
    persona = state["persona"]
    track = persona.get("track", "")
    memory = state.get("memory", [])

    task_type = _classify_task(task, track)
    primary_model, fallback_model = _select_model(task_type, persona)

    logger.info(
        "[Node 2] Research — task_type=%s, model=%s, fallback=%s",
        task_type, primary_model, fallback_model,
    )

    # 1a. External web search (Tavily)
    queries = _build_search_queries(task, persona)
    all_search_results: list[dict] = []
    data_sources: list[str] = []

    for query in queries:
        results = await _tavily_search(query)
        all_search_results.extend(results)
        if results:
            data_sources.append(f"tavily:{query}")

    # 1b. XHS in-app search (competitor / trending notes)
    try:
        adapter = get_adapter_for_account(persona)
        for query in queries[:1]:  # use primary query only
            xhs_results = await _xhs_search(adapter, query)
            all_search_results.extend(xhs_results)
            if xhs_results:
                data_sources.append(f"xhs_search:{query}")
    except Exception as e:
        logger.debug("[Node 2] XHS search unavailable: %s", e)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_results: list[dict] = []
    for r in all_search_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)

    # 2. Build analysis prompt
    audience = persona.get("persona", {}).get("audience", "通用读者")
    prompt = RESEARCH_PROMPT_TEMPLATE.format(
        task=task,
        audience=audience,
        search_results=_format_search_results(unique_results[:8]),
    )

    # Inject relevant memory as context
    system_prompt = persona.get("persona", {}).get("system_prompt", "")
    if memory:
        recent_successes = [
            m for m in memory if m.get("type") == "success"
        ][-3:]
        if recent_successes:
            memory_ctx = "\n".join(
                f"- [{m.get('task')}] 经验: {m.get('insight', '无')}"
                for m in recent_successes
            )
            system_prompt += f"\n\n## 历史成功经验（供参考）\n{memory_ctx}"

    # 3. Invoke LLM with fallback
    raw_response = await ModelAdapter.invoke_with_fallback(
        primary_model,
        fallback_model,
        prompt,
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=4096,
    )

    # 4. Parse structured results
    analysis = _parse_research_response(raw_response)

    research_results = [
        {
            "type": "web_search_analysis",
            "task_type": task_type,
            "model_used": primary_model,
            "raw_search_count": len(unique_results),
            "analysis": analysis,
            "raw_sources": unique_results[:8],
        }
    ]

    logger.info(
        "[Node 2] Research complete — %d sources, %d content angles.",
        len(unique_results),
        len(analysis.get("content_angles", [])),
    )

    return {
        "research_results": research_results,
        "data_sources": data_sources,
    }
