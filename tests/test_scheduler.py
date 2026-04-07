"""Unit tests for the scheduler module."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scheduler.monitor_worker import (
    get_pending_tasks_due_now,
    append_metrics_to_memory,
    process_single_task,
    run_monitor_worker,
)
from src.scheduler.task_creator import (
    create_task,
    get_today_task_count,
    create_daily_tasks,
)
from src.scheduler.social_worker import (
    get_recent_posts,
    extract_keywords,
    generate_smart_comment,
    _init_engagement_db,
    get_today_engagement_count,
    has_engaged_with_feed,
    record_engagement,
    get_daily_stats,
    human_like_delay,
    ENGAGEMENT_DB_PATH,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary SQLite database for testing."""
    db_path = tmp_path / "test_tasks.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'created',
            created_at TEXT,
            updated_at TEXT,
            draft_title TEXT,
            draft_content TEXT,
            draft_tags TEXT,
            research_summary TEXT,
            research_data TEXT,
            safety_issues TEXT,
            image_gen_prompt TEXT,
            post_url TEXT,
            error TEXT
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def temp_monitor_db(tmp_path):
    """Create a temporary monitor tasks database."""
    db_path = tmp_path / "monitor_tasks.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE monitor_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            post_url TEXT,
            feed_id TEXT,
            xsec_token TEXT,
            checkpoint TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            metrics_json TEXT,
            created_at TEXT,
            completed_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def temp_memory_dir(tmp_path):
    """Create a temporary memory directory."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    return memory_dir


# ---------------------------------------------------------------------------
# Monitor Worker Tests
# ---------------------------------------------------------------------------

class TestMonitorWorker:
    """Tests for monitor_worker.py"""
    
    def test_get_pending_tasks_due_now_empty(self, temp_monitor_db):
        """Should return empty list when no tasks exist."""
        with patch("src.scheduler.monitor_worker.MONITOR_DB_PATH", temp_monitor_db):
            tasks = get_pending_tasks_due_now()
            assert tasks == []
    
    def test_get_pending_tasks_due_now_with_due_tasks(self, temp_monitor_db):
        """Should return tasks whose scheduled_at has passed."""
        # Insert a task that's due
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn = sqlite3.connect(str(temp_monitor_db))
        conn.execute(
            """INSERT INTO monitor_tasks 
               (account_id, feed_id, xsec_token, checkpoint, scheduled_at, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("XHS_01", "feed123", "token123", "T+2h", past_time, "pending"),
        )
        conn.commit()
        conn.close()
        
        with patch("src.scheduler.monitor_worker.MONITOR_DB_PATH", temp_monitor_db):
            tasks = get_pending_tasks_due_now()
            assert len(tasks) == 1
            assert tasks[0]["account_id"] == "XHS_01"
            assert tasks[0]["feed_id"] == "feed123"
    
    def test_get_pending_tasks_excludes_future_tasks(self, temp_monitor_db):
        """Should not return tasks scheduled for the future."""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        conn = sqlite3.connect(str(temp_monitor_db))
        conn.execute(
            """INSERT INTO monitor_tasks 
               (account_id, feed_id, xsec_token, checkpoint, scheduled_at, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("XHS_01", "feed123", "token123", "T+24h", future_time, "pending"),
        )
        conn.commit()
        conn.close()
        
        with patch("src.scheduler.monitor_worker.MONITOR_DB_PATH", temp_monitor_db):
            tasks = get_pending_tasks_due_now()
            assert len(tasks) == 0
    
    def test_get_pending_tasks_excludes_completed(self, temp_monitor_db):
        """Should not return completed tasks."""
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn = sqlite3.connect(str(temp_monitor_db))
        conn.execute(
            """INSERT INTO monitor_tasks 
               (account_id, feed_id, xsec_token, checkpoint, scheduled_at, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("XHS_01", "feed123", "token123", "T+2h", past_time, "completed"),
        )
        conn.commit()
        conn.close()
        
        with patch("src.scheduler.monitor_worker.MONITOR_DB_PATH", temp_monitor_db):
            tasks = get_pending_tasks_due_now()
            assert len(tasks) == 0
    
    def test_append_metrics_to_memory_creates_file(self, temp_memory_dir):
        """Should create memory file if it doesn't exist."""
        with patch("src.scheduler.monitor_worker.MEMORY_DIR", temp_memory_dir):
            metrics = {"likes": 10, "collects": 5, "comments": 2, "checkpoint": "T+2h"}
            post_info = {"post_url": "https://example.com/post1"}
            
            append_metrics_to_memory("XHS_01", metrics, post_info)
            
            memory_path = temp_memory_dir / "XHS_01" / "memory.json"
            assert memory_path.exists()
            
            with open(memory_path) as f:
                data = json.load(f)
            
            assert data["account_id"] == "XHS_01"
            assert len(data["entries"]) == 1
    
    def test_append_metrics_updates_existing_entry(self, temp_memory_dir):
        """Should update existing entry with metrics."""
        # Create existing memory file with a success entry
        account_dir = temp_memory_dir / "XHS_01"
        account_dir.mkdir()
        memory_path = account_dir / "memory.json"
        
        existing_data = {
            "account_id": "XHS_01",
            "entries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": "success",
                    "title": "Test Post",
                    "post_url": "https://example.com/post1",
                    "detail": {},
                }
            ],
        }
        with open(memory_path, "w") as f:
            json.dump(existing_data, f)
        
        with patch("src.scheduler.monitor_worker.MEMORY_DIR", temp_memory_dir):
            metrics = {"likes": 10, "collects": 5, "comments": 2, "checkpoint": "T+2h"}
            post_info = {"post_url": "https://example.com/post1"}
            
            append_metrics_to_memory("XHS_01", metrics, post_info)
            
            with open(memory_path) as f:
                data = json.load(f)
            
            # Should have updated the existing entry
            assert len(data["entries"]) == 1
            assert "metrics_T+2h" in data["entries"][0]
            assert data["entries"][0]["detail"]["likes"] == 10


# ---------------------------------------------------------------------------
# Task Creator Tests
# ---------------------------------------------------------------------------

class TestTaskCreator:
    """Tests for task_creator.py"""
    
    def test_create_task(self, temp_db):
        """Should create a task in the database."""
        with patch("src.scheduler.task_creator.TASKS_DB_PATH", temp_db):
            task = create_task("XHS_01", "Test task description")
            
            assert task["account_id"] == "XHS_01"
            assert task["description"] == "Test task description"
            assert task["status"] == "created"
            assert "id" in task
            
            # Verify in database
            conn = sqlite3.connect(str(temp_db))
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task["id"],))
            row = cursor.fetchone()
            conn.close()
            
            assert row is not None
    
    def test_get_today_task_count(self, temp_db):
        """Should count tasks created today."""
        with patch("src.scheduler.task_creator.TASKS_DB_PATH", temp_db):
            # Create some tasks
            create_task("XHS_01", "Task 1")
            create_task("XHS_01", "Task 2")
            create_task("XHS_02", "Task 3")
            
            count = get_today_task_count("XHS_01")
            assert count == 2
            
            count = get_today_task_count("XHS_02")
            assert count == 1
            
            count = get_today_task_count("XHS_99")
            assert count == 0
    
    @pytest.mark.asyncio
    async def test_create_daily_tasks_respects_auto_post(self, temp_db):
        """Should only create tasks for accounts with auto_post enabled."""
        mock_registry = MagicMock()
        mock_registry.list_accounts.return_value = ["XHS_01", "XHS_02"]
        mock_registry.get.side_effect = lambda aid: {
            "XHS_01": {
                "schedule": {"auto_post": True, "max_daily_posts": 2},
                "keywords": ["中考", "择校"],
            },
            "XHS_02": {
                "schedule": {"auto_post": False},
                "keywords": ["股票"],
            },
        }[aid]
        
        with patch("src.scheduler.task_creator.TASKS_DB_PATH", temp_db), \
             patch("src.scheduler.task_creator.registry", mock_registry):
            
            result = await create_daily_tasks()
            
            assert result["created"] == 1
            assert result["skipped"] == 1
            assert result["tasks"][0]["account_id"] == "XHS_01"
    
    @pytest.mark.asyncio
    async def test_create_daily_tasks_respects_daily_limit(self, temp_db):
        """Should not create tasks if daily limit is reached."""
        mock_registry = MagicMock()
        mock_registry.list_accounts.return_value = ["XHS_01"]
        mock_registry.get.return_value = {
            "schedule": {"auto_post": True, "max_daily_posts": 1},
            "keywords": ["中考"],
        }
        
        with patch("src.scheduler.task_creator.TASKS_DB_PATH", temp_db), \
             patch("src.scheduler.task_creator.registry", mock_registry):
            
            # Create first task
            result1 = await create_daily_tasks()
            assert result1["created"] == 1
            
            # Try to create another - should be skipped due to limit
            result2 = await create_daily_tasks()
            assert result2["created"] == 0
            assert "daily limit" in result2["skipped_details"][0]["reason"]


# ---------------------------------------------------------------------------
# Social Worker Tests
# ---------------------------------------------------------------------------

class TestSocialWorker:
    """Tests for social_worker.py"""
    
    def test_get_recent_posts_empty(self, temp_memory_dir):
        """Should return empty list when no memory exists."""
        with patch("src.scheduler.social_worker.MEMORY_DIR", temp_memory_dir):
            posts = get_recent_posts("XHS_01", days=1)
            assert posts == []
    
    def test_get_recent_posts_filters_by_date(self, temp_memory_dir):
        """Should only return posts within the specified days."""
        account_dir = temp_memory_dir / "XHS_01"
        account_dir.mkdir()
        memory_path = account_dir / "memory.json"
        
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(days=5)).isoformat()
        recent_time = (now - timedelta(hours=12)).isoformat()
        
        data = {
            "account_id": "XHS_01",
            "entries": [
                {"timestamp": old_time, "type": "success", "title": "Old Post"},
                {"timestamp": recent_time, "type": "success", "title": "Recent Post"},
            ],
        }
        with open(memory_path, "w") as f:
            json.dump(data, f)
        
        with patch("src.scheduler.social_worker.MEMORY_DIR", temp_memory_dir):
            posts = get_recent_posts("XHS_01", days=1)
            assert len(posts) == 1
            assert posts[0]["title"] == "Recent Post"
    
    def test_get_recent_posts_filters_by_type(self, temp_memory_dir):
        """Should only return successful posts."""
        account_dir = temp_memory_dir / "XHS_01"
        account_dir.mkdir()
        memory_path = account_dir / "memory.json"
        
        now = datetime.now(timezone.utc).isoformat()
        
        data = {
            "account_id": "XHS_01",
            "entries": [
                {"timestamp": now, "type": "success", "title": "Good Post"},
                {"timestamp": now, "type": "failed", "title": "Failed Post"},
                {"timestamp": now, "type": "rejected", "title": "Rejected Post"},
            ],
        }
        with open(memory_path, "w") as f:
            json.dump(data, f)
        
        with patch("src.scheduler.social_worker.MEMORY_DIR", temp_memory_dir):
            posts = get_recent_posts("XHS_01", days=1)
            assert len(posts) == 1
            assert posts[0]["title"] == "Good Post"
    
    def test_extract_keywords_from_tags(self):
        """Should extract keywords from tags."""
        keywords = extract_keywords("Some Title", ["中考", "择校", "政策"])
        assert "中考" in keywords
        assert "择校" in keywords
    
    def test_extract_keywords_from_title(self):
        """Should extract keywords from title when tags are empty."""
        keywords = extract_keywords("2026上海中考：体育考试新规解读", [])
        assert len(keywords) > 0
        # Should contain meaningful parts
        assert any("中考" in kw or "体育" in kw or "上海" in kw for kw in keywords)
    
    def test_extract_keywords_limits_count(self):
        """Should limit the number of keywords."""
        keywords = extract_keywords(
            "Very Long Title With Many Words",
            ["tag1", "tag2", "tag3", "tag4", "tag5"],
        )
        assert len(keywords) <= 4
    
    @pytest.mark.asyncio
    async def test_generate_smart_comment(self):
        """Should generate a comment using the LLM."""
        mock_router = MagicMock()
        mock_router.invoke = AsyncMock(return_value="这篇笔记太实用了！收藏了 👍")
        
        mock_feed = MagicMock()
        mock_feed.title = "中考体育满分攻略"
        mock_feed.desc = "分享一些备考技巧"
        
        persona = {
            "persona": {
                "name": "中考学生家长",
                "tone": "专业但亲切",
            }
        }
        
        comment = await generate_smart_comment(mock_router, mock_feed, persona)
        
        assert comment == "这篇笔记太实用了！收藏了 👍"
        mock_router.invoke.assert_called_once()


# ---------------------------------------------------------------------------
# Daily Scheduler Tests
# ---------------------------------------------------------------------------

class TestEngagementHistory:
    """Tests for engagement history tracking (Phase 2)"""
    
    def test_record_and_check_engagement(self, tmp_path):
        """Should record engagement and detect duplicates."""
        db_path = tmp_path / "engagement_history.db"
        
        with patch("src.scheduler.social_worker.ENGAGEMENT_DB_PATH", db_path):
            # Record an engagement
            record_engagement("XHS_01", "feed123", "like")
            
            # Should detect it exists
            assert has_engaged_with_feed("XHS_01", "feed123", "like") is True
            
            # Different feed should not exist
            assert has_engaged_with_feed("XHS_01", "feed456", "like") is False
            
            # Different action type should not exist
            assert has_engaged_with_feed("XHS_01", "feed123", "comment") is False
    
    def test_daily_engagement_count(self, tmp_path):
        """Should count today's engagements correctly."""
        db_path = tmp_path / "engagement_history.db"
        
        with patch("src.scheduler.social_worker.ENGAGEMENT_DB_PATH", db_path):
            # Record some engagements
            record_engagement("XHS_01", "feed1", "like")
            record_engagement("XHS_01", "feed2", "like")
            record_engagement("XHS_01", "feed3", "comment", "Great post!")
            
            # Check counts
            assert get_today_engagement_count("XHS_01", "like") == 2
            assert get_today_engagement_count("XHS_01", "comment") == 1
            assert get_today_engagement_count("XHS_01", "search") == 0
    
    def test_get_daily_stats(self, tmp_path):
        """Should return complete daily stats."""
        db_path = tmp_path / "engagement_history.db"
        
        with patch("src.scheduler.social_worker.ENGAGEMENT_DB_PATH", db_path):
            record_engagement("XHS_01", "feed1", "like")
            record_engagement("XHS_01", "kw1", "search")
            
            stats = get_daily_stats("XHS_01")
            
            assert stats["likes"] == 1
            assert stats["comments"] == 0
            assert stats["searches"] == 1
    
    def test_duplicate_engagement_ignored(self, tmp_path):
        """Should ignore duplicate engagements (INSERT OR IGNORE)."""
        db_path = tmp_path / "engagement_history.db"
        
        with patch("src.scheduler.social_worker.ENGAGEMENT_DB_PATH", db_path):
            # Record same engagement twice
            record_engagement("XHS_01", "feed1", "like")
            record_engagement("XHS_01", "feed1", "like")  # Duplicate
            
            # Should only count once
            assert get_today_engagement_count("XHS_01", "like") == 1


class TestAntiDetection:
    """Tests for anti-detection features (Phase 2)"""
    
    @pytest.mark.asyncio
    async def test_human_like_delay(self):
        """Should add a random delay within range."""
        import time
        
        start = time.monotonic()
        await human_like_delay((0.1, 0.2))
        elapsed = time.monotonic() - start
        
        # Should be at least 0.1 seconds
        assert elapsed >= 0.1
        # Should be reasonable (not too long due to random variation)
        assert elapsed < 1.0
    
    def test_comment_style_variation(self):
        """Comment generation should use varied styles."""
        from src.scheduler.social_worker import generate_smart_comment
        
        # The function uses random.choice for styles
        # Just verify the function signature is correct
        import inspect
        sig = inspect.signature(generate_smart_comment)
        params = list(sig.parameters.keys())
        
        assert "router" in params
        assert "feed" in params
        assert "persona" in params


class TestDailyScheduler:
    """Tests for daily_scheduler.py"""
    
    def test_scheduler_setup(self):
        """Should configure all jobs correctly."""
        from src.scheduler.daily_scheduler import DailyScheduler
        
        scheduler = DailyScheduler()
        scheduler.setup()
        
        jobs = scheduler.scheduler.get_jobs()
        job_ids = [job.id for job in jobs]
        
        assert "monitor_morning" in job_ids
        assert "daily_tasks" in job_ids
        assert "social_engagement" in job_ids
        assert "monitor_evening" in job_ids
    
    def test_scheduler_setup_idempotent(self):
        """Should not duplicate jobs on multiple setup calls."""
        from src.scheduler.daily_scheduler import DailyScheduler
        
        scheduler = DailyScheduler()
        scheduler.setup()
        scheduler.setup()  # Call again
        
        jobs = scheduler.scheduler.get_jobs()
        # Should still have exactly 4 jobs
        assert len(jobs) == 4
