"""Tests for Node 1: Persona & Context Loader."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.nodes.context_loader import _load_identity, _load_memory, persona_context_loader


class TestLoadIdentity:
    """Test identity config loading."""

    def test_load_identity_valid(self, tmp_path):
        """Test loading a valid identity config."""
        config_dir = tmp_path / "identities"
        config_dir.mkdir()
        config_file = config_dir / "TEST_01.yaml"
        config_file.write_text(
            "account_id: TEST_01\nplatform: xiaohongshu\npersona:\n  name: Test\n",
            encoding="utf-8",
        )

        with patch("src.nodes.context_loader.CONFIG_DIR", config_dir):
            result = _load_identity("TEST_01")

        assert result["account_id"] == "TEST_01"
        assert result["platform"] == "xiaohongshu"
        assert result["persona"]["name"] == "Test"

    def test_load_identity_not_found(self, tmp_path):
        """Test loading a non-existent identity raises FileNotFoundError."""
        config_dir = tmp_path / "identities"
        config_dir.mkdir()

        with patch("src.nodes.context_loader.CONFIG_DIR", config_dir):
            with pytest.raises(FileNotFoundError):
                _load_identity("NONEXISTENT")


class TestLoadMemory:
    """Test memory loading."""

    def test_load_memory_no_file(self, tmp_path):
        """Test loading memory when no memory file exists returns empty list."""
        with patch("src.nodes.context_loader.MEMORY_DIR", tmp_path):
            result = _load_memory("TEST_01")
        assert result == []

    def test_load_memory_with_entries(self, tmp_path):
        """Test loading memory with existing entries."""
        memory_dir = tmp_path / "TEST_01"
        memory_dir.mkdir()
        memory_file = memory_dir / "memory.json"
        memory_file.write_text(
            json.dumps({
                "account_id": "TEST_01",
                "entries": [
                    {"type": "success", "task": "task1", "insight": "good"},
                    {"type": "failed", "task": "task2", "insight": "bad"},
                ],
            }),
            encoding="utf-8",
        )

        with patch("src.nodes.context_loader.MEMORY_DIR", tmp_path):
            result = _load_memory("TEST_01")

        assert len(result) == 2
        assert result[0]["task"] == "task1"

    def test_load_memory_max_entries(self, tmp_path):
        """Test that memory is truncated to max_entries."""
        memory_dir = tmp_path / "TEST_01"
        memory_dir.mkdir()
        entries = [{"type": "success", "task": f"task_{i}"} for i in range(50)]
        memory_file = memory_dir / "memory.json"
        memory_file.write_text(
            json.dumps({"account_id": "TEST_01", "entries": entries}),
            encoding="utf-8",
        )

        with patch("src.nodes.context_loader.MEMORY_DIR", tmp_path):
            result = _load_memory("TEST_01", max_entries=5)

        assert len(result) == 5
        assert result[0]["task"] == "task_45"


class TestPersonaContextLoaderNode:
    """Test the full graph node function."""

    @pytest.mark.asyncio
    async def test_persona_context_loader(self, tmp_path):
        """Test the full context loader node."""
        config_dir = tmp_path / "identities"
        config_dir.mkdir()
        config_file = config_dir / "TEST_01.yaml"
        config_file.write_text(
            "account_id: TEST_01\n"
            "platform: xiaohongshu\n"
            "persona:\n  name: Test\n"
            "schedule:\n  review_mode: auto\n",
            encoding="utf-8",
        )
        memory_dir = tmp_path / "memory"

        with (
            patch("src.nodes.context_loader.CONFIG_DIR", config_dir),
            patch("src.nodes.context_loader.MEMORY_DIR", memory_dir),
        ):
            state = {"account_id": "TEST_01", "task": "test task"}
            result = await persona_context_loader(state)

        assert result["persona"]["account_id"] == "TEST_01"
        assert result["memory"] == []
        assert result["review_mode"] == "auto"
