"""WeChat Official Account Publisher

Publishes content to WeChat Official Account (微信公众号).

Note: WeChat Official Account API requires:
1. Verified service account (服务号) or subscription account (订阅号)
2. API credentials (AppID, AppSecret)
3. Content must pass WeChat's content review

This is a placeholder implementation. Full integration requires:
- WeChat Official Account Platform API access
- Media upload for images
- Draft creation and publishing workflow
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
class WeChatConfig:
    """Configuration for WeChat Official Account."""
    
    app_id: str
    app_secret: str
    # Optional: for custom domain
    api_base: str = "https://api.weixin.qq.com"


class WeChatPublisher(Publisher):
    """Publisher for WeChat Official Account (微信公众号).
    
    Implements the Publisher protocol for WeChat platform.
    """
    
    def __init__(self, config: WeChatConfig | None = None):
        """Initialize the WeChat publisher.
        
        Args:
            config: WeChat API configuration. If None, reads from environment.
        """
        if config:
            self.config = config
        else:
            app_id = os.getenv("WECHAT_APP_ID", "")
            app_secret = os.getenv("WECHAT_APP_SECRET", "")
            self.config = WeChatConfig(app_id=app_id, app_secret=app_secret)
        
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
    
    async def _get_access_token(self) -> str:
        """Get or refresh the access token."""
        import time
        
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        
        if not self.config.app_id or not self.config.app_secret:
            raise ValueError("WeChat AppID and AppSecret are required")
        
        url = f"{self.config.api_base}/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.config.app_id,
            "secret": self.config.app_secret,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()
        
        if "access_token" not in data:
            error = data.get("errmsg", "Unknown error")
            raise ValueError(f"Failed to get access token: {error}")
        
        self._access_token = data["access_token"]
        # Token expires in 7200 seconds, refresh 5 minutes early
        self._token_expires_at = time.time() + data.get("expires_in", 7200) - 300
        
        return self._access_token
    
    async def login_check(self) -> bool:
        """Check if the WeChat API credentials are valid."""
        try:
            await self._get_access_token()
            return True
        except Exception as e:
            logger.warning("[WeChat] Login check failed: %s", e)
            return False
    
    async def _upload_image(self, image_path: str) -> str:
        """Upload an image to WeChat and return the media_id."""
        import aiofiles
        
        token = await self._get_access_token()
        url = f"{self.config.api_base}/cgi-bin/material/add_material"
        params = {"access_token": token, "type": "image"}
        
        async with aiofiles.open(image_path, "rb") as f:
            image_data = await f.read()
        
        # Determine filename and content type
        filename = os.path.basename(image_path)
        content_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
        
        async with httpx.AsyncClient() as client:
            files = {"media": (filename, image_data, content_type)}
            response = await client.post(url, params=params, files=files)
            data = response.json()
        
        if "media_id" not in data:
            error = data.get("errmsg", "Unknown error")
            raise ValueError(f"Failed to upload image: {error}")
        
        return data["media_id"]
    
    async def publish(self, content: PublishContent) -> PublishResult:
        """Publish content to WeChat Official Account.
        
        WeChat publishing workflow:
        1. Upload images to get media_ids
        2. Create a draft article
        3. Submit for review (optional, depending on account type)
        4. Publish the article
        """
        try:
            token = await self._get_access_token()
            
            # Upload images if any
            thumb_media_id = None
            if content.images:
                thumb_media_id = await self._upload_image(content.images[0])
            
            # Create article content
            # WeChat uses HTML for article body
            html_body = self._markdown_to_html(content.body)
            
            article = {
                "title": content.title,
                "thumb_media_id": thumb_media_id or "",
                "author": "",
                "digest": content.body[:120] if len(content.body) > 120 else content.body,
                "show_cover_pic": 1 if thumb_media_id else 0,
                "content": html_body,
                "content_source_url": "",
                "need_open_comment": 1,
                "only_fans_can_comment": 0,
            }
            
            # Create draft
            url = f"{self.config.api_base}/cgi-bin/draft/add"
            payload = {"articles": [article]}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    params={"access_token": token},
                    json=payload,
                )
                data = response.json()
            
            if "media_id" not in data:
                error = data.get("errmsg", "Unknown error")
                return PublishResult(success=False, error=f"Failed to create draft: {error}")
            
            draft_media_id = data["media_id"]
            logger.info("[WeChat] Draft created: %s", draft_media_id)
            
            # Publish the draft
            publish_url = f"{self.config.api_base}/cgi-bin/freepublish/submit"
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    publish_url,
                    params={"access_token": token},
                    json={"media_id": draft_media_id},
                )
                publish_data = response.json()
            
            if publish_data.get("errcode", 0) != 0:
                error = publish_data.get("errmsg", "Unknown error")
                return PublishResult(
                    success=False,
                    post_id=draft_media_id,
                    error=f"Failed to publish: {error}",
                )
            
            publish_id = publish_data.get("publish_id", "")
            logger.info("[WeChat] Article published: %s", publish_id)
            
            return PublishResult(
                success=True,
                post_id=publish_id,
                post_url=None,  # WeChat doesn't return URL immediately
            )
            
        except Exception as e:
            logger.error("[WeChat] Publish failed: %s", e)
            return PublishResult(success=False, error=str(e))
    
    async def fetch_metrics(self, post_id: str) -> PostMetrics:
        """Fetch engagement metrics for a published article.
        
        Note: WeChat metrics API has limitations and may require
        additional permissions.
        """
        try:
            token = await self._get_access_token()
            
            # Get article statistics
            url = f"{self.config.api_base}/datacube/getarticletotal"
            
            # WeChat requires date range for statistics
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    params={"access_token": token},
                    json={"begin_date": start_date, "end_date": end_date},
                )
                data = response.json()
            
            # Parse metrics from response
            # This is simplified - actual implementation needs to match post_id
            if "list" in data and data["list"]:
                stats = data["list"][0].get("details", [{}])[0]
                return PostMetrics(
                    impressions=stats.get("int_page_read_count", 0),
                    likes=stats.get("like_count", 0) or stats.get("old_like_count", 0),
                    favorites=stats.get("add_to_fav_count", 0),
                    comments=0,  # WeChat doesn't provide comment count in this API
                    shares=stats.get("share_count", 0),
                )
            
            return PostMetrics()
            
        except Exception as e:
            logger.warning("[WeChat] Failed to fetch metrics: %s", e)
            return PostMetrics()
    
    def _markdown_to_html(self, markdown_text: str) -> str:
        """Convert markdown-like text to WeChat-compatible HTML."""
        import re
        
        html = markdown_text
        
        # Bold: **text** -> <strong>text</strong>
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        
        # Italic: *text* -> <em>text</em>
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        # Line breaks
        html = html.replace('\n\n', '</p><p>')
        html = html.replace('\n', '<br/>')
        
        # Wrap in paragraphs
        html = f'<p>{html}</p>'
        
        # Clean up empty paragraphs
        html = re.sub(r'<p>\s*</p>', '', html)
        
        return html
