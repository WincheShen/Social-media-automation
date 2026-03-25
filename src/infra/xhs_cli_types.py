"""Data types for xiaohongshu-skills CLI adapter.

Typed dataclasses for parsing JSON output from CLI commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class XhsCliError(Exception):
    """Generic CLI error (exit code 2)."""


class XhsNotLoggedInError(XhsCliError):
    """User not logged in (exit code 1)."""


class XhsTimeoutError(XhsCliError):
    """CLI command timed out."""


class XhsChromeNotRunning(XhsCliError):
    """Chrome instance is not running or unreachable."""


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclass
class LoginStatus:
    """Result of check-login / login commands."""

    logged_in: bool
    nickname: str | None = None
    xhs_id: str | None = None


@dataclass
class FeedItem:
    """Single note entry from list-feeds or search-feeds."""

    feed_id: str
    xsec_token: str = ""
    title: str = ""
    author: str = ""
    likes: int = 0
    url: str | None = None


@dataclass
class FeedDetail:
    """Detailed note info from get-feed-detail."""

    feed_id: str
    title: str = ""
    content: str = ""
    author: str = ""
    likes: int = 0
    collects: int = 0
    comments: int = 0
    comment_list: list[dict] = field(default_factory=list)
    images: list[str] = field(default_factory=list)


@dataclass
class UserProfile:
    """User profile from user-profile command."""

    user_id: str
    nickname: str = ""
    xhs_id: str = ""
    description: str = ""
    followers: int = 0
    following: int = 0
    likes_received: int = 0


@dataclass
class PublishResult:
    """Result of click-publish command."""

    success: bool
    post_url: str | None = None
    error: str | None = None
