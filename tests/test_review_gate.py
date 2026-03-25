"""Tests for Node 5: Review & Approval Gate."""

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch

from src.nodes.review_gate import (
    review_gate,
    _init_queue_db,
    _enqueue_content,
    FORCED_REVIEW_TRACKS,
)


class TestForcedReviewTracks:
    """Test that finance tracks are correctly identified."""

    def test_finance_in_forced_tracks(self):
        assert "finance" in FORCED_REVIEW_TRACKS
        assert "金融" in FORCED_REVIEW_TRACKS
        assert "股票" in FORCED_REVIEW_TRACKS

    def test_education_not_forced(self):
        assert "教育" not in FORCED_REVIEW_TRACKS
        assert "上海中考" not in FORCED_REVIEW_TRACKS


class TestAutoMode:
    """Test auto-approval mode."""

    @pytest.mark.asyncio
    async def test_auto_mode_approves(self):
        state = {
            "account_id": "XHS_01",
            "review_mode": "auto",
            "persona": {"track": "上海中考"},
            "draft_title": "标题",
            "draft_content": "正文",
            "draft_tags": [],
            "visual_assets": [],
        }
        result = await review_gate(state)
        assert result["approved"] is True

    @pytest.mark.asyncio
    async def test_finance_auto_forced_to_review(self):
        """Finance accounts cannot use auto mode — must be overridden to review."""
        state = {
            "account_id": "XHS_02",
            "review_mode": "auto",
            "persona": {"track": "finance"},
            "draft_title": "标题",
            "draft_content": "正文",
            "draft_tags": [],
            "visual_assets": [],
            "safety_issues": [],
        }
        # Since review mode gets overridden to "review", it will call input()
        # We mock input to simulate approval
        with patch("builtins.input", return_value="a"):
            result = await review_gate(state)
        assert result["approved"] is True


class TestScheduledMode:
    """Test scheduled publishing mode."""

    @pytest.mark.asyncio
    async def test_scheduled_mode_enqueues(self, tmp_path):
        db_path = tmp_path / "queue.db"
        state = {
            "account_id": "XHS_01",
            "review_mode": "scheduled",
            "persona": {
                "track": "上海中考",
                "schedule": {"post_windows": ["19:00-21:00"]},
            },
            "draft_title": "测试标题",
            "draft_content": "测试正文",
            "draft_tags": ["标签1"],
            "visual_assets": [],
        }

        with patch("src.nodes.review_gate.QUEUE_DB_PATH", db_path):
            result = await review_gate(state)

        assert result["approved"] is True

        # Verify content was written to the queue DB
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT * FROM publish_queue").fetchall()
        conn.close()
        assert len(rows) == 1


class TestReviewMode:
    """Test human-in-the-loop review mode."""

    @pytest.mark.asyncio
    async def test_approve_via_input(self):
        state = {
            "account_id": "XHS_01",
            "review_mode": "review",
            "persona": {"track": "上海中考"},
            "draft_title": "标题",
            "draft_content": "正文内容",
            "draft_tags": ["标签"],
            "visual_assets": [],
            "safety_issues": [],
        }

        with patch("builtins.input", return_value="a"):
            result = await review_gate(state)
        assert result["approved"] is True

    @pytest.mark.asyncio
    async def test_reject_via_input(self):
        state = {
            "account_id": "XHS_01",
            "review_mode": "review",
            "persona": {"track": "上海中考"},
            "draft_title": "标题",
            "draft_content": "正文内容",
            "draft_tags": ["标签"],
            "visual_assets": [],
            "safety_issues": [],
        }

        with patch("builtins.input", return_value="r"):
            result = await review_gate(state)
        assert result["approved"] is False


class TestEnqueueContent:
    """Test the SQLite queue write logic."""

    def test_enqueue_creates_db_and_inserts(self, tmp_path):
        db_path = tmp_path / "queue.db"
        state = {
            "account_id": "XHS_03",
            "persona": {"schedule": {"post_windows": ["06:00-08:00"]}},
            "draft_title": "养生小贴士",
            "draft_content": "今天分享一个养生方法",
            "draft_tags": ["养生", "健康"],
            "visual_assets": ["/tmp/img.png"],
        }

        with patch("src.nodes.review_gate.QUEUE_DB_PATH", db_path):
            queue_id = _enqueue_content(state)

        assert queue_id is not None
        assert queue_id > 0

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT account_id, title, status FROM publish_queue WHERE id = ?",
            (queue_id,),
        ).fetchone()
        conn.close()

        assert row[0] == "XHS_03"
        assert row[1] == "养生小贴士"
        assert row[2] == "pending"
