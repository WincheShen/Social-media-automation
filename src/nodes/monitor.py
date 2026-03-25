"""Node 7: Post-Publish Monitor

Schedules and performs data collection at key time points after publishing:
- T+2h:  Initial impressions & engagement (detect throttling)
- T+24h: Core performance metrics
- T+72h: Final metrics for long-tail analysis
"""

from __future__ import annotations

import logging

from src.graph.state import AgentState

logger = logging.getLogger(__name__)


async def post_publish_monitor(state: AgentState) -> dict:
    """Graph node: schedule post-publish metric collection."""
    publish_result = state.get("publish_result", {})
    account_id = state["account_id"]

    if publish_result.get("status") != "success":
        logger.warning(
            "[Node 7] Skipping monitor — publish was not successful for %s.",
            account_id,
        )
        return {"post_metrics": None}

    logger.info(
        "[Node 7] Scheduling metric collection for account: %s, url: %s",
        account_id,
        publish_result.get("url"),
    )

    # TODO: Implement metric collection scheduling
    # 1. Register T+2h, T+24h, T+72h collection tasks
    # 2. Each task: open browser → navigate to post → scrape metrics
    # 3. Store metrics in data/memory/{account_id}/

    post_metrics = {
        "impressions": 0,
        "likes": 0,
        "favorites": 0,
        "comments": 0,
        "shares": 0,
        "new_followers": 0,
        "engagement_rate": 0.0,
        "collection_status": "scheduled",
    }

    return {"post_metrics": post_metrics}
