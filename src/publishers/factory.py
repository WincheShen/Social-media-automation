"""Publisher Factory — Create platform-specific publishers.

Usage:
    from src.publishers.factory import get_publisher, Platform
    
    publisher = get_publisher(Platform.XIAOHONGSHU, account_config)
    result = await publisher.publish(content)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from .base import Publisher

logger = logging.getLogger(__name__)


class Platform(str, Enum):
    """Supported social media platforms."""
    
    XIAOHONGSHU = "xiaohongshu"
    WECHAT = "wechat"
    DOUYIN = "douyin"
    
    @classmethod
    def from_string(cls, value: str) -> "Platform":
        """Convert string to Platform enum."""
        value = value.lower().strip()
        for platform in cls:
            if platform.value == value:
                return platform
        raise ValueError(f"Unknown platform: {value}")


def get_publisher(platform: Platform | str, config: dict[str, Any] | None = None) -> Publisher:
    """Get a publisher instance for the specified platform.
    
    Args:
        platform: The target platform (enum or string)
        config: Platform-specific configuration from account YAML
    
    Returns:
        A Publisher instance for the platform
    
    Raises:
        ValueError: If the platform is not supported
    """
    if isinstance(platform, str):
        platform = Platform.from_string(platform)
    
    config = config or {}
    
    if platform == Platform.XIAOHONGSHU:
        from src.infra.xhs_cli import XhsCliAdapter
        
        xhs_config = config.get("xhs_cli", {})
        return XhsCliAdapter(
            account=xhs_config.get("account", "default"),
            cdp_port=xhs_config.get("cdp_port", 9222),
        )
    
    elif platform == Platform.WECHAT:
        from .wechat import WeChatPublisher, WeChatConfig
        
        wechat_config = config.get("wechat", {})
        return WeChatPublisher(
            config=WeChatConfig(
                app_id=wechat_config.get("app_id", ""),
                app_secret=wechat_config.get("app_secret", ""),
            ) if wechat_config else None
        )
    
    elif platform == Platform.DOUYIN:
        from .douyin import DouyinPublisher, DouyinConfig
        
        douyin_config = config.get("douyin", {})
        return DouyinPublisher(
            config=DouyinConfig(
                client_key=douyin_config.get("client_key", ""),
                client_secret=douyin_config.get("client_secret", ""),
                access_token=douyin_config.get("access_token"),
                open_id=douyin_config.get("open_id"),
            ) if douyin_config else None
        )
    
    else:
        raise ValueError(f"Unsupported platform: {platform}")


def get_platform_from_config(config: dict[str, Any]) -> Platform:
    """Detect platform from account configuration.
    
    Args:
        config: Account configuration dictionary
    
    Returns:
        Detected Platform enum
    """
    # Check explicit platform field
    if "platform" in config:
        return Platform.from_string(config["platform"])
    
    # Detect from config keys
    if "xhs_cli" in config:
        return Platform.XIAOHONGSHU
    if "wechat" in config:
        return Platform.WECHAT
    if "douyin" in config:
        return Platform.DOUYIN
    
    # Default to xiaohongshu for backward compatibility
    return Platform.XIAOHONGSHU


def list_supported_platforms() -> list[str]:
    """Return list of supported platform names."""
    return [p.value for p in Platform]
