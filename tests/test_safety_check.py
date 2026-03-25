"""Tests for Node 4: Content Safety Check."""

import pytest
from pathlib import Path
from unittest.mock import patch

from src.nodes.safety_check import (
    _check_sensitive_words,
    _check_finance_compliance,
    _check_content_length,
    _check_image_compliance,
    _load_sensitive_words,
    content_safety_check,
)


class TestSensitiveWordDetection:
    """Test sensitive word detection logic."""

    def test_detects_present_words(self):
        words = {"免费领取", "加微信", "暴涨"}
        found = _check_sensitive_words("快来免费领取资料，加微信咨询", words)
        assert "免费领取" in found
        assert "加微信" in found
        assert "暴涨" not in found

    def test_no_false_positives(self):
        words = {"免费领取", "加微信"}
        found = _check_sensitive_words("这是一篇正常的学习攻略", words)
        assert found == []

    def test_empty_word_list(self):
        found = _check_sensitive_words("任何内容", set())
        assert found == []


class TestFinanceCompliance:
    """Test financial content compliance checks."""

    def test_flags_absolute_claims(self):
        issues = _check_finance_compliance("这只股票一定涨，稳赚不赔！", "finance")
        assert any("一定涨" in i for i in issues)
        assert any("稳赚" in i for i in issues)

    def test_skips_non_finance_track(self):
        issues = _check_finance_compliance("这只股票一定涨", "教育")
        assert issues == []

    def test_clean_finance_content(self):
        issues = _check_finance_compliance("从技术面看，该股近期走势偏强", "finance")
        assert issues == []


class TestContentLength:
    """Test content length validation."""

    def test_title_too_short(self):
        issues = _check_content_length("短", "正文内容足够长" * 10)
        assert any("标题过短" in i for i in issues)

    def test_title_too_long(self):
        issues = _check_content_length("这是一个非常非常非常非常非常非常非常长的标题已经超过了三十个字了吧", "正文内容足够长" * 10)
        assert any("标题过长" in i for i in issues)

    def test_content_too_short(self):
        issues = _check_content_length("正常标题长度", "太短了")
        assert any("正文过短" in i for i in issues)

    def test_valid_lengths(self):
        issues = _check_content_length("合适的标题", "这是一段足够长的正文内容" * 10)
        assert issues == []


class TestImageCompliance:
    """Test image file compliance checks."""

    def test_missing_image_file(self):
        issues = _check_image_compliance(["/nonexistent/image.png"])
        assert any("不存在" in i for i in issues)

    def test_valid_image(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 100)
        issues = _check_image_compliance([str(img)])
        assert issues == []


class TestLoadSensitiveWords:
    """Test sensitive word loading from YAML files."""

    def test_load_common_words(self, tmp_path):
        common = tmp_path / "common.yaml"
        common.write_text("words:\n  - 免费领取\n  - 加微信\n", encoding="utf-8")

        with patch("src.nodes.safety_check.SENSITIVE_WORDS_DIR", tmp_path):
            words = _load_sensitive_words("nonexistent_track")

        assert "免费领取" in words
        assert "加微信" in words

    def test_load_track_specific_words(self, tmp_path):
        common = tmp_path / "common.yaml"
        common.write_text("words:\n  - 通用词\n", encoding="utf-8")
        finance = tmp_path / "finance.yaml"
        finance.write_text("words:\n  - 稳赚不赔\n", encoding="utf-8")

        with patch("src.nodes.safety_check.SENSITIVE_WORDS_DIR", tmp_path):
            words = _load_sensitive_words("finance")

        assert "通用词" in words
        assert "稳赚不赔" in words


class TestContentSafetyCheckNode:
    """Integration tests for the full safety check node."""

    @pytest.mark.asyncio
    async def test_clean_content_passes(self, tmp_path):
        common = tmp_path / "common.yaml"
        common.write_text("words:\n  - 免费领取\n", encoding="utf-8")

        state = {
            "account_id": "TEST_01",
            "persona": {"track": "教育", "sensitive_words_extra": []},
            "draft_title": "2026上海中考体育新规解读",
            "draft_content": "今年中考体育考试有重大变化，耐力跑标准调整如下" + "详细内容" * 20,
            "visual_assets": [],
        }

        with patch("src.nodes.safety_check.SENSITIVE_WORDS_DIR", tmp_path):
            result = await content_safety_check(state)

        assert result["safety_passed"] is True
        assert result["safety_issues"] == []

    @pytest.mark.asyncio
    async def test_sensitive_content_blocked(self, tmp_path):
        common = tmp_path / "common.yaml"
        common.write_text("words:\n  - 免费领取\n", encoding="utf-8")

        state = {
            "account_id": "TEST_01",
            "persona": {"track": "教育", "sensitive_words_extra": ["包过"]},
            "draft_title": "包过！免费领取中考秘籍",
            "draft_content": "这份资料包过中考" + "详细内容" * 20,
            "visual_assets": [],
        }

        with patch("src.nodes.safety_check.SENSITIVE_WORDS_DIR", tmp_path):
            result = await content_safety_check(state)

        assert result["safety_passed"] is False
        assert len(result["safety_issues"]) > 0

    @pytest.mark.asyncio
    async def test_finance_disclaimer_auto_appended(self, tmp_path):
        common = tmp_path / "common.yaml"
        common.write_text("words: []\n", encoding="utf-8")

        state = {
            "account_id": "XHS_02",
            "persona": {"track": "finance", "sensitive_words_extra": []},
            "draft_title": "今日A股技术面分析",
            "draft_content": "从K线形态来看，大盘短期内呈现震荡走势" + "分析内容" * 20,
            "visual_assets": [],
        }

        with patch("src.nodes.safety_check.SENSITIVE_WORDS_DIR", tmp_path):
            result = await content_safety_check(state)

        assert result["safety_passed"] is True
        assert "免责声明" in result.get("draft_content", "")
