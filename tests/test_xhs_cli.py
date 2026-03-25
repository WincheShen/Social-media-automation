"""Tests for XhsCliAdapter — subprocess wrapper for xiaohongshu-skills CLI.

Tests use mocked subprocess calls to verify:
- Command construction and argument passing
- JSON output parsing into typed dataclasses
- Exit code → exception mapping
- Factory function from persona config
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.xhs_cli import XhsCliAdapter, get_adapter_for_account, _safe_int
from src.infra.xhs_cli_types import (
    FeedDetail,
    FeedItem,
    LoginStatus,
    PublishResult,
    XhsCliError,
    XhsNotLoggedInError,
    XhsTimeoutError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_process(returncode: int = 0, stdout: str = "{}", stderr: str = ""):
    """Create a mock asyncio subprocess."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(
        return_value=(stdout.encode(), stderr.encode())
    )
    proc.kill = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------

class TestSafeInt:
    def test_int_passthrough(self):
        assert _safe_int(42) == 42

    def test_string_to_int(self):
        assert _safe_int("123") == 123

    def test_invalid_returns_zero(self):
        assert _safe_int("abc") == 0
        assert _safe_int(None) == 0


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

class TestGetAdapterForAccount:
    def test_creates_adapter_from_persona(self):
        persona = {
            "xhs_cli": {"account": "xhs_01", "port": 9222},
        }
        adapter = get_adapter_for_account(persona)
        assert adapter._account == "xhs_01"
        assert adapter._port == 9222

    def test_default_port(self):
        persona = {"xhs_cli": {"account": "xhs_02"}}
        adapter = get_adapter_for_account(persona)
        assert adapter._port == 9222

    def test_no_xhs_cli_block(self):
        persona = {}
        adapter = get_adapter_for_account(persona)
        assert adapter._account is None
        assert adapter._port == 9222


# ---------------------------------------------------------------------------
# _run_cli — command construction and error handling
# ---------------------------------------------------------------------------

class TestRunCli:
    @pytest.fixture
    def adapter(self, tmp_path):
        # Create fake CLI script so path validation passes
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "cli.py").touch()
        (scripts_dir / "chrome_launcher.py").touch()
        return XhsCliAdapter(
            skills_dir=tmp_path,
            account="test_account",
            host="127.0.0.1",
            port=9999,
            python_bin="python3",
        )

    @pytest.mark.asyncio
    async def test_success_json_output(self, adapter):
        data = {"nickname": "测试用户", "xhs_id": "12345"}
        proc = _make_process(stdout=json.dumps(data))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await adapter._run_cli("check-login")

        assert result == data

    @pytest.mark.asyncio
    async def test_exit_code_1_raises_not_logged_in(self, adapter):
        proc = _make_process(returncode=1, stderr="not logged in")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(XhsNotLoggedInError):
                await adapter._run_cli("check-login")

    @pytest.mark.asyncio
    async def test_exit_code_2_raises_cli_error(self, adapter):
        proc = _make_process(returncode=2, stderr="element not found")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(XhsCliError, match="element not found"):
                await adapter._run_cli("fill-publish")

    @pytest.mark.asyncio
    async def test_timeout_raises(self, adapter):
        async def hang(*a, **kw):
            return _make_process()

        with patch("asyncio.create_subprocess_exec", side_effect=hang) as mock_exec:
            # Patch wait_for to simulate timeout
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                with pytest.raises(XhsTimeoutError):
                    await adapter._run_cli("login", timeout=1)

    @pytest.mark.asyncio
    async def test_non_json_output_returns_raw(self, adapter):
        proc = _make_process(stdout="OK - published")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await adapter._run_cli("click-publish")

        assert result == {"raw": "OK - published"}

    @pytest.mark.asyncio
    async def test_cli_not_found_raises(self, tmp_path):
        adapter = XhsCliAdapter(skills_dir=tmp_path / "nonexistent")
        with pytest.raises(XhsCliError, match="CLI script not found"):
            await adapter._run_cli("check-login")


# ---------------------------------------------------------------------------
# check_login
# ---------------------------------------------------------------------------

class TestCheckLogin:
    @pytest.fixture
    def adapter(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "cli.py").touch()
        return XhsCliAdapter(skills_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_logged_in(self, adapter):
        data = {"nickname": "学霸学长", "red_id": "XHS123"}
        proc = _make_process(stdout=json.dumps(data))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            status = await adapter.check_login()

        assert status.logged_in is True
        assert status.nickname == "学霸学长"
        assert status.xhs_id == "XHS123"

    @pytest.mark.asyncio
    async def test_not_logged_in(self, adapter):
        proc = _make_process(returncode=1, stderr="not logged in")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            status = await adapter.check_login()

        assert status.logged_in is False
        assert status.nickname is None


# ---------------------------------------------------------------------------
# search_feeds
# ---------------------------------------------------------------------------

class TestSearchFeeds:
    @pytest.fixture
    def adapter(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "cli.py").touch()
        return XhsCliAdapter(skills_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_search_returns_feed_items(self, adapter):
        data = {
            "feeds": [
                {"id": "f1", "xsec_token": "t1", "title": "露营攻略", "nickname": "户外达人", "liked_count": 500},
                {"id": "f2", "xsec_token": "t2", "title": "露营装备", "nickname": "旅行家", "liked_count": 300},
            ]
        }
        proc = _make_process(stdout=json.dumps(data))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            feeds = await adapter.search_feeds(keyword="露营")

        assert len(feeds) == 2
        assert isinstance(feeds[0], FeedItem)
        assert feeds[0].feed_id == "f1"
        assert feeds[0].title == "露营攻略"
        assert feeds[1].likes == 300


# ---------------------------------------------------------------------------
# get_feed_detail
# ---------------------------------------------------------------------------

class TestGetFeedDetail:
    @pytest.fixture
    def adapter(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "cli.py").touch()
        return XhsCliAdapter(skills_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_returns_feed_detail(self, adapter):
        data = {
            "title": "2024中考分数线",
            "content": "详细解读...",
            "nickname": "学霸学长",
            "liked_count": 1200,
            "collected_count": 800,
            "comment_count": 56,
            "comment_list": [{"text": "太有用了"}],
            "image_list": ["img1.jpg", "img2.jpg"],
        }
        proc = _make_process(stdout=json.dumps(data))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            detail = await adapter.get_feed_detail("feed123", "token456")

        assert isinstance(detail, FeedDetail)
        assert detail.feed_id == "feed123"
        assert detail.title == "2024中考分数线"
        assert detail.likes == 1200
        assert detail.collects == 800
        assert detail.comments == 56
        assert len(detail.comment_list) == 1


# ---------------------------------------------------------------------------
# fill_publish + click_publish
# ---------------------------------------------------------------------------

class TestPublishFlow:
    @pytest.fixture
    def adapter(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "cli.py").touch()
        return XhsCliAdapter(skills_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_fill_publish_writes_temp_files(self, adapter):
        proc = _make_process(stdout="OK")

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await adapter.fill_publish(
                title="测试标题",
                content="测试正文内容",
                images=[],
            )

        # Verify CLI was called with fill-publish and temp file args
        call_args = mock_exec.call_args[0]
        assert "fill-publish" in call_args
        assert "--title-file" in call_args
        assert "--content-file" in call_args

    @pytest.mark.asyncio
    async def test_click_publish_success(self, adapter):
        data = {"url": "https://www.xiaohongshu.com/explore/abc123"}
        proc = _make_process(stdout=json.dumps(data))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await adapter.click_publish()

        assert isinstance(result, PublishResult)
        assert result.success is True
        assert result.post_url == "https://www.xiaohongshu.com/explore/abc123"

    @pytest.mark.asyncio
    async def test_click_publish_failure(self, adapter):
        proc = _make_process(returncode=2, stderr="publish button not found")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await adapter.click_publish()

        assert result.success is False
        assert "publish button not found" in result.error


# ---------------------------------------------------------------------------
# Social interactions
# ---------------------------------------------------------------------------

class TestSocialInteractions:
    @pytest.fixture
    def adapter(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "cli.py").touch()
        return XhsCliAdapter(skills_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_like_feed(self, adapter):
        proc = _make_process(stdout="OK")

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await adapter.like_feed("feed123", "token456")

        call_args = mock_exec.call_args[0]
        assert "like-feed" in call_args
        assert "--feed-id" in call_args

    @pytest.mark.asyncio
    async def test_post_comment(self, adapter):
        proc = _make_process(stdout="{}")

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await adapter.post_comment("feed123", "token456", "好文章！")

        call_args = mock_exec.call_args[0]
        assert "post-comment" in call_args
        assert "--content" in call_args
