"""Node 8: Feedback & Memory Update

Aggregates execution results (success/failure/rejection), generates
optimization insights via LLM, and persists them to account memory.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.graph.state import AgentState
from src.infra.model_adapter import ModelRouter

logger = logging.getLogger(__name__)

MEMORY_DIR = Path("data/memory")

INSIGHT_PROMPT_TEMPLATE = """你是一位资深的社交媒体运营分析师。请分析以下内容发布记录并给出简要洞察。

## 账号人设
{persona_name} — {persona_desc}

## 本次任务
{task}

## 执行结果
- 状态: {outcome}
- 标题: {title}
- 正文长度: {content_len}字
- 标签: {tags}
{extra_detail}

## 请给出
1. 一句话总结本次执行结果
2. 如果成功：哪些做法值得复用？标题/选题/配图策略如何？
3. 如果失败：根本原因是什么？下次应如何调整？

请用一段话回复（100字以内），直接给结论，不要客套话。"""


def _save_memory_entry(account_id: str, entry: dict) -> None:
    """Append a new entry to the account's memory file."""
    memory_dir = MEMORY_DIR / account_id
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_path = memory_dir / "memory.json"

    if memory_path.exists():
        with open(memory_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"account_id": account_id, "entries": []}

    data["entries"].append(entry)

    # Keep memory bounded: retain last 100 entries
    if len(data["entries"]) > 100:
        data["entries"] = data["entries"][-100:]

    with open(memory_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def _generate_insight(state: AgentState, outcome_type: str) -> str | None:
    """Generate a brief insight about this run via LLM (uses Flash for speed)."""
    persona = state.get("persona", {})
    persona_cfg = persona.get("persona", {})

    extra_detail = ""
    if outcome_type == "safety_blocked":
        issues = state.get("safety_issues", [])
        extra_detail = f"- 安全问题: {', '.join(issues)}"
    elif outcome_type == "publish_failed":
        error = state.get("publish_result", {}).get("error", "未知")
        extra_detail = f"- 错误信息: {error}"

    prompt = INSIGHT_PROMPT_TEMPLATE.format(
        persona_name=persona_cfg.get("name", "未知"),
        persona_desc=persona_cfg.get("description", ""),
        task=state.get("task", ""),
        outcome=outcome_type,
        title=state.get("draft_title", "(无)"),
        content_len=len(state.get("draft_content", "")),
        tags=", ".join(state.get("draft_tags", [])),
        extra_detail=extra_detail,
    )

    router = ModelRouter(persona)

    try:
        insight = await router.invoke("strategist", prompt)
        return insight.strip()
    except Exception as e:
        logger.warning("[Node 8] Failed to generate insight: %s", e)
        return None


def _print_summary(account_id: str, task: str, outcome_type: str, insight: str | None) -> None:
    """Print a terminal summary of the workflow result."""
    status_icons = {
        "success": "✅",
        "safety_blocked": "🚫",
        "rejected": "❌",
        "publish_failed": "⚠️",
    }
    icon = status_icons.get(outcome_type, "❓")

    print(f"\n{icon} [{account_id}] {outcome_type.upper()}: {task}")
    if insight:
        print(f"   💡 {insight}")
    print()


async def feedback_memory_update(state: AgentState) -> dict:
    """Graph node: record results and update account memory."""
    account_id = state["account_id"]
    task = state["task"]

    logger.info("[Node 8] Updating memory for account: %s", account_id)

    # Determine outcome type
    if not state.get("safety_passed", True):
        outcome_type = "safety_blocked"
        detail = state.get("safety_issues", [])
    elif not state.get("approved", True):
        outcome_type = "rejected"
        detail = "Content rejected during review."
    elif state.get("publish_result", {}).get("status") == "success":
        outcome_type = "success"
        detail = state.get("post_metrics")
    else:
        outcome_type = "publish_failed"
        detail = state.get("publish_result", {}).get("error")

    # Generate insight via LLM
    insight = await _generate_insight(state, outcome_type)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": outcome_type,
        "task": task,
        "title": state.get("draft_title", ""),
        "tags": state.get("draft_tags", []),
        "data_sources": state.get("data_sources", []),
        "detail": detail,
        "insight": insight,
    }

    _save_memory_entry(account_id, entry)
    _print_summary(account_id, task, outcome_type, insight)

    return {"feedback_summary": f"[{outcome_type}] {task} — {insight or ''}"}
