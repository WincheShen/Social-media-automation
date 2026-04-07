"""Node 1.5: Traffic Analyst — Attribution & Topic Selection

Reads the account's historical memory (past posts + metrics), performs
traffic attribution analysis (why some posts did well / poorly), and
recommends today's topic direction for the research + creative nodes.

Position in graph: context_loader → analyst → research → creative → ...
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.graph.state import AgentState
from src.infra.model_adapter import ModelRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ATTRIBUTION_PROMPT = """你是一位专业的社交媒体流量分析师。请根据以下历史发帖记录，进行流量归因分析并推荐今日选题。

## 账号人设
{persona_name} — {persona_desc}
目标受众: {audience}
账号关键词: {keywords}

## 历史发帖记录（最近 {entry_count} 条）
{memory_entries}

## 当前任务方向（用户指定）
{task}

## 分析要求
1. **高流量归因**：哪些帖子表现好？总结共性（选题类型、标题特征、内容角度、发布时机）
2. **低流量归因**：哪些帖子表现差？找出原因（选题太泛、内容太专业、缺乏共鸣等）
3. **今日选题推荐**：基于归因结论 + 当前任务方向 + 账号人设，推荐最有潜力的具体选题
4. **内容策略建议**：给创作师的 2-3 条具体建议（标题风格、内容结构、情绪基调）

请以 JSON 格式输出：
```json
{{
  "high_traffic_patterns": [
    {{"pattern": "特征描述", "example_title": "举例标题", "reason": "为什么有流量"}}
  ],
  "low_traffic_patterns": [
    {{"pattern": "特征描述", "example_title": "举例标题", "reason": "为什么没流量"}}
  ],
  "suggested_topic": "今日推荐的具体选题（一句话）",
  "topic_reasoning": "为什么推荐这个选题（50字以内）",
  "content_strategy": ["建议1", "建议2", "建议3"],
  "confidence": "high/medium/low"
}}
```"""

NO_HISTORY_PROMPT = """你是一位专业的社交媒体运营顾问。该账号暂无历史数据，请基于账号定位推荐首篇选题。

## 账号人设
{persona_name} — {persona_desc}
目标受众: {audience}
账号关键词: {keywords}

## 用户指定任务方向
{task}

请推荐一个适合该账号的具体选题，输出 JSON：
```json
{{
  "high_traffic_patterns": [],
  "low_traffic_patterns": [],
  "suggested_topic": "推荐选题（一句话）",
  "topic_reasoning": "推荐理由（50字以内）",
  "content_strategy": ["建议1", "建议2"],
  "confidence": "low"
}}
```"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_memory_entries(memory: list[dict]) -> str:
    """Format memory entries into a readable text for the LLM."""
    if not memory:
        return "(暂无历史记录)"

    lines = []
    for i, entry in enumerate(memory, 1):
        ts = entry.get("timestamp", "")[:10]
        outcome = entry.get("type", "unknown")
        title = entry.get("title", "(无标题)")
        tags = ", ".join(entry.get("tags", []))
        insight = entry.get("insight", "")
        detail = entry.get("detail", "")

        # Extract metrics if stored
        metrics_str = ""
        if isinstance(detail, dict):
            m = detail
            parts = []
            if m.get("likes"):
                parts.append(f"点赞{m['likes']}")
            if m.get("favorites"):
                parts.append(f"收藏{m['favorites']}")
            if m.get("comments"):
                parts.append(f"评论{m['comments']}")
            if m.get("views"):
                parts.append(f"阅读{m['views']}")
            metrics_str = f" | 数据: {', '.join(parts)}" if parts else ""

        outcome_icon = {
            "success": "✅",
            "safety_blocked": "🚫",
            "rejected": "❌",
            "publish_failed": "⚠️",
        }.get(outcome, "❓")

        lines.append(
            f"{i}. [{ts}] {outcome_icon} {outcome.upper()}\n"
            f"   标题: 《{title}》\n"
            f"   标签: {tags or '无'}{metrics_str}\n"
            f"   洞察: {insight or '无'}\n"
        )

    return "\n".join(lines)


def _parse_analyst_response(text: str) -> dict:
    """Extract JSON from the LLM analyst response."""
    for fence in ("```json", "```"):
        if fence in text:
            start = text.index(fence) + len(fence)
            end = text.find("```", start)
            text = text[start:end].strip() if end != -1 else text[start:].strip()
            break
    else:
        brace = text.find("{")
        if brace != -1:
            text = text[brace:]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("[Node 1.5] Failed to parse analyst JSON.")
        return {
            "high_traffic_patterns": [],
            "low_traffic_patterns": [],
            "suggested_topic": "",
            "topic_reasoning": text[:200],
            "content_strategy": [],
            "confidence": "low",
        }


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

async def traffic_analyst(state: AgentState) -> dict:
    """Graph node: analyse historical traffic and suggest today's topic.

    Reads memory loaded by context_loader, runs attribution analysis via
    Logic Analyst (Claude Opus), and returns:
    - traffic_analysis: full attribution report
    - suggested_topic: recommended topic string (used by research_engine)
    """
    account_id = state["account_id"]
    task = state["task"]
    persona = state["persona"]
    memory = state.get("memory", [])

    persona_cfg = persona.get("persona", {})
    persona_name = persona_cfg.get("name", account_id)
    persona_desc = persona_cfg.get("description", "")
    audience = persona_cfg.get("audience", "通用读者")
    keywords = ", ".join(persona.get("keywords", []))

    logger.info(
        "[Node 1.5] Traffic attribution for %s — %d memory entries available.",
        account_id,
        len(memory),
    )

    router = ModelRouter(persona)

    # Choose prompt based on whether we have history
    successful_entries = [m for m in memory if m.get("type") == "success"]

    if len(memory) >= 3:
        prompt = ATTRIBUTION_PROMPT.format(
            persona_name=persona_name,
            persona_desc=persona_desc,
            audience=audience,
            keywords=keywords,
            entry_count=len(memory),
            memory_entries=_format_memory_entries(memory),
            task=task,
        )
    else:
        logger.info("[Node 1.5] Insufficient history (%d entries), using cold-start prompt.", len(memory))
        prompt = NO_HISTORY_PROMPT.format(
            persona_name=persona_name,
            persona_desc=persona_desc,
            audience=audience,
            keywords=keywords,
            task=task,
        )

    try:
        raw = await router.invoke("logic_analyst", prompt)
        analysis = _parse_analyst_response(raw)
    except Exception as e:
        logger.warning("[Node 1.5] Analyst LLM call failed: %s — using task as-is.", e)
        analysis = {
            "high_traffic_patterns": [],
            "low_traffic_patterns": [],
            "suggested_topic": task,
            "topic_reasoning": "LLM调用失败，使用原始任务描述",
            "content_strategy": [],
            "confidence": "low",
        }

    suggested_topic = analysis.get("suggested_topic", "").strip() or task

    logger.info(
        "[Node 1.5] Analysis complete — suggested_topic='%s' (confidence=%s), "
        "high_patterns=%d, low_patterns=%d",
        suggested_topic,
        analysis.get("confidence", "unknown"),
        len(analysis.get("high_traffic_patterns", [])),
        len(analysis.get("low_traffic_patterns", [])),
    )

    analysis["generated_at"] = datetime.now(timezone.utc).isoformat()
    analysis["based_on_entries"] = len(memory)
    analysis["successful_entries"] = len(successful_entries)

    return {
        "traffic_analysis": analysis,
        "suggested_topic": suggested_topic,
    }
