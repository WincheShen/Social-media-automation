"""Social Media Automation Agent — Entry Point

Usage:
    # Run a single task
    python -m src.main run --account XHS_01 --task "分析 2026 上海体育中考新规"

    # List all registered accounts
    python -m src.main accounts
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

from src.graph.state import AgentState
from src.graph.workflow import build_graph
from src.infra.identity_registry import registry
from src.infra.logger import setup_logging
from src.infra.model_adapter import init_models, usage_tracker

logger = logging.getLogger(__name__)


def _bootstrap() -> None:
    """Common bootstrap: load .env, init logging, registry, models."""
    load_dotenv()
    setup_logging()
    init_models()
    registry.load_all()


async def run(account_id: str, task: str) -> dict:
    """Execute the full workflow for a single account + task."""
    _bootstrap()

    # Validate account exists
    try:
        _ = registry.get(account_id)
    except KeyError:
        logger.error("Account '%s' not found. Available: %s", account_id, registry.list_accounts())
        sys.exit(1)

    logger.info("Starting workflow — account=%s, task=%s", account_id, task)

    graph = build_graph()

    initial_state: AgentState = {
        "account_id": account_id,
        "task": task,
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

    # Print cost summary
    total_in, total_out = usage_tracker.total_tokens
    logger.info(
        "Workflow completed — tokens_in=%d, tokens_out=%d, cost=$%.4f",
        total_in, total_out, usage_tracker.total_cost,
    )
    logger.info("Result: %s", result.get("feedback_summary"))

    return result


def list_accounts() -> None:
    """Print all registered accounts and their personas."""
    _bootstrap()
    accounts = registry.list_accounts()
    if not accounts:
        print("No accounts registered. Add YAML files to config/identities/")
        return

    print(f"\n{'ID':<12} {'Platform':<15} {'Persona':<20} {'Track':<20} {'Review Mode'}")
    print("─" * 80)
    for aid in accounts:
        cfg = registry.get(aid)
        persona = cfg.get("persona", {})
        schedule = cfg.get("schedule", {})
        print(
            f"{aid:<12} "
            f"{cfg.get('platform', '-'):<15} "
            f"{persona.get('name', '-'):<20} "
            f"{cfg.get('track', '-'):<20} "
            f"{schedule.get('review_mode', '-')}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Social Media Automation Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- run command ---
    run_parser = subparsers.add_parser("run", help="Run a content task for an account")
    run_parser.add_argument("--account", required=True, help="Account ID (e.g. XHS_01)")
    run_parser.add_argument("--task", required=True, help="Task description in natural language")

    # --- accounts command ---
    subparsers.add_parser("accounts", help="List all registered accounts")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(run(args.account, args.task))
    elif args.command == "accounts":
        list_accounts()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
