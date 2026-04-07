"""Unit tests for the image generation module."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.infra.image_gen import (
    ImageGenerator,
    ImageGenerationError,
    STYLE_SUFFIXES,
    generate_image,
)


class TestImageGenerator:
    """Tests for ImageGenerator class."""
    
    def test_detect_backend_placeholder(self):
        """Should default to placeholder when no API keys are set."""
        with patch.dict("os.environ", {}, clear=True):
            gen = ImageGenerator()
            assert gen.backend == "placeholder"
    
    def test_detect_backend_openai(self):
        """Should use OpenAI when OPENAI_API_KEY is set."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            gen = ImageGenerator()
            assert gen.backend == "openai"
    
    def test_detect_backend_replicate(self):
        """Should use Replicate when REPLICATE_API_TOKEN is set."""
        with patch.dict("os.environ", {"REPLICATE_API_TOKEN": "test-token"}, clear=True):
            gen = ImageGenerator()
            assert gen.backend == "replicate"
    
    def test_force_backend(self):
        """Should allow forcing a specific backend."""
        gen = ImageGenerator(backend="placeholder")
        assert gen.backend == "placeholder"
    
    @pytest.mark.asyncio
    async def test_generate_placeholder(self, tmp_path):
        """Should create a placeholder file."""
        with patch("src.infra.image_gen.IMAGES_DIR", tmp_path):
            gen = ImageGenerator(backend="placeholder")
            path = await gen.generate("A test image", account_id="XHS_01")
            
            assert Path(path).exists()
            assert "placeholder" in path or "XHS_01" in path
    
    @pytest.mark.asyncio
    async def test_generate_with_style(self, tmp_path):
        """Should apply style suffix to prompt."""
        with patch("src.infra.image_gen.IMAGES_DIR", tmp_path):
            gen = ImageGenerator(backend="placeholder")
            
            # The placeholder backend doesn't actually use the style,
            # but we verify it doesn't crash
            path = await gen.generate(
                "A beautiful sunset",
                style="xiaohongshu",
                account_id="XHS_01",
            )
            
            assert Path(path).exists()
    
    @pytest.mark.asyncio
    async def test_generate_for_post(self, tmp_path):
        """Should generate image from post content."""
        with patch("src.infra.image_gen.IMAGES_DIR", tmp_path):
            gen = ImageGenerator(backend="placeholder")
            
            paths = await gen.generate_for_post(
                title="中考体育满分攻略",
                content="分享一些备考技巧...",
                tags=["中考", "体育", "备考"],
                account_id="XHS_01",
            )
            
            assert len(paths) == 1
            assert Path(paths[0]).exists()
    
    @pytest.mark.asyncio
    async def test_generate_for_post_with_explicit_prompt(self, tmp_path):
        """Should use explicit image_prompt when provided."""
        with patch("src.infra.image_gen.IMAGES_DIR", tmp_path):
            gen = ImageGenerator(backend="placeholder")
            
            paths = await gen.generate_for_post(
                title="Test",
                content="Test content",
                tags=[],
                image_prompt="A specific image description",
                account_id="XHS_01",
            )
            
            assert len(paths) == 1


class TestStyleSuffixes:
    """Tests for style suffix configuration."""
    
    def test_xiaohongshu_style_exists(self):
        """Should have xiaohongshu style."""
        assert "xiaohongshu" in STYLE_SUFFIXES
        assert "aesthetic" in STYLE_SUFFIXES["xiaohongshu"].lower()
    
    def test_wechat_style_exists(self):
        """Should have wechat style."""
        assert "wechat" in STYLE_SUFFIXES
        assert "professional" in STYLE_SUFFIXES["wechat"].lower()
    
    def test_douyin_style_exists(self):
        """Should have douyin style."""
        assert "douyin" in STYLE_SUFFIXES
        assert "vibrant" in STYLE_SUFFIXES["douyin"].lower()
    
    def test_default_style_exists(self):
        """Should have default style."""
        assert "default" in STYLE_SUFFIXES


class TestConvenienceFunction:
    """Tests for the generate_image convenience function."""
    
    @pytest.mark.asyncio
    async def test_generate_image_function(self, tmp_path):
        """Should work as a standalone function."""
        with patch("src.infra.image_gen.IMAGES_DIR", tmp_path):
            with patch.dict("os.environ", {}, clear=True):
                path = await generate_image("A test prompt")
                assert Path(path).exists()
