"""Tests for Node 2: Multi-VLM Research Engine."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.nodes.research_engine import (
    _classify_task,
    _build_search_queries,
    _format_search_results,
    _parse_research_response,
    multi_vlm_research,
)
from src.infra.model_adapter import get_role_model, get_fallback_model, ModelRouter


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


class TestRoleModelRouting:
    """Test per-role model routing via get_role_model."""

    def test_explicit_roles(self):
        persona = {"models": {
            "data_collector": "gemini-2.5-pro",
            "logic_analyst": "claude-3.7-opus",
            "copywriter": "claude-3.7-sonnet",
            "strategist": "gpt-4o",
            "fallback": "gemini-2.5-flash",
        }}
        assert get_role_model(persona, "data_collector") == "gemini-2.5-pro"
        assert get_role_model(persona, "logic_analyst") == "claude-3.7-opus"
        assert get_role_model(persona, "copywriter") == "claude-3.7-sonnet"
        assert get_role_model(persona, "strategist") == "gpt-4o"
        assert get_fallback_model(persona) == "gemini-2.5-flash"

    def test_legacy_primary_fallback(self):
        """Old-style config with only primary/fallback should still work."""
        persona = {"models": {"primary": "gemini-2.5-pro", "fallback": "gemini-2.5-flash"}}
        assert get_role_model(persona, "data_collector") == "gemini-2.5-pro"
        assert get_role_model(persona, "copywriter") == "gemini-2.5-pro"
        assert get_fallback_model(persona) == "gemini-2.5-flash"

    def test_missing_models_uses_defaults(self):
        persona = {}
        assert get_role_model(persona, "data_collector") == "gemini-2.5-pro"
        assert get_role_model(persona, "logic_analyst") == "claude-3.7-opus"
        assert get_role_model(persona, "copywriter") == "claude-3.7-sonnet"
        assert get_role_model(persona, "strategist") == "gpt-4o"
        assert get_fallback_model(persona) == "gemini-2.5-flash"


class TestModelRouter:
    """Test ModelRouter track-aware routing."""

    def test_zhongkao_policy_boosts_gemini_temp(self):
        """上海中考 + policy_analysis → data_collector temp lowered to 0.15."""
        persona = {
            "track": "上海中考",
            "models": {
                "data_collector": "gemini-2.5-pro",
                "logic_analyst": "claude-3.7-opus",
                "fallback": "gemini-2.5-flash",
            },
        }
        router = ModelRouter(persona)
        rc = router.route("data_collector", {"task_type": "policy_analysis"})
        assert rc.model == "gemini-2.5-pro"
        assert rc.temperature == 0.15
        assert "政策条文" in rc.system_prompt_suffix

    def test_zhongkao_analyst_gets_suffix(self):
        persona = {"track": "上海中考", "models": {"fallback": "gemini-2.5-flash"}}
        router = ModelRouter(persona)
        rc = router.route("logic_analyst")
        assert rc.temperature == 0.25
        assert "家长" in rc.system_prompt_suffix

    def test_elderly_copywriter_warm_temp(self):
        """老年生活 → copywriter temp raised to 0.9."""
        persona = {
            "track": "老年生活",
            "models": {
                "copywriter": "claude-3.7-sonnet",
                "fallback": "gemini-2.5-flash",
            },
        }
        router = ModelRouter(persona)
        rc = router.route("copywriter")
        assert rc.model == "claude-3.7-sonnet"
        assert rc.temperature == 0.9
        assert "温暖" in rc.system_prompt_suffix

    def test_finance_conservative_copywriter(self):
        persona = {"track": "finance", "models": {"fallback": "gemini-2.5-pro"}}
        router = ModelRouter(persona)
        rc = router.route("copywriter")
        assert rc.temperature == 0.6
        assert "免责声明" in rc.system_prompt_suffix

    def test_no_track_uses_base_params(self):
        """No track match → role base params unchanged."""
        persona = {
            "track": "旅游",
            "models": {"copywriter": "claude-3.7-sonnet", "fallback": "gemini-2.5-flash"},
        }
        router = ModelRouter(persona)
        rc = router.route("copywriter")
        assert rc.temperature == 0.8  # base for copywriter
        assert rc.system_prompt_suffix == ""

    def test_fallback_resolved(self):
        persona = {"models": {"fallback": "gemini-2.0-flash"}}
        router = ModelRouter(persona)
        rc = router.route("strategist")
        assert rc.fallback == "gemini-2.0-flash"


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

        # Stage 1 extraction response
        extraction_response = json.dumps({
            "extracted_facts": [
                {"fact": "耐力跑标准降低10秒", "source_url": "https://edu.sh.cn/1", "importance": "high"},
            ],
            "raw_data_points": ["耐力跑标准变化"],
            "source_count": 1,
        })

        state = {
            "account_id": "XHS_01",
            "task": "分析 2026 上海体育中考新规",
            "persona": {
                "track": "上海中考",
                "keywords": ["中考", "择校", "体育考"],
                "models": {
                    "data_collector": "gemini-2.5-pro",
                    "logic_analyst": "claude-3.7-opus",
                    "fallback": "gemini-2.5-flash",
                },
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
                "src.infra.model_adapter.ModelAdapter.invoke_with_fallback",
                new_callable=AsyncMock,
                side_effect=[extraction_response, llm_response],
            ),
        ):
            result = await multi_vlm_research(state)

        assert len(result["research_results"]) == 1
        analysis = result["research_results"][0]["analysis"]
        assert "耐力跑" in analysis["key_facts"][0]
        assert len(result["data_sources"]) > 0
        # Verify two-stage model routing
        models_used = result["research_results"][0]["models_used"]
        assert models_used["data_collector"] == "gemini-2.5-pro"
        assert models_used["logic_analyst"] == "claude-3.7-opus"
