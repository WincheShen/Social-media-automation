"""Identity Registry

Loads and manages account identity configurations from YAML files.
Supports hot-reload and dynamic account enable/disable.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("config/identities")


class IdentityRegistry:
    """Central registry for all account identities."""

    def __init__(self, config_dir: Path = CONFIG_DIR):
        self._config_dir = config_dir
        self._identities: dict[str, dict] = {}

    def load_all(self) -> None:
        """Load all identity configs from the config directory."""
        self._identities.clear()
        if not self._config_dir.exists():
            logger.warning("Identity config dir not found: %s", self._config_dir)
            return

        for path in sorted(self._config_dir.glob("*.yaml")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                account_id = config.get("account_id")
                if account_id:
                    self._identities[account_id] = config
                    logger.info("Loaded identity: %s from %s", account_id, path.name)
            except Exception as e:
                logger.error("Failed to load identity from %s: %s", path, e)

        logger.info("Total identities loaded: %d", len(self._identities))

    def get(self, account_id: str) -> dict:
        """Get identity config by account_id."""
        if account_id not in self._identities:
            raise KeyError(f"Account not found: {account_id}")
        return self._identities[account_id]

    def list_accounts(self) -> list[str]:
        """List all registered account IDs."""
        return list(self._identities.keys())

    def reload(self) -> None:
        """Hot-reload all identity configs."""
        logger.info("Reloading identity registry...")
        self.load_all()


# Global singleton
registry = IdentityRegistry()
