"""Tests for Node 2: Multi-VLM Research Engine."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.nodes.research_engine import (
    _classify_task,
    _select_model,
    _build_search_queries,
    _format_search_results,
    _parse_research_response,
    multi_vlm_research,
)


class TestClassifyTask:
    """Test task classification logic."""

    def test_policy_analysis(self):
        assert _classify_task("分析 2026 上海体育中考新规", "") == "policy_analysis"
        assert _classify_task("解读最新教育政策文件", "") == "policy_analysis"

    def test_market_analysis(self):
        assert _classify_task("分析特斯拉股票走势", "") == "market_analysis"
        assert _classify_task("今日A股行情点评", "") == "market_analysis"
        assert _classify_task("K线分析入门", "") == "market_analysis"

    def test_trend_scan(self):
        assert _classify_task("最近养生热点话题", "") == "trend_scan"
        assert _classify_task("社交媒体趋势分析", "") == "trend_scan"

    def test_general(self):
        assert _classify_task("写一篇学习攻略", "") == "general"
        assert _classify_task("推荐几本好书", "") == "general"


class TestSelectModel:
    """Test model selection based on task type and persona config."""

    def test_policy_uses_gemini_pro(self):
        persona = {"models": {"primary": "gemini-1.5-flash", "fallback": "gemini-1.5-flash"}}
        primary, fallback = _select_model("policy_analysis", persona)
        assert primary == "gemini-1.5-pro"
        assert fallback == "gemini-1.5-flash"

    def test_market_uses_claude(self):
        persona = {"models": {"primary": "gemini-1.5-pro", "fallback": "gemini-1.5-flash"}}
        primary, fallback = _select_model("market_analysis", persona)
        assert primary == "claude-3.7-sonnet"

    def test_general_uses_persona_primary(self):
        persona = {"models": {"primary": "gemini-1.5-flash", "fallback": "gemini-1.5-flash"}}
        primary, fallback = _select_model("general", persona)
        assert primary == "gemini-1.5-flash"

    def test_missing_models_config(self):
        persona = {}
        primary, fallback = _select_model("general", persona)
        assert primary == "gemini-1.5-pro"
        assert fallback == "gemini-1.5-flash"


class TestBuildSearchQueries:
    """Test search query generation."""

    def test_basic_query(self):
        persona = {"keywords": []}
        queries = _build_search_queries("中考体育新规", persona)
        assert queries == ["中考体育新规"]

    def test_with_keywords(self):
        persona = {"keywords": ["中考", "择校", "体育考", "自招"]}
        queries = _build_search_queries("体育新规", persona)
        assert len(queries) == 2
        assert queries[0] == "体育新规"
        assert "中考" in queries[1]


class TestFormatSearchResults:
    """Test search result formatting."""

    def test_empty_results(self):
        assert _format_search_results([]) == "(无搜索结果)"

    def test_formats_results(self):
        results = [
            {"title": "标题1", "url": "https://example.com/1", "content": "摘要1"},
            {"title": "标题2", "url": "https://example.com/2", "content": "摘要2"},
        ]
        text = _format_search_results(results)
        assert "标题1" in text
        assert "https://example.com/1" in text
        assert "结果 1" in text
        assert "结果 2" in text


class TestParseResearchResponse:
    """Test LLM response JSON parsing."""

    def test_parse_json_block(self):
        text = '一些前言\n```json\n{"key_facts": ["fact1"], "summary": "ok"}\n```\n结语'
        result = _parse_research_response(text)
        assert result["key_facts"] == ["fact1"]
        assert result["summary"] == "ok"

    def test_parse_plain_json(self):
        text = '{"key_facts": ["a"], "pain_points": [], "content_angles": [], "summary": "s"}'
        result = _parse_research_response(text)
        assert result["key_facts"] == ["a"]

    def test_fallback_on_invalid_json(self):
        text = "这不是JSON，只是普通文字分析结果"
        result = _parse_research_response(text)
        assert result["key_facts"] == []
        assert "这不是JSON" in result["summary"]


class TestMultiVlmResearchNode:
    """Integration test for the research node."""

    @pytest.mark.asyncio
    async def test_research_with_mocked_search_and_llm(self):
        """Test full node with mocked Tavily + LLM."""
        mock_search_results = [
            {"title": "新规详解", "url": "https://edu.sh.cn/1", "content": "耐力跑标准变化", "score": 0.9},
        ]

        llm_response = json.dumps({
            "key_facts": ["耐力跑标准降低10秒"],
            "pain_points": ["家长担心孩子体能不足"],
            "content_angles": [{"angle": "对比新旧标准", "supporting_data": "数据", "source_url": "url"}],
            "summary": "2026年上海中考体育新规主要调整了耐力跑标准",
        })

        state = {
            "account_id": "XHS_01",
            "task": "分析 2026 上海体育中考新规",
            "persona": {
                "track": "上海中考",
                "keywords": ["中考", "择校", "体育考"],
                "models": {"primary": "gemini-1.5-pro", "fallback": "gemini-1.5-flash"},
                "persona": {
                    "audience": "上海初中生家长",
                    "system_prompt": "你是教育博主",
                },
            },
            "memory": [],
        }

        with (
            patch(
                "src.nodes.research_engine._tavily_search",
                new_callable=AsyncMock,
                return_value=mock_search_results,
            ),
            patch(
                "src.nodes.research_engine.ModelAdapter.invoke_with_fallback",
                new_callable=AsyncMock,
                return_value=llm_response,
            ),
        ):
            result = await multi_vlm_research(state)

        assert len(result["research_results"]) == 1
        analysis = result["research_results"][0]["analysis"]
        assert "耐力跑" in analysis["key_facts"][0]
        assert len(result["data_sources"]) > 0
