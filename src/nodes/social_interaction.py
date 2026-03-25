"""Social Interaction Engine

Provides social engagement capabilities via xiaohongshu-skills CLI:
- Like notes (养号 / reciprocal engagement)
- Favorite (collect) notes
- Comment on notes
- Reply to comments

Can be invoked standalone or as part of a feedback/nurture workflow.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from src.infra.xhs_cli import XhsCliAdapter, get_adapter_for_account
from src.infra.xhs_cli_types import FeedItem, XhsCliError

logger = logging.getLogger(__name__)

# Random delay range between interactions (anti-detection)
INTERACTION_DELAY_RANGE = (3.0, 8.0)


async def like_notes(
    adapter: XhsCliAdapter,
    feeds: list[FeedItem],
    max_count: int = 5,
) -> list[str]:
    """Like a batch of notes with random delays.

    Args:
        adapter: XhsCliAdapter instance.
        feeds: List of FeedItem to like.
        max_count: Maximum number of notes to like.

    Returns:
        List of feed_ids that were successfully liked.
    """
    import asyncio

    liked: list[str] = []
    for feed in feeds[:max_count]:
        try:
            await adapter.like_feed(feed.feed_id, feed.xsec_token)
            liked.append(feed.feed_id)
        except XhsCliError as e:
            logger.warning("[Social] Failed to like %s: %s", feed.feed_id, e)

        await asyncio.sleep(random.uniform(*INTERACTION_DELAY_RANGE))

    logger.info("[Social] Liked %d/%d notes.", len(liked), len(feeds[:max_count]))
    return liked


async def favorite_notes(
    adapter: XhsCliAdapter,
    feeds: list[FeedItem],
    max_count: int = 3,
) -> list[str]:
    """Favorite (collect) a batch of notes with random delays.

    Returns:
        List of feed_ids that were successfully favorited.
    """
    import asyncio

    collected: list[str] = []
    for feed in feeds[:max_count]:
        try:
            await adapter.favorite_feed(feed.feed_id, feed.xsec_token)
            collected.append(feed.feed_id)
        except XhsCliError as e:
            logger.warning("[Social] Failed to favorite %s: %s", feed.feed_id, e)

        await asyncio.sleep(random.uniform(*INTERACTION_DELAY_RANGE))

    logger.info("[Social] Favorited %d/%d notes.", len(collected), len(feeds[:max_count]))
    return collected


async def comment_on_notes(
    adapter: XhsCliAdapter,
    targets: list[dict],
) -> list[str]:
    """Post comments on multiple notes.

    Args:
        adapter: XhsCliAdapter instance.
        targets: List of dicts with keys: feed_id, xsec_token, comment.

    Returns:
        List of feed_ids that were successfully commented on.
    """
    import asyncio

    commented: list[str] = []
    for target in targets:
        feed_id = target.get("feed_id", "")
        xsec_token = target.get("xsec_token", "")
        comment = target.get("comment", "")

        if not feed_id or not comment:
            continue

        try:
            await adapter.post_comment(feed_id, xsec_token, comment)
            commented.append(feed_id)
        except XhsCliError as e:
            logger.warning("[Social] Failed to comment on %s: %s", feed_id, e)

        await asyncio.sleep(random.uniform(*INTERACTION_DELAY_RANGE))

    logger.info("[Social] Commented on %d/%d notes.", len(commented), len(targets))
    return commented


async def engage_with_trending(
    adapter: XhsCliAdapter,
    keyword: str,
    like_count: int = 5,
    favorite_count: int = 2,
) -> dict[str, Any]:
    """Search for trending notes and engage with them (养号 routine).

    This is a convenience function that combines search + like + favorite
    into a single engagement session.

    Args:
        adapter: XhsCliAdapter instance.
        keyword: Search term for finding relevant notes.
        like_count: Number of notes to like.
        favorite_count: Number of notes to favorite.

    Returns:
        Summary dict with counts and feed_ids.
    """
    try:
        feeds = await adapter.search_feeds(
            keyword=keyword, sort_by="最多点赞", note_type="图文",
        )
    except XhsCliError as e:
        logger.error("[Social] Trending search failed: %s", e)
        return {"liked": [], "favorited": [], "error": str(e)}

    if not feeds:
        logger.info("[Social] No feeds found for keyword: %s", keyword)
        return {"liked": [], "favorited": []}

    liked = await like_notes(adapter, feeds, max_count=like_count)
    favorited = await favorite_notes(adapter, feeds, max_count=favorite_count)

    return {
        "keyword": keyword,
        "feeds_found": len(feeds),
        "liked": liked,
        "favorited": favorited,
    }
