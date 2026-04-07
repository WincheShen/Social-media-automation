"""Social Worker — Automated social engagement for traffic growth.

Searches for similar content based on recent posts and engages
(like/comment) to drive traffic back to the account.

Anti-detection features:
- Random delays between actions (human-like timing)
- Daily limits on likes/comments
- Engagement history to avoid duplicate interactions
- Random skip probability for natural behavior
- Time-of-day awareness (avoid late night activity)
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.infra.identity_registry import registry
from src.infra.model_adapter import ModelRouter
from src.infra.xhs_cli import get_adapter_for_account
from src.infra.xhs_cli_types import FeedItem, XhsCliError
from src.nodes.social_interaction import like_notes, comment_on_notes

logger = logging.getLogger(__name__)

MEMORY_DIR = Path("data/memory")
ENGAGEMENT_DB_PATH = Path("data/state/engagement_history.db")

# Daily limits for safety (conservative to avoid detection)
MAX_DAILY_LIKES = 30
MAX_DAILY_COMMENTS = 10
MAX_DAILY_SEARCHES = 10

# Delay ranges (seconds) - varied to appear human
DELAY_BETWEEN_ACTIONS = (3.0, 8.0)      # Between like/comment on same feed
DELAY_BETWEEN_FEEDS = (5.0, 15.0)       # Between different feeds
DELAY_BETWEEN_SEARCHES = (15.0, 30.0)   # Between keyword searches
DELAY_BROWSE_SIMULATION = (1.0, 3.0)    # Simulate reading content

# Skip probabilities for natural behavior
SKIP_LIKE_PROB = 0.2      # 20% chance to skip liking
SKIP_COMMENT_PROB = 0.4   # 40% chance to skip commenting (comments are riskier)


# ---------------------------------------------------------------------------
# Engagement History Database
# ---------------------------------------------------------------------------

def _init_engagement_db() -> None:
    """Initialize the engagement history database."""
    ENGAGEMENT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ENGAGEMENT_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engagement_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            feed_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            comment_text TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(account_id, feed_id, action_type)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_engagement_account_date 
        ON engagement_history(account_id, created_at)
    """)
    conn.commit()
    conn.close()


def get_today_engagement_count(account_id: str, action_type: str) -> int:
    """Get the number of engagements of a specific type today."""
    _init_engagement_db()
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(ENGAGEMENT_DB_PATH))
    cursor = conn.execute(
        """SELECT COUNT(*) FROM engagement_history
           WHERE account_id = ? AND action_type = ? AND created_at LIKE ?""",
        (account_id, action_type, f"{today}%"),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def has_engaged_with_feed(account_id: str, feed_id: str, action_type: str) -> bool:
    """Check if we've already engaged with this feed."""
    _init_engagement_db()
    
    conn = sqlite3.connect(str(ENGAGEMENT_DB_PATH))
    cursor = conn.execute(
        """SELECT 1 FROM engagement_history
           WHERE account_id = ? AND feed_id = ? AND action_type = ?""",
        (account_id, feed_id, action_type),
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def record_engagement(account_id: str, feed_id: str, action_type: str, comment_text: str | None = None) -> None:
    """Record an engagement action."""
    _init_engagement_db()
    
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(ENGAGEMENT_DB_PATH))
    try:
        conn.execute(
            """INSERT OR IGNORE INTO engagement_history
               (account_id, feed_id, action_type, comment_text, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (account_id, feed_id, action_type, comment_text, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_daily_stats(account_id: str) -> dict:
    """Get today's engagement statistics for an account."""
    return {
        "likes": get_today_engagement_count(account_id, "like"),
        "comments": get_today_engagement_count(account_id, "comment"),
        "searches": get_today_engagement_count(account_id, "search"),
    }


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def get_recent_posts(account_id: str, days: int = 1) -> list[dict]:
    """Get recent successful posts from memory."""
    memory_path = MEMORY_DIR / account_id / "memory.json"
    
    if not memory_path.exists():
        return []
    
    with open(memory_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = []
    
    for entry in reversed(data.get("entries", [])):
        if entry.get("type") != "success":
            continue
        
        try:
            ts = datetime.fromisoformat(entry.get("timestamp", ""))
            if ts < cutoff:
                break
            recent.append(entry)
        except (ValueError, TypeError):
            continue
    
    return recent


def extract_keywords(title: str, tags: list[str]) -> list[str]:
    """Extract search keywords from post title and tags."""
    keywords = []
    
    # Use tags first (most specific)
    keywords.extend(tags[:2])
    
    # Extract key phrases from title
    # Simple heuristic: split by common delimiters and take meaningful parts
    if title:
        parts = title.replace("：", " ").replace("｜", " ").replace("|", " ").split()
        for part in parts:
            if len(part) >= 2 and part not in keywords:
                keywords.append(part)
                if len(keywords) >= 4:
                    break
    
    return keywords[:4]


async def human_like_delay(delay_range: tuple[float, float], action: str = "") -> None:
    """Add a human-like random delay with slight variation."""
    base_delay = random.uniform(*delay_range)
    # Add occasional longer pauses (simulating distraction)
    if random.random() < 0.1:  # 10% chance of longer pause
        base_delay *= random.uniform(1.5, 2.5)
    
    if action:
        logger.debug("[SocialWorker] Waiting %.1fs before %s", base_delay, action)
    
    await asyncio.sleep(base_delay)


async def generate_smart_comment(
    router: ModelRouter,
    feed: FeedItem,
    persona: dict,
) -> str:
    """Generate a personalized comment using LLM.
    
    Uses varied prompts and styles to avoid repetitive patterns.
    """
    persona_cfg = persona.get("persona", {})
    persona_name = persona_cfg.get("name", "用户")
    persona_tone = persona_cfg.get("tone", "友好")
    audience = persona_cfg.get("audience", "")
    
    # Vary the comment style randomly
    comment_styles = [
        "提问式：对内容中某个点表示好奇，提一个简短问题",
        "共鸣式：表达对内容的认同，分享类似感受",
        "补充式：基于内容补充一点自己的小经验",
        "感谢式：真诚感谢分享，说明对自己有帮助",
    ]
    chosen_style = random.choice(comment_styles)
    
    # Vary the length requirement
    length_options = [
        "10-20字，简短有力",
        "15-25字，适中长度",
        "20-35字，稍微详细",
    ]
    chosen_length = random.choice(length_options)
    
    prompt = f"""你是「{persona_name}」，正在浏览小红书。
你的语气风格：{persona_tone}
你的目标读者：{audience}

看到这篇笔记：
标题：《{feed.title}》
简介：{feed.desc[:150] if feed.desc else '(无简介)'}

请写一条评论，要求：
- 风格：{chosen_style}
- 长度：{chosen_length}
- 像真人一样自然，不要太正式
- 与内容相关，不要泛泛而谈
- 不要用"博主"，可以用"姐妹"、"亲"、"楼主"、"宝子"等
- emoji 用 0-2 个，不要过度

直接输出评论内容，不要任何解释或引号。"""

    try:
        comment = await router.invoke("copywriter", prompt, temperature=0.95)
        # Clean up the comment
        comment = comment.strip().strip('"').strip("'").strip()
        # Remove common LLM artifacts
        for prefix in ["评论：", "评论:", "Comment:", "我的评论："]:
            if comment.startswith(prefix):
                comment = comment[len(prefix):].strip()
        # Ensure reasonable length
        if len(comment) > 60:
            comment = comment[:60]
        return comment
    except Exception as e:
        logger.warning("[SocialWorker] Failed to generate comment: %s", e)
        return ""


async def engage_with_similar_content(
    account_id: str,
    keyword: str,
    max_likes: int = 5,
    max_comments: int = 2,
) -> dict:
    """Search for similar content and engage with it.
    
    Features:
    - Checks daily limits before engaging
    - Skips already-engaged content
    - Human-like delays between actions
    - Random skip probability for natural behavior
    
    Returns:
        Summary of engagement actions.
    """
    logger.info(
        "[SocialWorker] Engaging with content for keyword: %s (account=%s)",
        keyword, account_id,
    )
    
    # Check daily limits
    stats = get_daily_stats(account_id)
    if stats["likes"] >= MAX_DAILY_LIKES:
        logger.warning("[SocialWorker] Daily like limit reached for %s (%d/%d)",
                       account_id, stats["likes"], MAX_DAILY_LIKES)
        return {"skipped": "daily_like_limit", "stats": stats}
    
    if stats["comments"] >= MAX_DAILY_COMMENTS:
        logger.warning("[SocialWorker] Daily comment limit reached for %s (%d/%d)",
                       account_id, stats["comments"], MAX_DAILY_COMMENTS)
        max_comments = 0  # Still allow likes
    
    remaining_likes = MAX_DAILY_LIKES - stats["likes"]
    remaining_comments = MAX_DAILY_COMMENTS - stats["comments"]
    
    try:
        adapter = get_adapter_for_account(account_id)
        config = registry.get(account_id)
    except Exception as e:
        logger.error("[SocialWorker] Failed to initialize: %s", e)
        return {"error": str(e)}
    
    # Search for similar content
    try:
        feeds = await adapter.search_feeds(
            keyword=keyword,
            sort_by="最新",  # Recent content for better engagement
            note_type="图文",
        )
        record_engagement(account_id, keyword, "search")  # Track search
    except XhsCliError as e:
        logger.error("[SocialWorker] Search failed: %s", e)
        return {"error": str(e), "keyword": keyword}
    
    if not feeds:
        logger.info("[SocialWorker] No feeds found for keyword: %s", keyword)
        return {"keyword": keyword, "feeds_found": 0, "liked": [], "commented": []}
    
    logger.info("[SocialWorker] Found %d feeds for keyword: %s", len(feeds), keyword)
    
    # Filter out already-engaged feeds
    new_feeds = [
        f for f in feeds 
        if not has_engaged_with_feed(account_id, f.feed_id, "like")
    ]
    logger.info("[SocialWorker] %d new feeds (not previously engaged)", len(new_feeds))
    
    router = ModelRouter(config)
    liked = []
    commented = []
    
    # Process feeds with human-like behavior
    for i, feed in enumerate(new_feeds[:max(max_likes, max_comments)]):
        # Simulate browsing/reading the content first
        await human_like_delay(DELAY_BROWSE_SIMULATION, "reading content")
        
        # Like with some randomness
        if len(liked) < min(max_likes, remaining_likes):
            if random.random() > SKIP_LIKE_PROB:
                try:
                    await adapter.like_note(feed.feed_id, feed.xsec_token)
                    liked.append(feed.feed_id)
                    record_engagement(account_id, feed.feed_id, "like")
                    logger.info("[SocialWorker] Liked %s: %s", feed.feed_id, feed.title[:30])
                except XhsCliError as e:
                    logger.warning("[SocialWorker] Like failed: %s", e)
                
                await human_like_delay(DELAY_BETWEEN_ACTIONS, "next action")
        
        # Comment with more randomness (comments are riskier)
        if len(commented) < min(max_comments, remaining_comments):
            if random.random() > SKIP_COMMENT_PROB:
                comment_text = await generate_smart_comment(router, feed, config)
                
                if comment_text:
                    try:
                        await adapter.post_comment(feed.feed_id, feed.xsec_token, comment_text)
                        commented.append({
                            "feed_id": feed.feed_id,
                            "title": feed.title,
                            "comment": comment_text,
                        })
                        record_engagement(account_id, feed.feed_id, "comment", comment_text)
                        logger.info(
                            "[SocialWorker] Commented on %s: %s",
                            feed.feed_id, comment_text[:30],
                        )
                    except XhsCliError as e:
                        logger.warning("[SocialWorker] Comment failed: %s", e)
        
        # Delay between feeds
        if i < len(new_feeds) - 1:
            await human_like_delay(DELAY_BETWEEN_FEEDS, "next feed")
    
    return {
        "keyword": keyword,
        "feeds_found": len(feeds),
        "new_feeds": len(new_feeds),
        "liked": liked,
        "commented": commented,
        "daily_stats": get_daily_stats(account_id),
    }


async def run_social_engagement(account_id: str | None = None) -> dict:
    """Run social engagement for one or all accounts.
    
    Features:
    - Respects daily limits per account
    - Tracks engagement history to avoid duplicates
    - Human-like delays between actions
    - Time-of-day awareness
    
    Args:
        account_id: Specific account to run for, or None for all.
    
    Returns:
        Summary of all engagement actions.
    """
    logger.info("[SocialWorker] Starting social engagement run...")
    
    # Check time of day - avoid late night activity (looks suspicious)
    current_hour = datetime.now().hour
    if current_hour < 7 or current_hour > 23:
        logger.warning("[SocialWorker] Skipping — outside active hours (7:00-23:00)")
        return {"skipped": "outside_active_hours", "hour": current_hour}
    
    if account_id:
        accounts = [account_id]
    else:
        accounts = registry.list_accounts()
    
    results = {}
    
    for acc_id in accounts:
        try:
            config = registry.get(acc_id)
        except Exception as e:
            logger.warning("[SocialWorker] Failed to load config for %s: %s", acc_id, e)
            results[acc_id] = {"error": str(e)}
            continue
        
        # Check if social engagement is enabled
        schedule = config.get("schedule", {})
        if not schedule.get("auto_engage", True):  # Default to True
            logger.debug("[SocialWorker] Skipping %s — auto_engage disabled", acc_id)
            results[acc_id] = {"skipped": "auto_engage disabled"}
            continue
        
        # Check daily limits before starting
        stats = get_daily_stats(acc_id)
        if stats["likes"] >= MAX_DAILY_LIKES and stats["comments"] >= MAX_DAILY_COMMENTS:
            logger.info("[SocialWorker] Skipping %s — daily limits reached", acc_id)
            results[acc_id] = {"skipped": "daily_limits_reached", "stats": stats}
            continue
        
        # Get recent posts to find keywords
        recent_posts = get_recent_posts(acc_id, days=3)
        
        if not recent_posts:
            # Fall back to account keywords
            keywords = config.get("keywords", [])[:2]
        else:
            # Extract keywords from recent posts
            keywords = []
            for post in recent_posts[:2]:
                title = post.get("title", "")
                tags = post.get("tags", [])
                keywords.extend(extract_keywords(title, tags))
            keywords = list(set(keywords))[:3]  # Dedupe and limit
        
        if not keywords:
            logger.info("[SocialWorker] No keywords for %s, skipping", acc_id)
            results[acc_id] = {"skipped": "no keywords"}
            continue
        
        # Shuffle keywords for variety
        random.shuffle(keywords)
        
        logger.info("[SocialWorker] Processing %s with keywords: %s", acc_id, keywords)
        
        account_results = []
        for kw in keywords[:2]:  # Limit to 2 keywords per run
            result = await engage_with_similar_content(
                acc_id, kw,
                max_likes=5,
                max_comments=2,
            )
            account_results.append(result)
            
            # Human-like delay between keyword searches
            await human_like_delay(DELAY_BETWEEN_SEARCHES, "next keyword search")
        
        results[acc_id] = {
            "keywords": keywords[:2],
            "engagements": account_results,
            "final_stats": get_daily_stats(acc_id),
        }
    
    logger.info("[SocialWorker] Social engagement run complete.")
    return results


async def main():
    """CLI entry point for manual testing."""
    import argparse
    from src.infra.logger import setup_logging
    from src.infra.model_adapter import init_models
    from dotenv import load_dotenv
    
    parser = argparse.ArgumentParser(description="Social engagement worker")
    parser.add_argument("--account", help="Specific account ID to run for")
    args = parser.parse_args()
    
    load_dotenv()
    setup_logging()
    init_models()
    registry.load_all()
    
    result = await run_social_engagement(args.account)
    print(f"\nSocial Worker Result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
