"""Douyin (TikTok China) Publisher

Publishes content to Douyin (抖音).

Note: Douyin Open Platform API requires:
1. Registered developer account
2. App credentials (Client Key, Client Secret)
3. User authorization (OAuth 2.0)

This is a placeholder implementation. Full integration requires:
- Douyin Open Platform API access
- Video upload capabilities (Douyin is primarily video-based)
- OAuth flow for user authorization
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

from .base import PostMetrics, PublishContent, PublishResult, Publisher

logger = logging.getLogger(__name__)


@dataclass
class DouyinConfig:
    """Configuration for Douyin Open Platform."""
    
    client_key: str
    client_secret: str
    access_token: Optional[str] = None
    open_id: Optional[str] = None
    api_base: str = "https://open.douyin.com"


class DouyinPublisher(Publisher):
    """Publisher for Douyin (抖音).
    
    Implements the Publisher protocol for Douyin platform.
    
    Note: Douyin is primarily a video platform. This publisher
    supports image posts (图文) which are available on Douyin.
    """
    
    def __init__(self, config: DouyinConfig | None = None):
        """Initialize the Douyin publisher.
        
        Args:
            config: Douyin API configuration. If None, reads from environment.
        """
        if config:
            self.config = config
        else:
            self.config = DouyinConfig(
                client_key=os.getenv("DOUYIN_CLIENT_KEY", ""),
                client_secret=os.getenv("DOUYIN_CLIENT_SECRET", ""),
                access_token=os.getenv("DOUYIN_ACCESS_TOKEN"),
                open_id=os.getenv("DOUYIN_OPEN_ID"),
            )
    
    async def _refresh_token(self) -> str:
        """Refresh the access token if needed."""
        if self.config.access_token:
            return self.config.access_token
        
        # In production, this would implement OAuth refresh flow
        raise ValueError("Douyin access token not configured. OAuth flow required.")
    
    async def login_check(self) -> bool:
        """Check if the Douyin API credentials are valid."""
        try:
            if not self.config.access_token or not self.config.open_id:
                logger.warning("[Douyin] Missing access_token or open_id")
                return False
            
            # Verify token by fetching user info
            url = f"{self.config.api_base}/oauth/userinfo/"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params={
                        "access_token": self.config.access_token,
                        "open_id": self.config.open_id,
                    },
                )
                data = response.json()
            
            if data.get("data", {}).get("error_code", 0) != 0:
                return False
            
            return True
            
        except Exception as e:
            logger.warning("[Douyin] Login check failed: %s", e)
            return False
    
    async def _upload_image(self, image_path: str) -> str:
        """Upload an image to Douyin and return the image_id."""
        import aiofiles
        
        url = f"{self.config.api_base}/image/upload/"
        
        async with aiofiles.open(image_path, "rb") as f:
            image_data = await f.read()
        
        filename = os.path.basename(image_path)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                params={
                    "access_token": self.config.access_token,
                    "open_id": self.config.open_id,
                },
                files={"image": (filename, image_data)},
            )
            data = response.json()
        
        if data.get("data", {}).get("error_code", 0) != 0:
            error = data.get("data", {}).get("description", "Unknown error")
            raise ValueError(f"Failed to upload image: {error}")
        
        return data["data"]["image"]["image_id"]
    
    async def publish(self, content: PublishContent) -> PublishResult:
        """Publish content to Douyin.
        
        Douyin supports:
        - Video posts (主要)
        - Image posts (图文笔记)
        
        This implementation focuses on image posts.
        """
        try:
            if not self.config.access_token or not self.config.open_id:
                return PublishResult(
                    success=False,
                    error="Douyin credentials not configured",
                )
            
            # Upload images
            image_ids = []
            for image_path in content.images[:9]:  # Douyin allows up to 9 images
                try:
                    image_id = await self._upload_image(image_path)
                    image_ids.append(image_id)
                except Exception as e:
                    logger.warning("[Douyin] Failed to upload image %s: %s", image_path, e)
            
            if not image_ids and content.images:
                return PublishResult(
                    success=False,
                    error="Failed to upload any images",
                )
            
            # Create image post
            url = f"{self.config.api_base}/image/create/"
            
            # Build post content
            # Douyin uses text field for caption
            caption = f"{content.title}\n\n{content.body}"
            if content.tags:
                hashtags = " ".join(f"#{tag}" for tag in content.tags)
                caption = f"{caption}\n\n{hashtags}"
            
            payload = {
                "image_id": ",".join(image_ids) if image_ids else "",
                "text": caption[:2200],  # Douyin caption limit
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    params={
                        "access_token": self.config.access_token,
                        "open_id": self.config.open_id,
                    },
                    json=payload,
                )
                data = response.json()
            
            if data.get("data", {}).get("error_code", 0) != 0:
                error = data.get("data", {}).get("description", "Unknown error")
                return PublishResult(success=False, error=f"Failed to publish: {error}")
            
            item_id = data.get("data", {}).get("item_id", "")
            logger.info("[Douyin] Post published: %s", item_id)
            
            return PublishResult(
                success=True,
                post_id=item_id,
                post_url=f"https://www.douyin.com/video/{item_id}" if item_id else None,
            )
            
        except Exception as e:
            logger.error("[Douyin] Publish failed: %s", e)
            return PublishResult(success=False, error=str(e))
    
    async def fetch_metrics(self, post_id: str) -> PostMetrics:
        """Fetch engagement metrics for a published post."""
        try:
            if not self.config.access_token or not self.config.open_id:
                return PostMetrics()
            
            url = f"{self.config.api_base}/item/data/"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params={
                        "access_token": self.config.access_token,
                        "open_id": self.config.open_id,
                        "item_id": post_id,
                    },
                )
                data = response.json()
            
            if data.get("data", {}).get("error_code", 0) != 0:
                return PostMetrics()
            
            stats = data.get("data", {}).get("result", {})
            
            return PostMetrics(
                impressions=stats.get("play_count", 0),
                likes=stats.get("digg_count", 0),
                favorites=stats.get("collect_count", 0),
                comments=stats.get("comment_count", 0),
                shares=stats.get("share_count", 0),
            )
            
        except Exception as e:
            logger.warning("[Douyin] Failed to fetch metrics: %s", e)
            return PostMetrics()
