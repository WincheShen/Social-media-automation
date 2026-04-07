"""Auto Task Creator — Creates daily tasks for accounts with auto_post enabled.

Reads account configs, checks if auto_post is enabled, and creates
tasks that automatically enter the workflow pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.infra.identity_registry import registry

logger = logging.getLogger(__name__)

TASKS_DB_PATH = Path("data/state/web_tasks.db")


def _init_tasks_db() -> None:
    """Ensure tasks database exists with correct schema."""
    TASKS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(TASKS_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'created',
            created_at TEXT,
            updated_at TEXT,
            draft_title TEXT,
            draft_content TEXT,
            draft_tags TEXT,
            research_summary TEXT,
            research_data TEXT,
            safety_issues TEXT,
            image_gen_prompt TEXT,
            post_url TEXT,
            error TEXT
        )
    """)
    conn.commit()
    conn.close()


def create_task(account_id: str, description: str) -> dict:
    """Create a new task in the database.
    
    Returns:
        Task dict with id and other fields.
    """
    _init_tasks_db()
    
    task_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()
    
    conn = sqlite3.connect(str(TASKS_DB_PATH))
    conn.execute(
        """INSERT INTO tasks (id, account_id, description, status, created_at, updated_at)
           VALUES (?, ?, ?, 'created', ?, ?)""",
        (task_id, account_id, description, now, now),
    )
    conn.commit()
    conn.close()
    
    logger.info("[TaskCreator] Created task %s for account %s", task_id, account_id)
    
    return {
        "id": task_id,
        "account_id": account_id,
        "description": description,
        "status": "created",
        "created_at": now,
    }


def get_today_task_count(account_id: str) -> int:
    """Get the number of tasks created today for an account."""
    if not TASKS_DB_PATH.exists():
        return 0
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(str(TASKS_DB_PATH))
    cursor = conn.execute(
        """SELECT COUNT(*) FROM tasks 
           WHERE account_id = ? AND created_at LIKE ?""",
        (account_id, f"{today}%"),
    )
    count = cursor.fetchone()[0]
    conn.close()
    
    return count


async def create_daily_tasks() -> dict:
    """Create daily tasks for all accounts with auto_post enabled.
    
    Returns:
        Summary dict with created task info.
    """
    logger.info("[TaskCreator] Starting daily task creation...")
    
    accounts = registry.list_accounts()
    created_tasks = []
    skipped = []
    
    for account_id in accounts:
        try:
            config = registry.get(account_id)
        except Exception as e:
            logger.warning("[TaskCreator] Failed to load config for %s: %s", account_id, e)
            skipped.append({"account_id": account_id, "reason": str(e)})
            continue
        
        schedule = config.get("schedule", {})
        
        # Check if auto_post is enabled
        if not schedule.get("auto_post", False):
            logger.debug("[TaskCreator] Skipping %s — auto_post disabled", account_id)
            skipped.append({"account_id": account_id, "reason": "auto_post disabled"})
            continue
        
        # Check daily limit
        max_daily = schedule.get("max_daily_posts", 1)
        today_count = get_today_task_count(account_id)
        
        if today_count >= max_daily:
            logger.info(
                "[TaskCreator] Skipping %s — daily limit reached (%d/%d)",
                account_id, today_count, max_daily,
            )
            skipped.append({"account_id": account_id, "reason": f"daily limit {today_count}/{max_daily}"})
            continue
        
        # Create task with auto-generated description
        # The Analyst node will determine the actual topic based on trends + history
        persona = config.get("persona", {})
        keywords = config.get("keywords", [])
        
        description = f"自动选题：基于今日热点和历史表现，围绕「{', '.join(keywords[:3])}」方向创作"
        
        task = create_task(account_id, description)
        created_tasks.append(task)
        
        logger.info(
            "[TaskCreator] Created task for %s — id=%s, desc=%s",
            account_id, task["id"], description[:50],
        )
    
    summary = {
        "created": len(created_tasks),
        "skipped": len(skipped),
        "tasks": created_tasks,
        "skipped_details": skipped,
    }
    
    logger.info(
        "[TaskCreator] Daily task creation complete — created=%d, skipped=%d",
        summary["created"], summary["skipped"],
    )
    
    return summary


async def run_workflow_for_task(task: dict) -> None:
    """Trigger the workflow for a created task.
    
    This imports and calls the workflow runner, similar to what
    the Web Admin does when a task is created.
    """
    from src.graph.state import AgentState
    from src.graph.workflow import build_graph
    from src.infra.model_adapter import usage_tracker
    
    account_id = task["account_id"]
    task_id = task["id"]
    description = task["description"]
    
    logger.info("[TaskCreator] Starting workflow for task %s", task_id)
    
    # Update task status to running
    _update_task_status(task_id, "running")
    
    try:
        graph = build_graph()
        
        initial_state: AgentState = {
            "account_id": account_id,
            "task": description,
            "persona": {},
            "memory": [],
            "research_results": [],
            "data_sources": [],
            "draft_title": "",
            "draft_content": "",
            "draft_tags": [],
            "visual_assets": [],
            "safety_passed": False,
            "safety_issues": [],
            "review_mode": "review",
            "approved": False,
            "publish_result": None,
            "post_metrics": None,
            "feedback_summary": None,
        }
        
        result = await graph.ainvoke(initial_state)
        
        # Update task with results
        _update_task_with_result(task_id, result)
        
        total_in, total_out = usage_tracker.total_tokens
        logger.info(
            "[TaskCreator] Workflow complete for %s — tokens=%d/%d, cost=$%.4f",
            task_id, total_in, total_out, usage_tracker.total_cost,
        )
        
    except Exception as e:
        logger.error("[TaskCreator] Workflow failed for %s: %s", task_id, e)
        _update_task_status(task_id, "failed", error=str(e))


def _update_task_status(task_id: str, status: str, error: str | None = None) -> None:
    """Update task status in database."""
    conn = sqlite3.connect(str(TASKS_DB_PATH))
    now = datetime.now(timezone.utc).isoformat()
    
    if error:
        conn.execute(
            "UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error, now, task_id),
        )
    else:
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, task_id),
        )
    
    conn.commit()
    conn.close()


def _update_task_with_result(task_id: str, result: dict) -> None:
    """Update task with workflow results."""
    import json
    
    conn = sqlite3.connect(str(TASKS_DB_PATH))
    now = datetime.now(timezone.utc).isoformat()
    
    # Determine final status based on result
    if not result.get("safety_passed", True):
        status = "failed"
    elif result.get("review_mode") == "review" and not result.get("approved"):
        status = "reviewing"
    elif result.get("publish_result", {}).get("status") == "success":
        status = "published"
    else:
        status = "reviewing"
    
    conn.execute(
        """UPDATE tasks SET
           status = ?,
           draft_title = ?,
           draft_content = ?,
           draft_tags = ?,
           research_summary = ?,
           safety_issues = ?,
           post_url = ?,
           updated_at = ?
           WHERE id = ?""",
        (
            status,
            result.get("draft_title", ""),
            result.get("draft_content", ""),
            json.dumps(result.get("draft_tags", []), ensure_ascii=False),
            result.get("traffic_analysis", {}).get("topic_reasoning", ""),
            json.dumps(result.get("safety_issues", []), ensure_ascii=False),
            result.get("publish_result", {}).get("url"),
            now,
            task_id,
        ),
    )
    conn.commit()
    conn.close()


async def create_and_run_daily_tasks() -> dict:
    """Create daily tasks and run workflows for them.
    
    This is the main entry point for the scheduler.
    """
    summary = await create_daily_tasks()
    
    for task in summary["tasks"]:
        await run_workflow_for_task(task)
    
    return summary


async def main():
    """CLI entry point for manual testing."""
    from src.infra.logger import setup_logging
    from src.infra.model_adapter import init_models
    from dotenv import load_dotenv
    
    load_dotenv()
    setup_logging()
    init_models()
    registry.load_all()
    
    # Just create tasks, don't run workflows (for testing)
    result = await create_daily_tasks()
    print(f"\nTask Creator Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
