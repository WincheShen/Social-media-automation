"""Shared test fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_persona() -> dict:
    """A minimal persona config for testing."""
    return {
        "account_id": "TEST_01",
        "platform": "xiaohongshu",
        "track": "上海中考",
        "keywords": ["中考", "择校", "体育考"],
        "persona": {
            "name": "测试学长",
            "description": "测试用教育博主",
            "tone": "专业友好",
            "audience": "上海初中生家长",
            "system_prompt": "你是一位教育博主。",
        },
        "models": {
            "primary": "gemini-1.5-pro",
            "fallback": "gemini-1.5-flash",
        },
        "visual_style": {
            "color_scheme": ["#1a73e8", "#ffffff", "#f0f4f9"],
            "font": "思源黑体",
            "template": "knowledge_card",
        },
        "browser": {
            "profile_dir": "/tmp/test_profile",
            "proxy": None,
            "fingerprint": {
                "user_agent": "Mozilla/5.0 Test",
                "resolution": "1920x1080",
            },
        },
        "schedule": {
            "post_windows": ["19:00-21:00"],
            "max_daily_posts": 2,
            "review_mode": "review",
        },
        "sensitive_words_extra": ["包过", "保分"],
    }


@pytest.fixture
def sample_state(sample_persona) -> dict:
    """A minimal AgentState dict for testing."""
    return {
        "account_id": "TEST_01",
        "task": "分析 2026 上海体育中考新规",
        "persona": sample_persona,
        "memory": [],
        "research_results": [],
        "data_sources": [],
        "draft_title": "",
        "draft_content": "",
        "draft_tags": [],
        "visual_assets": [],
        "safety_passed": False,
        "safety_issues": [],
        "review_mode": "review",
        "approved": False,
        "publish_result": None,
        "post_metrics": None,
        "feedback_summary": None,
    }
