"""Base Publisher Protocol

All platform-specific publishers must implement this interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class PublishContent:
    """Content payload to be published."""

    title: str
    body: str
    tags: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)  # file paths


@dataclass
class PublishResult:
    """Result of a publish operation."""

    success: bool
    post_url: Optional[str] = None
    post_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PostMetrics:
    """Engagement metrics for a published post."""

    impressions: int = 0
    likes: int = 0
    favorites: int = 0
    comments: int = 0
    shares: int = 0
    new_followers: int = 0

    @property
    def engagement_rate(self) -> float:
        if self.impressions == 0:
            return 0.0
        total = self.likes + self.favorites + self.comments + self.shares
        return total / self.impressions


class Publisher(Protocol):
    """Interface that all platform publishers must implement."""

    async def login_check(self) -> bool:
        """Check if the current session is authenticated."""
        ...

    async def publish(self, content: PublishContent) -> PublishResult:
        """Publish content to the platform."""
        ...

    async def fetch_metrics(self, post_id: str) -> PostMetrics:
        """Fetch engagement metrics for a published post."""
        ...
