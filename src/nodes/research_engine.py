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
from src.infra.model_adapter import ModelRouter
from src.infra.xhs_cli import XhsCliAdapter, get_adapter_for_account
from src.infra.xhs_cli_types import XhsCliError

logger = logging.getLogger(__name__)

def _classify_task(task: str, track: str) -> str:
    """Classify the task to determine data-source strategy."""
    task_lower = task.lower()
    if any(kw in task_lower for kw in ["政策", "新规", "文件", "解读"]):
        return "policy_analysis"
    if any(kw in task_lower for kw in ["股票", "k线", "行情", "财报", "美股", "a股"]):
        return "market_analysis"
    if any(kw in task_lower for kw in ["热点", "趋势", "话题", "养生"]):
        return "trend_scan"
    return "general"


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

# ---------------------------------------------------------------------------
# Stage 1 prompt: Data Collector — extract structured facts (Gemini)
# ---------------------------------------------------------------------------

EXTRACT_PROMPT_TEMPLATE = """你是一位专业的数据采集员。请从以下搜索结果中提取与任务相关的关键信息。

## 任务
{task}

## 搜索结果
{search_results}

## 要求
- 提取所有与任务直接相关的事实、数据点、政策条文和引用
- 保留数据来源 URL
- 按重要程度排序
- 不要做分析判断，只做信息提取和整理

请以 JSON 格式输出：
```json
{{
  "extracted_facts": [
    {{"fact": "事实描述", "source_url": "来源URL", "importance": "high/medium/low"}},
    ...
  ],
  "raw_data_points": ["数据1", "数据2", ...],
  "source_count": 0
}}
```"""

# ---------------------------------------------------------------------------
# Stage 2 prompt: Logic Analyst — deep analysis (Claude Opus)
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT_TEMPLATE = """你是一位逻辑严密的深度分析师。请基于以下已提取的事实数据，进行深入分析。

## 任务
{task}

## 目标受众
{audience}

## 已提取的事实数据
{extracted_facts}

## 要求
1. 基于事实数据进行严密的逻辑推理，不要编造信息
2. 识别目标受众最关心的核心痛点
3. 提炼 3-5 个有数据支撑的内容观点
4. 每个观点必须有对应的事实依据

请以 JSON 格式输出：
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
    # Try to extract JSON from code-fenced block
    for fence in ("```json", "```"):
        if fence in text:
            start = text.index(fence) + len(fence)
            end = text.find("```", start)
            text = text[start:end].strip() if end != -1 else text[start:].strip()
            break
    else:
        # No code fence — try to find a raw JSON object
        brace = text.find("{")
        if brace != -1:
            text = text[brace:]

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
    """Graph node: two-stage research using role-specific models.

    Stage 1 (data_collector / Gemini): Extract structured facts from search results.
    Stage 2 (logic_analyst / Claude Opus): Deep analysis of extracted facts.
    """
    task = state["task"]
    persona = state["persona"]
    track = persona.get("track", "")
    memory = state.get("memory", [])

    task_type = _classify_task(task, track)
    router = ModelRouter(persona)
    ctx = {"task_type": task_type}
    rc_collector = router.route("data_collector", ctx)
    rc_analyst = router.route("logic_analyst", ctx)

    logger.info(
        "[Node 2] Research — task_type=%s, collector=%s(temp=%.2f), analyst=%s(temp=%.2f)",
        task_type, rc_collector.model, rc_collector.temperature,
        rc_analyst.model, rc_analyst.temperature,
    )

    # ── 1. Data gathering (API-based, no LLM) ──
    queries = _build_search_queries(task, persona)
    all_search_results: list[dict] = []
    data_sources: list[str] = []

    for query in queries:
        results = await _tavily_search(query)
        all_search_results.extend(results)
        if results:
            data_sources.append(f"tavily:{query}")

    # XHS in-app search
    try:
        adapter = get_adapter_for_account(persona)
        for query in queries[:1]:
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

    # ── 2. Stage 1: Data Collector — extract facts (Gemini, large context) ──
    extract_prompt = EXTRACT_PROMPT_TEMPLATE.format(
        task=task,
        search_results=_format_search_results(unique_results[:10]),
    )

    raw_extraction = await router.invoke("data_collector", extract_prompt, context=ctx)
    extraction = _parse_research_response(raw_extraction)

    logger.info(
        "[Node 2] Stage 1 (data_collector=%s) extracted %d facts.",
        rc_collector.model,
        len(extraction.get("extracted_facts", extraction.get("key_facts", []))),
    )

    # ── 3. Stage 2: Logic Analyst — deep analysis (Claude Opus) ──
    audience = persona.get("persona", {}).get("audience", "通用读者")

    # Format extracted facts for the analyst
    facts_list = extraction.get("extracted_facts", [])
    if facts_list:
        facts_text = "\n".join(
            f"- [{f.get('importance', 'medium')}] {f.get('fact', str(f))} (来源: {f.get('source_url', 'N/A')})"
            for f in facts_list
        )
    else:
        # Fallback: use raw extraction summary
        facts_text = extraction.get("summary", json.dumps(extraction, ensure_ascii=False)[:2000])

    analysis_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        task=task,
        audience=audience,
        extracted_facts=facts_text,
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

    raw_analysis = await router.invoke(
        "logic_analyst", analysis_prompt,
        context=ctx,
        system_prompt=system_prompt,
    )

    analysis = _parse_research_response(raw_analysis)

    logger.info(
        "[Node 2] Stage 2 (logic_analyst=%s) — %d content angles.",
        rc_analyst.model,
        len(analysis.get("content_angles", [])),
    )

    research_results = [
        {
            "type": "web_search_analysis",
            "task_type": task_type,
            "models_used": {
                "data_collector": rc_collector.model,
                "logic_analyst": rc_analyst.model,
            },
            "raw_search_count": len(unique_results),
            "extraction": extraction,
            "analysis": analysis,
            "raw_sources": unique_results[:10],
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
