"""Structured logging configuration.

Outputs JSON-formatted logs with account_id and node context.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path("data/logs")


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include extra fields if present
        for key in ("account_id", "node", "model", "tokens_in", "tokens_out",
                     "latency_ms", "cost_usd"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Initialize logging with JSON formatter for file + readable for console."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console handler — human-readable
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)-7s %(name)s — %(message)s")
    )
    root.addHandler(console)

    # File handler — JSON structured
    file_handler = logging.FileHandler(
        LOG_DIR / "system.jsonl", encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    root.addHandler(file_handler)
