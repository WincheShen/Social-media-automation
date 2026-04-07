"""Daily Scheduler — Main scheduler using APScheduler.

Orchestrates all automated jobs:
- Morning: Monitor worker (collect T+24h data)
- Mid-morning: Create and run daily tasks
- Noon: Social engagement
- Evening: Monitor worker (collect T+2h data)

Usage:
    python -m src.scheduler.daily_scheduler
    python -m src.scheduler.daily_scheduler --run-now monitor
    python -m src.scheduler.daily_scheduler --run-now tasks
    python -m src.scheduler.daily_scheduler --run-now social
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Default schedule (can be overridden via config)
DEFAULT_SCHEDULE = {
    "monitor_morning": "0 8 * * *",      # 08:00 daily
    "daily_tasks": "0 9 * * *",          # 09:00 daily
    "social_engagement": "0 12 * * *",   # 12:00 daily
    "monitor_evening": "0 20 * * *",     # 20:00 daily
}


class DailyScheduler:
    """Main scheduler class that manages all automated jobs."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._setup_done = False
    
    def setup(self) -> None:
        """Initialize the scheduler with all jobs."""
        if self._setup_done:
            return
        
        # Import workers here to avoid circular imports
        from src.scheduler.monitor_worker import run_monitor_worker
        from src.scheduler.task_creator import create_and_run_daily_tasks
        from src.scheduler.social_worker import run_social_engagement
        
        # Morning monitor run (collect T+24h data from yesterday's posts)
        self.scheduler.add_job(
            self._wrap_async(run_monitor_worker),
            CronTrigger.from_crontab(DEFAULT_SCHEDULE["monitor_morning"]),
            id="monitor_morning",
            name="Monitor Worker (Morning)",
            replace_existing=True,
        )
        
        # Daily task creation and workflow execution
        self.scheduler.add_job(
            self._wrap_async(create_and_run_daily_tasks),
            CronTrigger.from_crontab(DEFAULT_SCHEDULE["daily_tasks"]),
            id="daily_tasks",
            name="Daily Task Creator",
            replace_existing=True,
        )
        
        # Social engagement (like/comment on similar content)
        self.scheduler.add_job(
            self._wrap_async(run_social_engagement),
            CronTrigger.from_crontab(DEFAULT_SCHEDULE["social_engagement"]),
            id="social_engagement",
            name="Social Engagement",
            replace_existing=True,
        )
        
        # Evening monitor run (collect T+2h data from today's posts)
        self.scheduler.add_job(
            self._wrap_async(run_monitor_worker),
            CronTrigger.from_crontab(DEFAULT_SCHEDULE["monitor_evening"]),
            id="monitor_evening",
            name="Monitor Worker (Evening)",
            replace_existing=True,
        )
        
        self._setup_done = True
        logger.info("[Scheduler] All jobs configured.")
    
    def _wrap_async(self, coro_func):
        """Wrap an async function for APScheduler."""
        async def wrapper():
            try:
                logger.info("[Scheduler] Starting job: %s", coro_func.__name__)
                result = await coro_func()
                logger.info("[Scheduler] Job complete: %s — result=%s", coro_func.__name__, result)
                return result
            except Exception as e:
                logger.error("[Scheduler] Job failed: %s — error=%s", coro_func.__name__, e)
                raise
        return wrapper
    
    def start(self) -> None:
        """Start the scheduler."""
        self.setup()
        self.scheduler.start()
        logger.info("[Scheduler] Scheduler started. Press Ctrl+C to stop.")
        self._print_schedule()
    
    def stop(self) -> None:
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("[Scheduler] Scheduler stopped.")
    
    def _print_schedule(self) -> None:
        """Print the current schedule."""
        print("\n" + "=" * 60)
        print("📅 Daily Schedule")
        print("=" * 60)
        
        jobs = self.scheduler.get_jobs()
        for job in jobs:
            next_run = job.next_run_time
            if next_run:
                next_str = next_run.strftime("%Y-%m-%d %H:%M:%S")
            else:
                next_str = "Not scheduled"
            print(f"  {job.name:<30} Next: {next_str}")
        
        print("=" * 60 + "\n")
    
    async def run_job_now(self, job_name: str) -> None:
        """Manually trigger a specific job."""
        from src.scheduler.monitor_worker import run_monitor_worker
        from src.scheduler.task_creator import create_and_run_daily_tasks
        from src.scheduler.social_worker import run_social_engagement
        
        jobs = {
            "monitor": run_monitor_worker,
            "tasks": create_and_run_daily_tasks,
            "social": run_social_engagement,
        }
        
        if job_name not in jobs:
            print(f"Unknown job: {job_name}")
            print(f"Available jobs: {', '.join(jobs.keys())}")
            return
        
        logger.info("[Scheduler] Manually running job: %s", job_name)
        result = await jobs[job_name]()
        print(f"\nJob '{job_name}' completed. Result: {result}")


def _bootstrap() -> None:
    """Common bootstrap: load .env, init logging, registry, models."""
    from src.infra.logger import setup_logging
    from src.infra.model_adapter import init_models
    from src.infra.identity_registry import registry
    
    load_dotenv()
    setup_logging()
    init_models()
    registry.load_all()


async def run_scheduler() -> None:
    """Run the scheduler in the foreground."""
    _bootstrap()
    
    scheduler = DailyScheduler()
    scheduler.start()
    
    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    
    def shutdown_handler():
        logger.info("[Scheduler] Shutdown signal received.")
        scheduler.stop()
        loop.stop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour, scheduler handles timing
    except asyncio.CancelledError:
        pass


async def run_job_immediately(job_name: str) -> None:
    """Run a specific job immediately."""
    _bootstrap()
    
    scheduler = DailyScheduler()
    await scheduler.run_job_now(job_name)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Daily Scheduler for Social Media Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run scheduler daemon
  python -m src.scheduler.daily_scheduler
  
  # Run a specific job immediately
  python -m src.scheduler.daily_scheduler --run-now monitor
  python -m src.scheduler.daily_scheduler --run-now tasks
  python -m src.scheduler.daily_scheduler --run-now social
        """,
    )
    parser.add_argument(
        "--run-now",
        choices=["monitor", "tasks", "social"],
        help="Run a specific job immediately instead of starting the scheduler",
    )
    
    args = parser.parse_args()
    
    if args.run_now:
        asyncio.run(run_job_immediately(args.run_now))
    else:
        asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
