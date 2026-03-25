"""Node 1: Persona & Context Loader

Loads identity config, historical memory, and recent focus areas
based on the given account_id.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from src.graph.state import AgentState

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("config/identities")
MEMORY_DIR = Path("data/memory")


def _load_identity(account_id: str) -> dict:
    """Load identity YAML config for the given account."""
    config_path = CONFIG_DIR / f"{account_id}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Identity config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_memory(account_id: str, max_entries: int = 20) -> list[dict]:
    """Load recent memory entries for the given account."""
    memory_path = MEMORY_DIR / account_id / "memory.json"
    if not memory_path.exists():
        logger.info("No memory file found for %s, starting fresh.", account_id)
        return []
    with open(memory_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries", [])
    return entries[-max_entries:]


async def persona_context_loader(state: AgentState) -> dict:
    """Graph node: load persona config and memory into state."""
    account_id = state["account_id"]
    logger.info("[Node 1] Loading context for account: %s", account_id)

    persona = _load_identity(account_id)
    memory = _load_memory(account_id)

    return {
        "persona": persona,
        "memory": memory,
        "review_mode": persona.get("schedule", {}).get("review_mode", "review"),
    }
