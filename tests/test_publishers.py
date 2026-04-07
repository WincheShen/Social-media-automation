"""Unit tests for the multi-platform publisher system."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.publishers import (
    Platform,
    get_publisher,
    get_platform_from_config,
    list_supported_platforms,
    PublishContent,
    PublishResult,
    PostMetrics,
)
from src.publishers.wechat import WeChatPublisher, WeChatConfig
from src.publishers.douyin import DouyinPublisher, DouyinConfig


class TestPlatformEnum:
    """Tests for Platform enum."""
    
    def test_platform_values(self):
        """Should have correct platform values."""
        assert Platform.XIAOHONGSHU.value == "xiaohongshu"
        assert Platform.WECHAT.value == "wechat"
        assert Platform.DOUYIN.value == "douyin"
    
    def test_from_string(self):
        """Should convert string to Platform enum."""
        assert Platform.from_string("xiaohongshu") == Platform.XIAOHONGSHU
        assert Platform.from_string("WECHAT") == Platform.WECHAT
        assert Platform.from_string("  douyin  ") == Platform.DOUYIN
    
    def test_from_string_invalid(self):
        """Should raise ValueError for unknown platform."""
        with pytest.raises(ValueError, match="Unknown platform"):
            Platform.from_string("instagram")


class TestPublisherFactory:
    """Tests for publisher factory functions."""
    
    def test_list_supported_platforms(self):
        """Should list all supported platforms."""
        platforms = list_supported_platforms()
        assert "xiaohongshu" in platforms
        assert "wechat" in platforms
        assert "douyin" in platforms
    
    def test_get_platform_from_config_explicit(self):
        """Should detect platform from explicit field."""
        config = {"platform": "wechat"}
        assert get_platform_from_config(config) == Platform.WECHAT
    
    def test_get_platform_from_config_xhs_cli(self):
        """Should detect xiaohongshu from xhs_cli config."""
        config = {"xhs_cli": {"account": "XHS_01", "cdp_port": 9222}}
        assert get_platform_from_config(config) == Platform.XIAOHONGSHU
    
    def test_get_platform_from_config_wechat(self):
        """Should detect wechat from wechat config."""
        config = {"wechat": {"app_id": "xxx"}}
        assert get_platform_from_config(config) == Platform.WECHAT
    
    def test_get_platform_from_config_douyin(self):
        """Should detect douyin from douyin config."""
        config = {"douyin": {"client_key": "xxx"}}
        assert get_platform_from_config(config) == Platform.DOUYIN
    
    def test_get_platform_from_config_default(self):
        """Should default to xiaohongshu."""
        config = {}
        assert get_platform_from_config(config) == Platform.XIAOHONGSHU
    
    def test_get_publisher_wechat(self):
        """Should create WeChatPublisher."""
        publisher = get_publisher(Platform.WECHAT, {})
        assert isinstance(publisher, WeChatPublisher)
    
    def test_get_publisher_douyin(self):
        """Should create DouyinPublisher."""
        publisher = get_publisher(Platform.DOUYIN, {})
        assert isinstance(publisher, DouyinPublisher)
    
    def test_get_publisher_from_string(self):
        """Should accept string platform name."""
        publisher = get_publisher("wechat", {})
        assert isinstance(publisher, WeChatPublisher)


class TestWeChatPublisher:
    """Tests for WeChat publisher."""
    
    def test_init_from_config(self):
        """Should initialize from config."""
        config = WeChatConfig(app_id="test_id", app_secret="test_secret")
        publisher = WeChatPublisher(config=config)
        assert publisher.config.app_id == "test_id"
    
    def test_init_from_env(self):
        """Should initialize from environment."""
        with patch.dict("os.environ", {"WECHAT_APP_ID": "env_id", "WECHAT_APP_SECRET": "env_secret"}):
            publisher = WeChatPublisher()
            assert publisher.config.app_id == "env_id"
    
    @pytest.mark.asyncio
    async def test_login_check_no_credentials(self):
        """Should fail login check without credentials."""
        publisher = WeChatPublisher(config=WeChatConfig(app_id="", app_secret=""))
        result = await publisher.login_check()
        assert result is False
    
    def test_markdown_to_html(self):
        """Should convert markdown to HTML."""
        publisher = WeChatPublisher(config=WeChatConfig(app_id="", app_secret=""))
        
        html = publisher._markdown_to_html("**bold** and *italic*")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html


class TestDouyinPublisher:
    """Tests for Douyin publisher."""
    
    def test_init_from_config(self):
        """Should initialize from config."""
        config = DouyinConfig(client_key="key", client_secret="secret")
        publisher = DouyinPublisher(config=config)
        assert publisher.config.client_key == "key"
    
    def test_init_from_env(self):
        """Should initialize from environment."""
        with patch.dict("os.environ", {
            "DOUYIN_CLIENT_KEY": "env_key",
            "DOUYIN_CLIENT_SECRET": "env_secret",
        }):
            publisher = DouyinPublisher()
            assert publisher.config.client_key == "env_key"
    
    @pytest.mark.asyncio
    async def test_login_check_no_token(self):
        """Should fail login check without access token."""
        publisher = DouyinPublisher(config=DouyinConfig(
            client_key="key",
            client_secret="secret",
        ))
        result = await publisher.login_check()
        assert result is False


class TestPublishContent:
    """Tests for PublishContent dataclass."""
    
    def test_create_content(self):
        """Should create content with all fields."""
        content = PublishContent(
            title="Test Title",
            body="Test body content",
            tags=["tag1", "tag2"],
            images=["/path/to/image.jpg"],
        )
        assert content.title == "Test Title"
        assert len(content.tags) == 2
        assert len(content.images) == 1
    
    def test_default_values(self):
        """Should have empty defaults for optional fields."""
        content = PublishContent(title="Title", body="Body")
        assert content.tags == []
        assert content.images == []


class TestPostMetrics:
    """Tests for PostMetrics dataclass."""
    
    def test_engagement_rate(self):
        """Should calculate engagement rate correctly."""
        metrics = PostMetrics(
            impressions=1000,
            likes=50,
            favorites=20,
            comments=10,
            shares=5,
        )
        # (50 + 20 + 10 + 5) / 1000 = 0.085
        assert metrics.engagement_rate == 0.085
    
    def test_engagement_rate_zero_impressions(self):
        """Should return 0 for zero impressions."""
        metrics = PostMetrics(impressions=0, likes=10)
        assert metrics.engagement_rate == 0.0
