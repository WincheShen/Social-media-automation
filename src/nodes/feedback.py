"""Node 8: Feedback & Memory Update

Aggregates execution results (success/failure/rejection), generates
optimization insights, and persists them to account memory.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.graph.state import AgentState

logger = logging.getLogger(__name__)

MEMORY_DIR = Path("data/memory")


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

    with open(memory_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": outcome_type,
        "task": task,
        "detail": detail,
        "insight": None,  # TODO: Generate insight via LLM
    }

    _save_memory_entry(account_id, entry)

    # TODO: For successful posts, schedule LLM-based insight generation
    # after T+72h metrics are collected.

    return {"feedback_summary": f"[{outcome_type}] {task}"}
