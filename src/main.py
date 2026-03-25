"""Social Media Automation Agent — Entry Point

Usage:
    python -m src.main --account XHS_01 --task "分析 2026 上海体育中考新规"
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from src.graph.state import AgentState
from src.graph.workflow import build_graph
from src.infra.identity_registry import registry
from src.infra.logger import setup_logging
from src.infra.model_adapter import init_models

logger = logging.getLogger(__name__)


async def run(account_id: str, task: str) -> None:
    """Execute the full workflow for a single account + task."""
    setup_logging()
    init_models()
    registry.load_all()

    # Validate account exists
    _ = registry.get(account_id)

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

    logger.info("Workflow completed — result: %s", result.get("feedback_summary"))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Social Media Automation Agent")
    parser.add_argument(
        "--account", required=True, help="Account ID (e.g. XHS_01)"
    )
    parser.add_argument(
        "--task", required=True, help="Task description"
    )
    args = parser.parse_args()

    asyncio.run(run(args.account, args.task))


if __name__ == "__main__":
    main()
