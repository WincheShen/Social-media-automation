"""Node 7: Post-Publish Monitor

Schedules and performs data collection at key time points after publishing:
- T+2h:  Initial impressions & engagement (detect throttling)
- T+24h: Core performance metrics
- T+72h: Final metrics for long-tail analysis

Metric collection tasks are stored in SQLite and consumed by a
separate scheduler process (see src/scheduler.py — future).
Actual metric collection uses xiaohongshu-skills CLI ``get-feed-detail``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.graph.state import AgentState
from src.infra.xhs_cli import XhsCliAdapter, get_adapter_for_account
from src.infra.xhs_cli_types import XhsCliError

logger = logging.getLogger(__name__)

MONITOR_DB_PATH = Path("data/state/monitor_tasks.db")

# Collection schedule: (label, delay_hours)
COLLECTION_SCHEDULE = [
    ("T+2h", 2),
    ("T+24h", 24),
    ("T+72h", 72),
]


def _init_monitor_db() -> None:
    """Initialize the monitor tasks SQLite database."""
    MONITOR_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(MONITOR_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS monitor_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            post_url TEXT,
            feed_id TEXT,
            xsec_token TEXT,
            checkpoint TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            metrics_json TEXT,
            created_at TEXT,
            completed_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def _schedule_collection_tasks(
    account_id: str,
    post_url: str | None,
    published_at: str,
    feed_id: str | None = None,
    xsec_token: str | None = None,
) -> int:
    """Register metric collection tasks at T+2h, T+24h, T+72h."""
    _init_monitor_db()

    try:
        base_time = datetime.fromisoformat(published_at)
    except (ValueError, TypeError):
        base_time = datetime.now(timezone.utc)

    conn = sqlite3.connect(str(MONITOR_DB_PATH))
    count = 0
    for label, delay_hours in COLLECTION_SCHEDULE:
        scheduled_at = base_time + timedelta(hours=delay_hours)
        conn.execute(
            """INSERT INTO monitor_tasks
               (account_id, post_url, feed_id, xsec_token,
                checkpoint, scheduled_at, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                account_id,
                post_url,
                feed_id,
                xsec_token,
                label,
                scheduled_at.isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        count += 1
    conn.commit()
    conn.close()

    logger.info(
        "[Node 7] Scheduled %d collection tasks for %s (url=%s)",
        count, account_id, post_url,
    )
    return count


async def collect_metrics_for_task(
    adapter: XhsCliAdapter,
    task_row: dict,
) -> dict | None:
    """Execute a single metric collection task using CLI get-feed-detail.

    Called by the scheduler process when a task's scheduled_at arrives.
    Updates the SQLite row with collected metrics.

    Args:
        adapter: XhsCliAdapter for the account.
        task_row: Dict with keys: id, feed_id, xsec_token, checkpoint.

    Returns:
        Metrics dict or None on failure.
    """
    task_id = task_row["id"]
    feed_id = task_row.get("feed_id")
    xsec_token = task_row.get("xsec_token")

    if not feed_id or not xsec_token:
        logger.warning(
            "[Monitor] Task %d missing feed_id/xsec_token, skipping.", task_id,
        )
        _update_task_status(task_id, "skipped")
        return None

    try:
        detail = await adapter.get_feed_detail(feed_id, xsec_token)
    except XhsCliError as e:
        logger.error("[Monitor] Task %d collection failed: %s", task_id, e)
        _update_task_status(task_id, "failed")
        return None

    metrics = {
        "likes": detail.likes,
        "collects": detail.collects,
        "comments": detail.comments,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint": task_row.get("checkpoint"),
    }

    _update_task_status(task_id, "completed", metrics)
    logger.info(
        "[Monitor] Task %d completed — likes=%d, collects=%d, comments=%d",
        task_id, detail.likes, detail.collects, detail.comments,
    )
    return metrics


def _update_task_status(
    task_id: int,
    status: str,
    metrics: dict | None = None,
) -> None:
    """Update a monitor task's status and optional metrics in SQLite."""
    conn = sqlite3.connect(str(MONITOR_DB_PATH))
    conn.execute(
        """UPDATE monitor_tasks
           SET status = ?, metrics_json = ?, completed_at = ?
           WHERE id = ?""",
        (
            status,
            json.dumps(metrics, ensure_ascii=False) if metrics else None,
            datetime.now(timezone.utc).isoformat(),
            task_id,
        ),
    )
    conn.commit()
    conn.close()


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

    post_url = publish_result.get("url")
    published_at = publish_result.get("published_at", "")

    # Extract feed_id and xsec_token if available from publish result
    feed_id = publish_result.get("feed_id")
    xsec_token = publish_result.get("xsec_token")

    # Schedule collection tasks in SQLite
    task_count = _schedule_collection_tasks(
        account_id, post_url, published_at,
        feed_id=feed_id, xsec_token=xsec_token,
    )

    logger.info(
        "[Node 7] Monitor setup complete — account=%s, url=%s, tasks=%d",
        account_id, post_url, task_count,
    )

    post_metrics = {
        "impressions": 0,
        "likes": 0,
        "favorites": 0,
        "comments": 0,
        "shares": 0,
        "new_followers": 0,
        "engagement_rate": 0.0,
        "collection_status": "scheduled",
        "scheduled_tasks": task_count,
    }

    return {"post_metrics": post_metrics}
