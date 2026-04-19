"""Node 2: Multi-VLM Research Engine

Dynamically selects models and data sources based on task type
and account configuration, then performs research & analysis.

Data sources:
- Tavily Web Search (general research)
- yfinance (market data)          — future
- PDF parser (policy documents)   — future
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse, parse_qs, unquote

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
# Search result quality filters
# ---------------------------------------------------------------------------

# Minimum Tavily relevance score (0–1). Results below this are noise.
_MIN_RELEVANCE_SCORE = 0.15

# Maximum age in days for web results. Older articles are dropped.
_MAX_AGE_DAYS = 30

# URL patterns that are almost always SEO spam or irrelevant
_SPAM_URL_PATTERNS: list[re.Pattern] = [
    re.compile(r"searchQuery=.*%[A-F0-9]{2}", re.IGNORECASE),   # encoded-junk query strings
    re.compile(r"(博彩|赌|棋牌|彩票|色情|porn|casino|gambling)", re.IGNORECASE),
]

# Domains that are never financial / policy news
_BLOCKED_DOMAINS = {
    "charteredaccountants.ie",
}

# Domains whose pages are help/docs, not news articles
_HELP_PAGE_PATTERNS: list[re.Pattern] = [
    re.compile(r"support\.[^/]+/topic"),      # e.g. support.futunn.com/topic43
    re.compile(r"/help/|/faq/|/docs/"),
]


def _extract_article_date(result: dict) -> datetime | None:
    """Try to extract a publication date from URL path or content snippet."""
    url = result.get("url", "")
    content = result.get("content", "")

    # Common URL date patterns: /2026-04-18/ or /20260418/ or /articles/2025-11-02/
    for pattern in (
        r"/(\d{4})-(\d{2})-(\d{2})/",
        r"/(\d{4})(\d{2})(\d{2})\d+",
        r"/articles/(\d{4})-(\d{2})-(\d{2})/",
        r"doc-\w+(\d{4})(\d{2})(\d{2})",
    ):
        m = re.search(pattern, url)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue

    # Try date in content: "2026-04-17 12:56:56" or "2025年11月2日"
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", content[:500])
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    return None


def _is_spam(result: dict) -> bool:
    """Detect SEO spam and irrelevant pages."""
    url = result.get("url", "")
    title = result.get("title", "")
    content = result.get("content", "")
    combined = f"{url} {title} {content}"

    # Blocked domains
    parsed = urlparse(url)
    domain = parsed.hostname or ""
    if domain.lstrip("www.") in _BLOCKED_DOMAINS:
        return True

    # URL pattern spam (encoded Chinese gambling keywords etc.)
    decoded_url = unquote(url)
    for pat in _SPAM_URL_PATTERNS:
        if pat.search(decoded_url):
            return True

    # Help / docs pages (not news)
    for pat in _HELP_PAGE_PATTERNS:
        if pat.search(url):
            return True

    return False


def _filter_search_results(
    results: list[dict],
    *,
    min_score: float = _MIN_RELEVANCE_SCORE,
    max_age_days: int = _MAX_AGE_DAYS,
) -> list[dict]:
    """Filter out low-quality, stale, and spam search results.

    Returns a new list sorted by score descending.
    """
    now = datetime.now()
    cutoff = now - timedelta(days=max_age_days)
    kept: list[dict] = []

    for r in results:
        # Skip XHS results (they use likes as score, not relevance)
        if r.get("source") == "xiaohongshu_search":
            kept.append(r)
            continue

        score = r.get("score", 0)

        # 1. Low relevance
        if score < min_score:
            logger.debug("[Filter] Dropped (score=%.3f < %.2f): %s", score, min_score, r.get("url", ""))
            continue

        # 2. Spam / irrelevant
        if _is_spam(r):
            logger.info("[Filter] Dropped (spam): %s", r.get("url", "")[:120])
            continue

        # 3. Stale content
        article_date = _extract_article_date(r)
        if article_date and article_date < cutoff:
            logger.info(
                "[Filter] Dropped (stale, %s > %d days): %s",
                article_date.strftime("%Y-%m-%d"), max_age_days, r.get("url", "")[:120],
            )
            continue

        kept.append(r)

    # Sort by relevance score descending (XHS results keep original order at bottom)
    web_results = [r for r in kept if r.get("source") != "xiaohongshu_search"]
    xhs_results = [r for r in kept if r.get("source") == "xiaohongshu_search"]
    web_results.sort(key=lambda r: r.get("score", 0), reverse=True)

    filtered = web_results + xhs_results
    dropped = len(results) - len(filtered)
    if dropped:
        logger.info("[Filter] Kept %d / %d results (%d dropped).", len(filtered), len(results), dropped)

    return filtered

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
- 如果包含小红书竞品数据，请额外提取：高赞帖的选题角度、标题写法、内容结构特点

请以 JSON 格式输出：
```json
{{
  "extracted_facts": [
    {{"fact": "事实描述", "source_url": "来源URL", "importance": "high/medium/low"}},
    ...
  ],
  "raw_data_points": ["数据1", "数据2", ...],
  "source_count": 0,
  "xhs_competitor_insights": {{
    "popular_angles": ["高赞帖常用的选题角度1", ...],
    "title_patterns": ["标题写法特点1", ...],
    "engagement_benchmarks": "点赞/收藏/评论的大致范围"
  }}
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

{strategy_section}## 要求
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
    """Format search results into a readable string for the LLM.

    Web results and XHS competitor results are presented in separate
    sections so the LLM can reason about them differently.
    """
    if not results:
        return "(无搜索结果)"

    web = [r for r in results if r.get("source") != "xiaohongshu_search"]
    xhs = [r for r in results if r.get("source") == "xiaohongshu_search"]

    parts: list[str] = []

    if web:
        parts.append("## 网页搜索结果\n")
        for i, r in enumerate(web, 1):
            parts.append(
                f"### 结果 {i}\n"
                f"**标题**: {r['title']}\n"
                f"**URL**: {r['url']}\n"
                f"**摘要**: {r['content']}\n"
            )

    if xhs:
        parts.append("## 小红书平台竞品（按点赞数排序）\n")
        # Sort by likes descending for clarity
        xhs_sorted = sorted(xhs, key=lambda r: r.get("score", 0), reverse=True)
        for i, r in enumerate(xhs_sorted, 1):
            parts.append(
                f"### 竞品 {i}（点赞 {r.get('score', 0)}）\n"
                f"**标题**: {r['title']}\n"
                f"**链接**: {r['url']}\n"
                f"**内容**: {r['content']}\n"
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
    top_n_detail: int = 5,
) -> list[dict]:
    """Search XHS in-app for competitor / trending notes.

    Fetches the search list, then loads full detail (content, collects,
    comments) for the top *top_n_detail* results so the research engine
    has real post content to work with — not just titles.
    """
    try:
        feeds = await adapter.search_feeds(
            keyword=keyword, sort_by=sort_by, note_type=note_type,
        )
    except XhsCliError as e:
        logger.warning("[Node 2] XHS search failed: %s", e)
        return []

    results: list[dict] = []
    # Fetch detail for top posts (concurrently, capped at top_n_detail)
    detail_tasks = []
    for f in feeds[:top_n_detail]:
        if f.feed_id and f.xsec_token:
            detail_tasks.append(adapter.get_feed_detail(f.feed_id, f.xsec_token))

    details: list[Any] = []
    if detail_tasks:
        details = await asyncio.gather(*detail_tasks, return_exceptions=True)

    detail_map: dict[str, Any] = {}
    for d in details:
        if isinstance(d, Exception):
            logger.debug("[Node 2] XHS detail fetch failed: %s", d)
            continue
        detail_map[d.feed_id] = d

    for f in feeds:
        detail = detail_map.get(f.feed_id)
        if detail and detail.content:
            # Rich result with full post content
            content_preview = detail.content[:500]
            content_str = (
                f"标题: {detail.title}\n"
                f"正文: {content_preview}\n"
                f"作者: {detail.author} | "
                f"点赞: {detail.likes} | 收藏: {detail.collects} | 评论: {detail.comments}"
            )
        else:
            # Fallback: basic info only
            content_str = f"标题: {f.title}\n作者: {f.author} | 点赞: {f.likes}"

        results.append({
            "title": detail.title if detail else f.title,
            "url": f.url or f"xhs://feed/{f.feed_id}",
            "content": content_str,
            "score": f.likes,
            "source": "xiaohongshu_search",
        })

    logger.info(
        "[Node 2] XHS search returned %d results (%d with detail) for: %s",
        len(results), len(detail_map), keyword,
    )
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

    # Use analyst's suggested topic if available (from Node 1.5)
    suggested_topic = state.get("suggested_topic") or task
    traffic_analysis = state.get("traffic_analysis") or {}

    if suggested_topic != task:
        logger.info("[Node 2] Using analyst-suggested topic: %s", suggested_topic)

    task_type = _classify_task(suggested_topic, track)
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
    queries = _build_search_queries(suggested_topic, persona)
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

    # Quality filter: drop spam, low-score, and stale results
    filtered_results = _filter_search_results(unique_results)

    # ── 2. Stage 1: Data Collector — extract facts (Gemini, large context) ──
    extract_prompt = EXTRACT_PROMPT_TEMPLATE.format(
        task=suggested_topic,
        search_results=_format_search_results(filtered_results[:10]),
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

    # Inject content strategy from traffic analyst if available
    strategy_section = ""
    content_strategy = traffic_analysis.get("content_strategy", [])
    if content_strategy:
        strategy_lines = "\n".join(f"- {s}" for s in content_strategy)
        strategy_section = f"## 流量分析师内容策略建议\n{strategy_lines}\n\n"

    analysis_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        task=suggested_topic,
        audience=audience,
        extracted_facts=facts_text,
        strategy_section=strategy_section,
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

    # Separate XHS competitor insights from general extraction
    xhs_insights = extraction.pop("xhs_competitor_insights", None) or {}

    research_results = [
        {
            "type": "web_search_analysis",
            "task_type": task_type,
            "models_used": {
                "data_collector": rc_collector.model,
                "logic_analyst": rc_analyst.model,
            },
            "raw_search_count": len(unique_results),
            "filtered_count": len(filtered_results),
            "extraction": extraction,
            "analysis": analysis,
            "xhs_competitor_insights": xhs_insights,
            "raw_sources": filtered_results[:10],
        }
    ]

    logger.info(
        "[Node 2] Research complete — %d sources (%d after filter), %d content angles.",
        len(unique_results),
        len(filtered_results),
        len(analysis.get("content_angles", [])),
    )

    return {
        "research_results": research_results,
        "data_sources": data_sources,
    }
