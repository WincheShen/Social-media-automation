"""Node 5: Review & Approval Gate

Routes content through one of three approval modes:
- auto:      Publish immediately (disabled for finance accounts)
- review:    Human-in-the-loop approval via terminal/UI
- scheduled: Queue for optimal time window publishing
"""

from __future__ import annotations

import logging

from src.graph.state import AgentState

logger = logging.getLogger(__name__)

# Tracks that MUST use review mode (cannot be set to auto)
FORCED_REVIEW_TRACKS = {"finance", "金融", "股票"}


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
        return {"approved": True}

    if review_mode == "scheduled":
        # TODO: Write content to publish queue (SQLite)
        # The scheduler will pick it up at the optimal time
        logger.info("[Node 5] Content queued for scheduled publishing.")
        return {"approved": True}

    # review mode — human in the loop
    # TODO: Replace with proper UI / interrupt mechanism
    print("\n" + "=" * 60)
    print(f"📝 内容审核 — 账号: {account_id}")
    print("=" * 60)
    print(f"标题: {state.get('draft_title', '(empty)')}")
    print(f"正文: {state.get('draft_content', '(empty)')[:500]}")
    print(f"标签: {state.get('draft_tags', [])}")
    print(f"图片: {state.get('visual_assets', [])}")
    print("=" * 60)

    user_input = input("输入 'approve' 确认发布, 其他内容拒绝: ").strip().lower()
    approved = user_input == "approve"

    if approved:
        logger.info("[Node 5] Content approved by human reviewer.")
    else:
        logger.info("[Node 5] Content rejected. Reason: %s", user_input)

    return {"approved": approved}
