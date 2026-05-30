"""Tests for indicator_cache.py and the list_popular_indicators MCP tool (Story 5.3)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import mcp_server.indicator_cache as indicator_cache
from mcp_server.server import list_popular_indicators

POPULAR_INDICATORS_PATH = Path(__file__).parent.parent.parent / "mcp_server" / "popular_indicators.json"
RESPONSE_KEYS = {"success", "data", "total_count", "returned_count", "truncated"}
INDICATOR_KEYS = {"code", "name", "description"}


def _load_source_file() -> dict:
    with POPULAR_INDICATORS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the module-level singleton before and after each test."""
    indicator_cache._popular_indicators = None
    yield
    indicator_cache._popular_indicators = None


class TestGetPopularIndicators:
    """Tests for indicator_cache.get_popular_indicators (AC1, AC4)."""

    def test_returns_indicators_and_total(self):
        """AC1: loader returns dict with indicators list and total count."""
        result = indicator_cache.get_popular_indicators()
        assert isinstance(result, dict)
        assert isinstance(result["indicators"], list)
        assert isinstance(result["total"], int)
        assert result["total"] == len(result["indicators"])
        assert result["total"] > 0

    def test_singleton_caches_after_first_load(self):
        """AC4: file is read from disk exactly once across consecutive calls."""
        with patch(
            "mcp_server.indicator_cache._load_json",
            wraps=indicator_cache._load_json,
        ) as spy:
            first = indicator_cache.get_popular_indicators()
            second = indicator_cache.get_popular_indicators()
        assert spy.call_count == 1
        assert first["total"] == second["total"]
        assert first["indicators"] is second["indicators"]


class TestListPopularIndicatorsTool:
    """Tests for the list_popular_indicators MCP tool (AC2, AC3, AC5, AC6)."""

    @pytest.mark.asyncio
    async def test_returns_success_contract(self):
        """AC2: response has the exact 5 success-contract keys."""
        result = await list_popular_indicators()
        assert set(result.keys()) == RESPONSE_KEYS
        assert result["success"] is True
        assert isinstance(result["data"], list)
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_data_grouped_by_category(self):
        """AC3: data is a list of group objects {category, indicators}."""
        result = await list_popular_indicators()
        for group in result["data"]:
            assert set(group.keys()) == {"category", "indicators"}
            assert isinstance(group["category"], str)
            assert isinstance(group["indicators"], list)
            for ind in group["indicators"]:
                assert set(ind.keys()) == INDICATOR_KEYS
                assert "category" not in ind

    @pytest.mark.asyncio
    async def test_counts_reflect_indicators_not_groups(self):
        """AC2: total_count/returned_count are sum of indicators, not group count."""
        source = _load_source_file()
        expected_total = len(source["indicators"])

        result = await list_popular_indicators()
        summed = sum(len(g["indicators"]) for g in result["data"])

        assert result["total_count"] == expected_total
        assert result["returned_count"] == expected_total
        assert summed == expected_total
        assert result["total_count"] != len(result["data"])  # guard against group-count bug

    @pytest.mark.asyncio
    async def test_categories_match_source_file(self):
        """AC3: categories in response match the set in popular_indicators.json with no duplicates."""
        source = _load_source_file()
        expected_categories = {ind["category"] for ind in source["indicators"]}

        result = await list_popular_indicators()
        response_categories = [g["category"] for g in result["data"]]

        assert len(response_categories) == len(set(response_categories))  # no duplicates
        assert set(response_categories) == expected_categories

    @pytest.mark.asyncio
    async def test_no_api_client_required(self):
        """AC1: tool must work without _client — does not touch the API."""
        with patch("mcp_server.server._client", None):
            result = await list_popular_indicators()
        assert result["success"] is True
        assert len(result["data"]) > 0

    @pytest.mark.asyncio
    async def test_error_path_returns_api_error_type(self):
        """AC6: failure in the loader surfaces the error contract."""
        with patch(
            "mcp_server.server.indicator_cache.get_popular_indicators",
            side_effect=RuntimeError("boom"),
        ):
            result = await list_popular_indicators()
        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert isinstance(result["error"], str)
        assert result["error"]  # non-empty
