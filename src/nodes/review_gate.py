"""Node 5: Review & Approval Gate

Routes content through one of three approval modes:
- auto:      Publish immediately (disabled for finance accounts)
- review:    Human-in-the-loop approval via terminal/UI
- scheduled: Queue for optimal time window publishing
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.graph.state import AgentState

logger = logging.getLogger(__name__)

# Tracks that MUST use review mode (cannot be set to auto)
FORCED_REVIEW_TRACKS = {"finance", "金融", "股票"}

QUEUE_DB_PATH = Path("data/queue/publish_queue.db")


def _init_queue_db() -> None:
    """Initialize the publish queue SQLite database."""
    QUEUE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(QUEUE_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS publish_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            title TEXT,
            content TEXT,
            tags TEXT,
            visual_assets TEXT,
            scheduled_window TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            published_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def _enqueue_content(state: AgentState) -> int:
    """Write content to the scheduled publish queue. Returns queue ID."""
    _init_queue_db()
    persona = state["persona"]
    schedule = persona.get("schedule", {})
    windows = schedule.get("post_windows", [])

    conn = sqlite3.connect(str(QUEUE_DB_PATH))
    cursor = conn.execute(
        """INSERT INTO publish_queue
           (account_id, title, content, tags, visual_assets, scheduled_window, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (
            state["account_id"],
            state.get("draft_title", ""),
            state.get("draft_content", ""),
            json.dumps(state.get("draft_tags", []), ensure_ascii=False),
            json.dumps(state.get("visual_assets", []), ensure_ascii=False),
            json.dumps(windows, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    queue_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return queue_id


def _display_review(state: AgentState) -> None:
    """Display content preview in terminal for human review."""
    account_id = state["account_id"]
    title = state.get("draft_title", "(empty)")
    content = state.get("draft_content", "(empty)")
    tags = state.get("draft_tags", [])
    images = state.get("visual_assets", [])
    safety_issues = state.get("safety_issues", [])

    print("\n")
    print("┌" + "─" * 58 + "┐")
    print(f"│{'📝 内容审核':^54}│")
    print("├" + "─" * 58 + "┤")
    print(f"│ 账号: {account_id:<51}│")
    print("├" + "─" * 58 + "┤")
    print(f"│ 标题: {title:<51}│")
    print("├" + "─" * 58 + "┤")

    # Show content in chunks
    print("│ 正文:                                                    │")
    for i in range(0, min(len(content), 500), 54):
        line = content[i:i + 54]
        print(f"│   {line:<55}│")
    if len(content) > 500:
        print(f"│   ... (共{len(content)}字){'':>42}│")

    print("├" + "─" * 58 + "┤")
    tag_str = ", ".join(tags)
    print(f"│ 标签: {tag_str[:51]:<51}│")
    print(f"│ 图片: {len(images)} 个文件{'':>42}│")

    if safety_issues:
        print("├" + "─" * 58 + "┤")
        print(f"│ ⚠️  安全提示:{'':>43}│")
        for issue in safety_issues[:3]:
            print(f"│   {issue[:54]:<55}│")

    print("└" + "─" * 58 + "┘")


async def review_gate(state: AgentState) -> dict:
    """Graph node: handle content approval based on review_mode."""
    account_id = state["account_id"]
    review_mode = state.get("review_mode", "review")
    persona = state["persona"]
    track = persona.get("track", "")

    # Enforce review mode for restricted tracks
    if track in FORCED_REVIEW_TRACKS and review_mode == "auto":
        logger.warning(
            "[Node 5] Track '%s' requires review mode. Overriding 'auto' → 'review'.",
            track,
        )
        review_mode = "review"

    logger.info(
        "[Node 5] Review gate — account=%s, mode=%s", account_id, review_mode
    )

    if review_mode == "auto":
        logger.info("[Node 5] Auto-approved.")
        return {"approved": True}

    if review_mode == "scheduled":
        queue_id = _enqueue_content(state)
        logger.info(
            "[Node 5] Content queued for scheduled publishing (queue_id=%d).",
            queue_id,
        )
        # For scheduled mode, we still approve — the scheduler handles timing
        return {"approved": True}

    # review mode — human in the loop
    _display_review(state)

    print("\n  操作: [a]pprove 确认发布 | [r]eject 拒绝 | [e]dit 修改后重试")
    user_input = input("  请输入: ").strip().lower()

    if user_input in ("a", "approve"):
        logger.info("[Node 5] Content approved by human reviewer.")
        return {"approved": True}
    else:
        reason = user_input if user_input not in ("r", "reject") else "人工拒绝"
        logger.info("[Node 5] Content rejected. Reason: %s", reason)
        return {"approved": False}
