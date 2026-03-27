"""XhsCliAdapter — async subprocess wrapper for xiaohongshu-skills CLI.

All browser operations are delegated to the CLI engine; the LangGraph
agent never touches the browser directly.

Architecture:
    Agent (think) → XhsCliAdapter (subprocess) → cli.py → CDP → Chrome → 小红书

Usage:
    adapter = XhsCliAdapter(skills_dir="vendor/xiaohongshu-skills", account="xhs_01")
    await adapter.launch_chrome()
    status = await adapter.check_login()
    feeds = await adapter.search_feeds(keyword="露营")
    await adapter.fill_publish(title="...", content="...", images=[...])
    # ← user previews in browser
    result = await adapter.click_publish()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.infra.xhs_cli_types import (
    FeedDetail,
    FeedItem,
    LoginStatus,
    PublishResult,
    UserProfile,
    XhsChromeNotRunning,
    XhsCliError,
    XhsNotLoggedInError,
    XhsTimeoutError,
)

logger = logging.getLogger(__name__)

# Default skills directory (git submodule location)
_DEFAULT_SKILLS_DIR = Path("vendor/xiaohongshu-skills")


class XhsCliAdapter:
    """Async wrapper around xiaohongshu-skills CLI commands.

    Every public method maps to one or more CLI sub-commands, executed via
    ``asyncio.create_subprocess_exec``.  Stdout is parsed as JSON; exit
    codes are translated into typed exceptions.
    """

    def __init__(
        self,
        skills_dir: str | Path | None = None,
        account: str | None = None,
        host: str = "127.0.0.1",
        port: int = 9222,
        python_bin: str | None = None,
        timeout: int = 60,
    ):
        self._skills_dir = Path(
            skills_dir or os.getenv("XHS_SKILLS_DIR", str(_DEFAULT_SKILLS_DIR))
        ).resolve()
        self._account = account
        self._host = host
        self._port = port
        self._python = python_bin or sys.executable
        self._timeout = timeout

        # Validate paths exist (soft check — may not be installed yet)
        self._cli_script = self._skills_dir / "scripts" / "cli.py"
        self._chrome_launcher = self._skills_dir / "scripts" / "chrome_launcher.py"

    # ------------------------------------------------------------------
    # Low-level subprocess runner
    # ------------------------------------------------------------------

    async def _run_cli(
        self,
        *args: str,
        timeout: int | None = None,
        parse_json: bool = True,
    ) -> dict | str:
        """Execute a CLI command and return parsed output.

        Exit codes:
            0 — success (stdout is JSON)
            1 — not logged in → XhsNotLoggedInError
            2 — error → XhsCliError

        Returns parsed JSON dict on success, or raw stdout if parse_json=False.
        """
        if not self._cli_script.exists():
            raise XhsCliError(
                f"CLI script not found: {self._cli_script}. "
                f"Did you install xiaohongshu-skills to {self._skills_dir}?"
            )

        cmd = [
            self._python,
            str(self._cli_script),
            "--host", self._host,
            "--port", str(self._port),
        ]
        if self._account:
            cmd.extend(["--account", self._account])
        cmd.extend(args)

        effective_timeout = timeout or self._timeout

        logger.debug("[XhsCli] Running: %s (timeout=%ds)", " ".join(cmd), effective_timeout)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._skills_dir),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()  # type: ignore[union-attr]
            raise XhsTimeoutError(
                f"CLI command timed out after {effective_timeout}s: {' '.join(args)}"
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        logger.debug("[XhsCli] exit=%s stdout=%s", proc.returncode, stdout[:200])

        if proc.returncode == 1:
            raise XhsNotLoggedInError(
                f"Not logged in. Run login first. stderr={stderr}"
            )
        if proc.returncode != 0:
            raise XhsCliError(
                f"CLI error (exit {proc.returncode}): {stderr or stdout}"
            )

        if not parse_json:
            return stdout

        # Parse JSON output
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("[XhsCli] Non-JSON output: %s", stdout[:300])
            return {"raw": stdout}

    async def _run_launcher(self, *args: str, timeout: int = 10) -> str:
        """Execute chrome_launcher.py and return stdout."""
        if not self._chrome_launcher.exists():
            raise XhsCliError(f"Chrome launcher not found: {self._chrome_launcher}")

        cmd = [self._python, str(self._chrome_launcher), *args]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._skills_dir),
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            raise XhsCliError(f"Chrome launcher failed: {stderr or stdout}")
        return stdout

    # ------------------------------------------------------------------
    # Chrome lifecycle
    # ------------------------------------------------------------------

    async def launch_chrome(self, headless: bool = False) -> None:
        """Start a Chrome instance with CDP debugging enabled."""
        args = []
        if headless:
            args.append("--headless")
        # chrome_launcher.py is typically long-running; start and detach
        logger.info("[XhsCli] Launching Chrome (headless=%s, port=%d)", headless, self._port)
        cmd = [self._python, str(self._chrome_launcher)]
        if headless:
            cmd.append("--headless")
        # Start as detached process
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(self._skills_dir),
        )
        # Give Chrome time to start
        await asyncio.sleep(3)
        logger.info("[XhsCli] Chrome launched (pid=%s)", proc.pid)

    async def is_chrome_running(self) -> bool:
        """Check if Chrome CDP endpoint is reachable."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"http://{self._host}:{self._port}/json/version")
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def check_login(self) -> LoginStatus:
        """Check current login status. Returns LoginStatus."""
        try:
            data = await self._run_cli("check-login")
        except XhsNotLoggedInError:
            return LoginStatus(logged_in=False)

        if isinstance(data, dict):
            return LoginStatus(
                logged_in=True,
                nickname=data.get("nickname") or data.get("name"),
                xhs_id=data.get("xhs_id") or data.get("red_id"),
            )
        return LoginStatus(logged_in=True)

    async def login(self, timeout: int = 120) -> LoginStatus:
        """Start QR-code login flow. Waits for user to scan.

        Args:
            timeout: Max seconds to wait for login (default 120).
        """
        logger.info("[XhsCli] Starting QR login — please scan in the browser window.")
        data = await self._run_cli("login", timeout=timeout)
        if isinstance(data, dict):
            return LoginStatus(
                logged_in=True,
                nickname=data.get("nickname") or data.get("name"),
                xhs_id=data.get("xhs_id") or data.get("red_id"),
            )
        return LoginStatus(logged_in=True)

    async def delete_cookies(self) -> None:
        """Clear saved cookies for this account."""
        await self._run_cli("delete-cookies", parse_json=False)
        logger.info("[XhsCli] Cookies deleted.")

    # ------------------------------------------------------------------
    # Browsing / Research
    # ------------------------------------------------------------------

    async def list_feeds(self) -> list[FeedItem]:
        """Fetch homepage recommendation feed."""
        data = await self._run_cli("list-feeds")
        return self._parse_feed_list(data)

    async def search_feeds(
        self,
        keyword: str,
        sort_by: str | None = None,
        note_type: str | None = None,
    ) -> list[FeedItem]:
        """Search notes by keyword with optional filters.

        Args:
            keyword: Search term.
            sort_by: "最多点赞" / "最新" etc.
            note_type: "图文" / "视频" etc.
        """
        args = ["search-feeds", "--keyword", keyword]
        if sort_by:
            args.extend(["--sort-by", sort_by])
        if note_type:
            args.extend(["--note-type", note_type])

        data = await self._run_cli(*args)
        return self._parse_feed_list(data)

    async def get_feed_detail(
        self,
        feed_id: str,
        xsec_token: str,
    ) -> FeedDetail:
        """Get detailed info for a specific note (including comments)."""
        data = await self._run_cli(
            "get-feed-detail",
            "--feed-id", feed_id,
            "--xsec-token", xsec_token,
        )
        if not isinstance(data, dict):
            return FeedDetail(feed_id=feed_id)

        return FeedDetail(
            feed_id=feed_id,
            title=data.get("title", ""),
            content=data.get("content") or data.get("desc", ""),
            author=data.get("author") or data.get("nickname", ""),
            likes=_safe_int(data.get("likes") or data.get("liked_count", 0)),
            collects=_safe_int(data.get("collects") or data.get("collected_count", 0)),
            comments=_safe_int(data.get("comments") or data.get("comment_count", 0)),
            comment_list=data.get("comment_list", []),
            images=data.get("images") or data.get("image_list", []),
        )

    async def user_profile(self, user_id: str) -> UserProfile:
        """Fetch a user's public profile."""
        data = await self._run_cli("user-profile", "--user-id", user_id)
        if not isinstance(data, dict):
            return UserProfile(user_id=user_id)

        return UserProfile(
            user_id=user_id,
            nickname=data.get("nickname", ""),
            xhs_id=data.get("xhs_id") or data.get("red_id", ""),
            description=data.get("description") or data.get("desc", ""),
            followers=_safe_int(data.get("followers") or data.get("fans", 0)),
            following=_safe_int(data.get("following", 0)),
            likes_received=_safe_int(data.get("likes_received") or data.get("liked", 0)),
        )

    # ------------------------------------------------------------------
    # Publishing (three-step: fill → preview → confirm)
    # ------------------------------------------------------------------

    async def fill_publish(
        self,
        title: str,
        content: str,
        images: list[str] | None = None,
    ) -> None:
        """Fill the publish form WITHOUT submitting.

        After this call the user can preview the note in the browser.
        Call ``click_publish()`` to actually publish, or ``save_draft()``
        to save as draft.
        """
        # Write title and content to temp files to avoid shell escaping issues
        title_file = self._write_temp("title", title)
        content_file = self._write_temp("content", content)

        args = [
            "fill-publish",
            "--title-file", title_file,
            "--content-file", content_file,
        ]
        if images:
            abs_images = [str(Path(img).resolve()) for img in images if Path(img).exists()]
            if abs_images:
                args.append("--images")
                args.extend(abs_images)

        await self._run_cli(*args, timeout=180, parse_json=False)
        logger.info("[XhsCli] Publish form filled — awaiting preview confirmation.")

    async def click_publish(self) -> PublishResult:
        """Confirm and submit the publish. Call after fill_publish + preview."""
        try:
            data = await self._run_cli("click-publish", timeout=30)
        except XhsCliError as e:
            return PublishResult(success=False, error=str(e))

        if isinstance(data, dict):
            return PublishResult(
                success=True,
                post_url=data.get("url") or data.get("post_url"),
            )
        return PublishResult(success=True)

    async def save_draft(self) -> None:
        """Save current form as draft instead of publishing."""
        await self._run_cli("save-draft", parse_json=False)
        logger.info("[XhsCli] Draft saved.")

    async def publish_video(
        self,
        title: str,
        content: str,
        video: str,
    ) -> PublishResult:
        """Publish a video note."""
        title_file = self._write_temp("title", title)
        content_file = self._write_temp("content", content)

        try:
            data = await self._run_cli(
                "publish-video",
                "--title-file", title_file,
                "--content-file", content_file,
                "--video", str(Path(video).resolve()),
                timeout=120,
            )
        except XhsCliError as e:
            return PublishResult(success=False, error=str(e))

        if isinstance(data, dict):
            return PublishResult(success=True, post_url=data.get("url"))
        return PublishResult(success=True)

    # ------------------------------------------------------------------
    # Social interactions
    # ------------------------------------------------------------------

    async def like_feed(self, feed_id: str, xsec_token: str) -> None:
        """Like a note."""
        await self._run_cli(
            "like-feed",
            "--feed-id", feed_id,
            "--xsec-token", xsec_token,
            parse_json=False,
        )
        logger.info("[XhsCli] Liked feed %s", feed_id)

    async def favorite_feed(self, feed_id: str, xsec_token: str) -> None:
        """Favorite (collect) a note."""
        await self._run_cli(
            "favorite-feed",
            "--feed-id", feed_id,
            "--xsec-token", xsec_token,
            parse_json=False,
        )
        logger.info("[XhsCli] Favorited feed %s", feed_id)

    async def post_comment(
        self,
        feed_id: str,
        xsec_token: str,
        content: str,
    ) -> None:
        """Post a comment on a note."""
        await self._run_cli(
            "post-comment",
            "--feed-id", feed_id,
            "--xsec-token", xsec_token,
            "--content", content,
        )
        logger.info("[XhsCli] Commented on feed %s", feed_id)

    async def reply_comment(
        self,
        feed_id: str,
        xsec_token: str,
        comment_id: str,
        content: str,
    ) -> None:
        """Reply to a comment on a note."""
        await self._run_cli(
            "reply-comment",
            "--feed-id", feed_id,
            "--xsec-token", xsec_token,
            "--comment-id", comment_id,
            "--content", content,
        )
        logger.info("[XhsCli] Replied to comment %s on feed %s", comment_id, feed_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_temp(prefix: str, text: str) -> str:
        """Write text to a temporary file, return its absolute path."""
        fd, path = tempfile.mkstemp(prefix=f"xhs_{prefix}_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    @staticmethod
    def _parse_feed_list(data: Any) -> list[FeedItem]:
        """Parse CLI output into a list of FeedItem."""
        items: list[dict] = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("feeds") or data.get("items") or data.get("notes", [])

        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            result.append(FeedItem(
                feed_id=item.get("id") or item.get("feed_id") or item.get("note_id", ""),
                xsec_token=item.get("xsec_token", ""),
                title=item.get("title") or item.get("display_title", ""),
                author=item.get("author") or item.get("nickname", ""),
                likes=_safe_int(item.get("likes") or item.get("liked_count", 0)),
                url=item.get("url"),
            ))
        return result


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def get_adapter_for_account(persona: dict) -> XhsCliAdapter:
    """Create an XhsCliAdapter from persona config.

    Reads the ``xhs_cli`` block from the persona YAML:
        xhs_cli:
          port: 9222
          account: "xhs_01"
    """
    cli_cfg = persona.get("xhs_cli", {})
    return XhsCliAdapter(
        account=cli_cfg.get("account"),
        port=cli_cfg.get("port", 9222),
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_int(value: Any) -> int:
    """Safely convert a value to int."""
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0
