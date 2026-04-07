"""Monitor Worker — Consumes pending monitor tasks and collects post metrics.

Scans monitor_tasks.db for tasks whose scheduled_at has passed,
executes get-feed-detail via CLI, and writes metrics back to memory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.infra.xhs_cli import get_adapter_for_account
from src.nodes.monitor import collect_metrics_for_task, MONITOR_DB_PATH

logger = logging.getLogger(__name__)

MEMORY_DIR = Path("data/memory")


def get_pending_tasks_due_now() -> list[dict]:
    """Fetch all pending monitor tasks whose scheduled_at <= now."""
    if not MONITOR_DB_PATH.exists():
        return []
    
    conn = sqlite3.connect(str(MONITOR_DB_PATH))
    conn.row_factory = sqlite3.Row
    
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """SELECT id, account_id, post_url, feed_id, xsec_token, checkpoint, scheduled_at
           FROM monitor_tasks
           WHERE status = 'pending' AND scheduled_at <= ?
           ORDER BY scheduled_at ASC
           LIMIT 50""",
        (now,),
    )
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return tasks


def append_metrics_to_memory(account_id: str, metrics: dict, post_info: dict) -> None:
    """Append collected metrics to the account's memory file for Analyst to use."""
    memory_dir = MEMORY_DIR / account_id
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_path = memory_dir / "memory.json"
    
    if memory_path.exists():
        with open(memory_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"account_id": account_id, "entries": []}
    
    # Find the entry for this post and update its metrics
    post_url = post_info.get("post_url", "")
    checkpoint = metrics.get("checkpoint", "")
    
    updated = False
    for entry in reversed(data["entries"]):
        # Match by post_url or by recent timestamp
        if entry.get("post_url") == post_url or (
            entry.get("type") == "success" and not entry.get(f"metrics_{checkpoint}")
        ):
            entry[f"metrics_{checkpoint}"] = metrics
            entry["detail"] = entry.get("detail") or {}
            if isinstance(entry["detail"], dict):
                entry["detail"]["likes"] = metrics.get("likes", 0)
                entry["detail"]["collects"] = metrics.get("collects", 0)
                entry["detail"]["comments"] = metrics.get("comments", 0)
            updated = True
            break
    
    if not updated:
        # Create a new metrics-only entry if no matching post found
        data["entries"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "metrics_update",
            "checkpoint": checkpoint,
            "post_url": post_url,
            "metrics": metrics,
        })
    
    with open(memory_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    logger.info(
        "[MonitorWorker] Metrics written to memory — account=%s, checkpoint=%s",
        account_id, checkpoint,
    )


async def process_single_task(task: dict) -> bool:
    """Process a single monitor task. Returns True on success."""
    account_id = task["account_id"]
    task_id = task["id"]
    checkpoint = task.get("checkpoint", "")
    
    logger.info(
        "[MonitorWorker] Processing task %d — account=%s, checkpoint=%s",
        task_id, account_id, checkpoint,
    )
    
    try:
        adapter = get_adapter_for_account(account_id)
    except Exception as e:
        logger.error("[MonitorWorker] Failed to get adapter for %s: %s", account_id, e)
        return False
    
    metrics = await collect_metrics_for_task(adapter, task)
    
    if metrics:
        append_metrics_to_memory(account_id, metrics, task)
        return True
    
    return False


async def run_monitor_worker(max_tasks: int = 50) -> dict:
    """Main entry point: process all due monitor tasks.
    
    Returns:
        Summary dict with counts.
    """
    logger.info("[MonitorWorker] Starting monitor worker run...")
    
    tasks = get_pending_tasks_due_now()
    
    if not tasks:
        logger.info("[MonitorWorker] No pending tasks due.")
        return {"processed": 0, "success": 0, "failed": 0}
    
    logger.info("[MonitorWorker] Found %d pending tasks to process.", len(tasks))
    
    success = 0
    failed = 0
    
    for task in tasks[:max_tasks]:
        try:
            if await process_single_task(task):
                success += 1
            else:
                failed += 1
        except Exception as e:
            logger.error("[MonitorWorker] Task %d failed with exception: %s", task["id"], e)
            failed += 1
        
        # Small delay between tasks to avoid rate limiting
        await asyncio.sleep(1)
    
    summary = {
        "processed": success + failed,
        "success": success,
        "failed": failed,
    }
    
    logger.info(
        "[MonitorWorker] Run complete — processed=%d, success=%d, failed=%d",
        summary["processed"], summary["success"], summary["failed"],
    )
    
    return summary


async def main():
    """CLI entry point for manual testing."""
    from src.infra.logger import setup_logging
    from src.infra.model_adapter import init_models
    from src.infra.identity_registry import registry
    from dotenv import load_dotenv
    
    load_dotenv()
    setup_logging()
    init_models()
    registry.load_all()
    
    result = await run_monitor_worker()
    print(f"\nMonitor Worker Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
