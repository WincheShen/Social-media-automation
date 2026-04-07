"""Image Generation Module — Generate images for social media posts.

Supports multiple backends:
- OpenAI DALL-E 3 (high quality, paid)
- Replicate Flux (good quality, cheaper)
- Local placeholder (for testing)

Usage:
    from src.infra.image_gen import ImageGenerator
    
    gen = ImageGenerator()
    path = await gen.generate(prompt, style="xiaohongshu")
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

IMAGES_DIR = Path("data/images")

# Style suffixes to enhance prompts for different platforms
STYLE_SUFFIXES = {
    "xiaohongshu": (
        "clean aesthetic, soft lighting, minimalist composition, "
        "high quality photography style, Instagram worthy, "
        "warm color palette, lifestyle blog aesthetic"
    ),
    "wechat": (
        "professional, clean design, informative infographic style, "
        "clear typography, business casual aesthetic"
    ),
    "douyin": (
        "vibrant colors, dynamic composition, eye-catching, "
        "trending visual style, high contrast, energetic mood"
    ),
    "default": "high quality, professional photography, clean composition",
}

# Negative prompts to avoid common issues
NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, ugly, deformed, "
    "watermark, text, logo, signature, cropped, out of frame"
)


class ImageGenerationError(Exception):
    """Base exception for image generation errors."""
    pass


class ImageGenerator:
    """Unified interface for image generation backends."""
    
    def __init__(self, backend: str | None = None):
        """Initialize the image generator.
        
        Args:
            backend: Force a specific backend. If None, auto-detect based on env vars.
                     Options: "openai", "replicate", "placeholder"
        """
        self.backend = backend or self._detect_backend()
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("ImageGenerator initialized with backend: %s", self.backend)
    
    def _detect_backend(self) -> str:
        """Auto-detect available backend based on environment variables."""
        if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_IMAGE_ENABLED", "true").lower() == "true":
            return "openai"
        if os.getenv("REPLICATE_API_TOKEN"):
            return "replicate"
        return "placeholder"
    
    async def generate(
        self,
        prompt: str,
        style: str = "xiaohongshu",
        size: Literal["1024x1024", "1792x1024", "1024x1792"] = "1024x1024",
        account_id: str | None = None,
    ) -> str:
        """Generate an image and return the local file path.
        
        Args:
            prompt: The image description
            style: Platform style to apply (xiaohongshu, wechat, douyin)
            size: Image dimensions
            account_id: Optional account ID for organizing images
        
        Returns:
            Absolute path to the generated image file
        """
        # Enhance prompt with style suffix
        style_suffix = STYLE_SUFFIXES.get(style, STYLE_SUFFIXES["default"])
        enhanced_prompt = f"{prompt}, {style_suffix}"
        
        logger.info("[ImageGen] Generating image with %s backend", self.backend)
        logger.debug("[ImageGen] Prompt: %s", enhanced_prompt[:100])
        
        if self.backend == "openai":
            image_url = await self._generate_openai(enhanced_prompt, size)
        elif self.backend == "replicate":
            image_url = await self._generate_replicate(enhanced_prompt, size)
        else:
            return await self._generate_placeholder(prompt, account_id)
        
        # Download and save the image
        local_path = await self._download_image(image_url, account_id)
        logger.info("[ImageGen] Image saved to: %s", local_path)
        
        return str(local_path)
    
    async def _generate_openai(self, prompt: str, size: str) -> str:
        """Generate image using OpenAI DALL-E 3."""
        import openai
        
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        
        if base_url:
            client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            client = openai.AsyncOpenAI(api_key=api_key)
        
        try:
            response = await client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality="standard",
                n=1,
            )
            return response.data[0].url
        except openai.OpenAIError as e:
            logger.error("[ImageGen] OpenAI error: %s", e)
            raise ImageGenerationError(f"OpenAI image generation failed: {e}") from e
    
    async def _generate_replicate(self, prompt: str, size: str) -> str:
        """Generate image using Replicate Flux model."""
        api_token = os.getenv("REPLICATE_API_TOKEN")
        
        if not api_token:
            raise ImageGenerationError("REPLICATE_API_TOKEN not set")
        
        # Parse size to width/height
        width, height = map(int, size.split("x"))
        
        # Use Flux Schnell for fast generation
        model = "black-forest-labs/flux-schnell"
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Start prediction
            response = await client.post(
                "https://api.replicate.com/v1/predictions",
                headers={"Authorization": f"Token {api_token}"},
                json={
                    "version": "flux-schnell",
                    "input": {
                        "prompt": prompt,
                        "width": width,
                        "height": height,
                        "num_outputs": 1,
                        "go_fast": True,
                    },
                },
            )
            
            if response.status_code != 201:
                raise ImageGenerationError(f"Replicate API error: {response.text}")
            
            prediction = response.json()
            prediction_id = prediction["id"]
            
            # Poll for completion
            for _ in range(60):  # Max 60 seconds
                await asyncio.sleep(1)
                
                status_response = await client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers={"Authorization": f"Token {api_token}"},
                )
                
                result = status_response.json()
                status = result.get("status")
                
                if status == "succeeded":
                    output = result.get("output")
                    if isinstance(output, list) and output:
                        return output[0]
                    raise ImageGenerationError("No output from Replicate")
                
                if status == "failed":
                    error = result.get("error", "Unknown error")
                    raise ImageGenerationError(f"Replicate generation failed: {error}")
            
            raise ImageGenerationError("Replicate generation timed out")
    
    async def _generate_placeholder(self, prompt: str, account_id: str | None) -> str:
        """Generate a placeholder image for testing."""
        # Create a simple placeholder using a hash of the prompt
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        
        # Organize by account and date
        if account_id:
            subdir = IMAGES_DIR / account_id / datetime.now().strftime("%Y-%m-%d")
        else:
            subdir = IMAGES_DIR / "placeholder"
        
        subdir.mkdir(parents=True, exist_ok=True)
        
        filename = f"placeholder_{prompt_hash}_{uuid.uuid4().hex[:6]}.txt"
        filepath = subdir / filename
        
        # Write prompt to file as placeholder
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"PLACEHOLDER IMAGE\n")
            f.write(f"Prompt: {prompt}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
        
        logger.info("[ImageGen] Created placeholder: %s", filepath)
        return str(filepath.absolute())
    
    async def _download_image(self, url: str, account_id: str | None) -> Path:
        """Download image from URL and save locally."""
        # Organize by account and date
        if account_id:
            subdir = IMAGES_DIR / account_id / datetime.now().strftime("%Y-%m-%d")
        else:
            subdir = IMAGES_DIR / "generated"
        
        subdir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        filename = f"img_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}.png"
        filepath = subdir / filename
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            with open(filepath, "wb") as f:
                f.write(response.content)
        
        return filepath.absolute()
    
    async def generate_for_post(
        self,
        title: str,
        content: str,
        tags: list[str],
        image_prompt: str | None = None,
        account_id: str | None = None,
        style: str = "xiaohongshu",
    ) -> list[str]:
        """Generate images suitable for a social media post.
        
        If image_prompt is provided, use it directly.
        Otherwise, generate a prompt from the post content.
        
        Args:
            title: Post title
            content: Post content
            tags: Post tags
            image_prompt: Optional explicit image prompt
            account_id: Account ID for organizing images
            style: Platform style
        
        Returns:
            List of image file paths
        """
        if image_prompt:
            prompt = image_prompt
        else:
            # Generate prompt from content
            prompt = self._generate_prompt_from_content(title, content, tags)
        
        try:
            path = await self.generate(prompt, style=style, account_id=account_id)
            return [path]
        except ImageGenerationError as e:
            logger.error("[ImageGen] Failed to generate image: %s", e)
            return []
    
    def _generate_prompt_from_content(
        self,
        title: str,
        content: str,
        tags: list[str],
    ) -> str:
        """Generate an image prompt from post content."""
        # Extract key themes from title and tags
        themes = [title]
        themes.extend(tags[:3])
        
        # Create a descriptive prompt
        prompt = f"A visually appealing image representing: {', '.join(themes)}"
        
        return prompt


# Convenience function for quick usage
async def generate_image(
    prompt: str,
    style: str = "xiaohongshu",
    account_id: str | None = None,
) -> str:
    """Generate an image and return the local file path."""
    gen = ImageGenerator()
    return await gen.generate(prompt, style=style, account_id=account_id)
