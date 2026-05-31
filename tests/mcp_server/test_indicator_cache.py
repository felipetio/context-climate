"""Tests for indicator_cache.py and the list_popular_indicators/search_local_indicators MCP tools.

Covers Story 5.3 (popular indicators) and Story 5.4 (offline search).
"""

import inspect
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import mcp_server.config as config
import mcp_server.indicator_cache as indicator_cache
from mcp_server.server import list_popular_indicators, search_local_indicators

POPULAR_INDICATORS_PATH = Path(__file__).parent.parent.parent / "mcp_server" / "popular_indicators.json"
METADATA_INDICATORS_PATH = Path(__file__).parent.parent.parent / "mcp_server" / "metadata_indicators.json"
RESPONSE_KEYS = {"success", "data", "total_count", "returned_count", "truncated"}
INDICATOR_KEYS = {"code", "name", "description"}
SEARCH_RESPONSE_KEYS = {"success", "query", "total_matches", "data", "note"}
SEARCH_RESULT_KEYS = {"indicator", "name", "description", "source", "relevance_score"}
NO_MATCH_NOTE = "No local matches found. Try search_indicators for API-based search."
MATCH_NOTE = "Local search - instant results from cached metadata"


def _load_source_file() -> dict:
    with POPULAR_INDICATORS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the module-level singletons before and after each test."""
    indicator_cache._popular_indicators = None
    indicator_cache._metadata_indicators = None
    yield
    indicator_cache._popular_indicators = None
    indicator_cache._metadata_indicators = None


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


# ---------------------------------------------------------------------------
# Story 5.4 — offline search via search_local_indicators
# ---------------------------------------------------------------------------

# Crafted so that codes do NOT contain the query terms used by the
# word-in-name / substring-in-name / substring-in-description tests. This
# avoids accidental hits on the higher-priority code-substring rule (90).
SCORING_FIXTURE = [
    {
        "code": "SP_POP_TOTL",
        "name": "Population, total",
        "description": "Total population midyear estimates by country.",
        "source": "WDI",
    },
    {
        "code": "EN_FUEL_KT",
        "name": "CO2 emissions (kt)",
        "description": "Carbon dioxide emissions from fuel combustion.",
        "source": "WDI",
    },
    {
        "code": "EG_ELEC_PC",
        "name": "Electric power consumption",
        "description": "Kilowatt-hours per capita per year.",
        "source": "WDI",
    },
]


class TestGetMetadataIndicators:
    """AC5: metadata loader and singleton caching."""

    def test_returns_list_of_records(self):
        result = indicator_cache.get_metadata_indicators()
        assert isinstance(result, list)
        assert len(result) > 0
        # First record has the expected metadata shape (presence, not exact values).
        first = result[0]
        assert isinstance(first, dict)

    def test_singleton_caches_after_first_load(self):
        with patch(
            "mcp_server.indicator_cache._load_json",
            wraps=indicator_cache._load_json,
        ) as spy:
            first = indicator_cache.get_metadata_indicators()
            second = indicator_cache.get_metadata_indicators()
        assert spy.call_count == 1
        assert first is second

    def test_metadata_and_popular_caches_are_independent(self):
        """Loading the metadata cache must not pollute the popular cache and vice versa."""
        meta = indicator_cache.get_metadata_indicators()
        popular = indicator_cache.get_popular_indicators()
        assert isinstance(meta, list)
        assert isinstance(popular, dict)
        assert "indicators" in popular
        # The metadata list and the popular indicators list are different objects.
        assert meta is not popular["indicators"]


class TestSearchLocalMetadata:
    """AC1, AC3: pure scoring function over the cached metadata list."""

    @pytest.fixture
    def scoring_fixture(self, monkeypatch):
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", SCORING_FIXTURE)
        return SCORING_FIXTURE

    def test_exact_code_match_scores_100(self, scoring_fixture):
        results = indicator_cache.search_local_metadata("SP_POP_TOTL")
        assert len(results) == 1
        assert results[0]["relevance_score"] == 100
        assert results[0]["indicator"] == "SP_POP_TOTL"
        assert set(results[0].keys()) == SEARCH_RESULT_KEYS

    def test_exact_code_match_is_case_insensitive(self, scoring_fixture):
        results = indicator_cache.search_local_metadata("sp_pop_totl")
        assert results[0]["relevance_score"] == 100
        # Original casing is preserved in the result, not the lowered query.
        assert results[0]["indicator"] == "SP_POP_TOTL"

    def test_code_substring_scores_90(self, scoring_fixture):
        # "ELEC" appears as a substring of code "EG_ELEC_PC" but is not the full code.
        results = indicator_cache.search_local_metadata("ELEC")
        assert len(results) == 1
        assert results[0]["indicator"] == "EG_ELEC_PC"
        assert results[0]["relevance_score"] == 90

    def test_word_in_name_scores_80(self, scoring_fixture):
        # Query "CO2" is a whole word in name "CO2 emissions (kt)" but
        # NOT in any code (codes use "EN_FUEL_KT").
        results = indicator_cache.search_local_metadata("CO2")
        assert len(results) == 1
        assert results[0]["indicator"] == "EN_FUEL_KT"
        assert results[0]["relevance_score"] == 80

    def test_substring_in_name_scores_70(self, scoring_fixture):
        # "atio" is a substring of "Population, total" (inside "popul-atio-n,")
        # but is not a whole word and not in any code.
        results = indicator_cache.search_local_metadata("atio")
        assert len(results) == 1
        assert results[0]["indicator"] == "SP_POP_TOTL"
        assert results[0]["relevance_score"] == 70

    def test_substring_in_description_scores_40(self, scoring_fixture):
        # "kilowatt" appears only in EG_ELEC_PC's description.
        results = indicator_cache.search_local_metadata("kilowatt")
        assert len(results) == 1
        assert results[0]["indicator"] == "EG_ELEC_PC"
        assert results[0]["relevance_score"] == 40

    def test_no_match_returns_empty_list(self, scoring_fixture):
        assert indicator_cache.search_local_metadata("xxxnomatchxxx") == []

    def test_results_sorted_by_score_desc(self, monkeypatch):
        fixture = [
            # Will score 90 (code substring) on query "POP"
            {"code": "SP_POP_TOTL", "name": "Population, total", "description": "", "source": "WDI"},
            # Will score 100 (exact code) on query "POP"
            {"code": "POP", "name": "Brief code record", "description": "", "source": "WDI"},
        ]
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        results = indicator_cache.search_local_metadata("POP")
        scores = [r["relevance_score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0]["relevance_score"] == 100
        assert results[1]["relevance_score"] == 90

    def test_limit_truncates_results(self, monkeypatch):
        # Build 5 records that all match at score 100 (exact code, lowered).
        fixture = [{"code": f"MATCH_{i}", "name": "", "description": "", "source": ""} for i in range(5)]
        # Trick: search by code substring "match" so all 5 match at score 90.
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        results = indicator_cache.search_local_metadata("match", limit=3)
        assert len(results) == 3

    def test_description_truncated_to_200_chars(self, monkeypatch):
        long_desc = "x" * 500
        fixture = [{"code": "C1", "name": "n", "description": long_desc, "source": "s"}]
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        results = indicator_cache.search_local_metadata("c1")
        assert len(results) == 1
        assert len(results[0]["description"]) == 200

    def test_source_truncated_to_100_chars(self, monkeypatch):
        long_source = "s" * 250
        fixture = [{"code": "C1", "name": "n", "description": "d", "source": long_source}]
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        results = indicator_cache.search_local_metadata("c1")
        assert len(results) == 1
        assert len(results[0]["source"]) == 100

    def test_empty_query_returns_empty_list(self, scoring_fixture):
        # Without the short-circuit the substring rule would match every record at score 90
        # (because `"" in code` is always True), so this is a real correctness test.
        assert indicator_cache.search_local_metadata("") == []

    def test_whitespace_query_returns_empty_list(self, scoring_fixture):
        assert indicator_cache.search_local_metadata("   ") == []
        assert indicator_cache.search_local_metadata("\t\n") == []

    def test_scoring_is_cascading_first_match_wins(self, monkeypatch):
        # Code is exactly "CO2" — query "CO2" matches the exact-code rule (100)
        # AND would also match the word-in-name rule (80) if cascade evaluation
        # did not short-circuit. We assert the higher-priority rule wins.
        fixture = [{"code": "CO2", "name": "CO2 emissions", "description": "co2", "source": "WDI"}]
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        results = indicator_cache.search_local_metadata("CO2")
        assert len(results) == 1
        assert results[0]["relevance_score"] == 100


class TestSearchLocalIndicatorsTool:
    """AC2, AC4, AC7: the MCP tool wrapper over search_local_metadata."""

    @pytest.fixture
    def scoring_fixture(self, monkeypatch):
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", SCORING_FIXTURE)
        return SCORING_FIXTURE

    @pytest.mark.asyncio
    async def test_returns_match_response_shape(self, scoring_fixture):
        result = await search_local_indicators(query="SP_POP_TOTL")
        assert set(result.keys()) == SEARCH_RESPONSE_KEYS
        assert result["success"] is True
        assert result["query"] == "SP_POP_TOTL"
        assert result["total_matches"] == 1
        assert result["note"] == MATCH_NOTE
        assert isinstance(result["data"], list)
        assert set(result["data"][0].keys()) == SEARCH_RESULT_KEYS
        # The standard contract keys must NOT be present (AC2 deviation).
        assert "total_count" not in result
        assert "returned_count" not in result
        assert "truncated" not in result

    @pytest.mark.asyncio
    async def test_no_match_returns_no_data_note(self, scoring_fixture):
        result = await search_local_indicators(query="xxxnomatchxxx")
        assert result["success"] is True
        assert result["data"] == []
        assert result["total_matches"] == 0
        assert result["note"] == NO_MATCH_NOTE

    @pytest.mark.asyncio
    async def test_empty_query_echoes_original_and_skips_scoring(self):
        with patch("mcp_server.server.indicator_cache.search_local_metadata") as spy:
            result = await search_local_indicators(query="")
        assert spy.call_count == 0
        assert result["success"] is True
        assert result["query"] == ""  # echoed verbatim
        assert result["data"] == []
        assert result["total_matches"] == 0
        assert result["note"] == NO_MATCH_NOTE

    @pytest.mark.asyncio
    async def test_whitespace_query_skips_scoring(self):
        with patch("mcp_server.server.indicator_cache.search_local_metadata") as spy:
            result = await search_local_indicators(query="   ")
        assert spy.call_count == 0
        assert result["query"] == "   "  # echoed verbatim, NOT stripped
        assert result["note"] == NO_MATCH_NOTE

    def test_limit_default_equals_config(self):
        """AC3: tool's `limit` default is bound to config.DATA360_LOCAL_SEARCH_LIMIT."""
        sig = inspect.signature(search_local_indicators)
        assert sig.parameters["limit"].default == config.DATA360_LOCAL_SEARCH_LIMIT

    @pytest.mark.asyncio
    async def test_limit_clamped_to_max_100(self, scoring_fixture):
        with patch(
            "mcp_server.server.indicator_cache.search_local_metadata",
            return_value=[],
        ) as spy:
            await search_local_indicators(query="anything", limit=999)
        spy.assert_called_once()
        assert spy.call_args.kwargs["limit"] == 100

    @pytest.mark.asyncio
    async def test_limit_clamped_to_min_1(self, scoring_fixture):
        with patch(
            "mcp_server.server.indicator_cache.search_local_metadata",
            return_value=[],
        ) as spy:
            await search_local_indicators(query="anything", limit=0)
        assert spy.call_args.kwargs["limit"] == 1

    @pytest.mark.asyncio
    async def test_negative_limit_clamped_to_1(self, scoring_fixture):
        with patch(
            "mcp_server.server.indicator_cache.search_local_metadata",
            return_value=[],
        ) as spy:
            await search_local_indicators(query="anything", limit=-5)
        assert spy.call_args.kwargs["limit"] == 1

    @pytest.mark.asyncio
    async def test_no_api_client_required(self, scoring_fixture):
        with patch("mcp_server.server._client", None):
            result = await search_local_indicators(query="SP_POP_TOTL")
        assert result["success"] is True
        assert result["total_matches"] == 1

    @pytest.mark.asyncio
    async def test_error_path_returns_api_error_type(self):
        with patch(
            "mcp_server.server.indicator_cache.search_local_metadata",
            side_effect=RuntimeError("boom"),
        ):
            result = await search_local_indicators(query="anything")
        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert result["error"] == "boom"


# ---------------------------------------------------------------------------
# Story 5.5 — real-file integration, performance, and edge-case gap-fill tests
# ---------------------------------------------------------------------------


class TestRealDataFiles:
    """AC3: validate the committed JSON files and real-file relevance scoring."""

    def test_popular_indicators_file_integrity(self):
        """AC3: popular_indicators.json has 25-30 indicators across the 7 documented categories."""
        result = indicator_cache.get_popular_indicators()
        indicators = result["indicators"]
        assert 25 <= len(indicators) <= 30
        for ind in indicators:
            assert {"category", "code", "name", "description"} <= set(ind.keys())
        categories = {ind["category"] for ind in indicators}
        expected = {
            "Climate & Environment",
            "Energy",
            "Demographics",
            "Economy",
            "Health",
            "Infrastructure",
            "Agriculture & Land Use",
        }
        assert categories == expected

    def test_metadata_indicators_file_integrity(self):
        """AC3: metadata_indicators.json has ≥1500 records with required keys and no duplicate codes."""
        records = indicator_cache.get_metadata_indicators()
        assert isinstance(records, list)
        assert len(records) >= 1500
        for rec in records:
            assert {"code", "name", "description", "source"} <= set(rec.keys())
        codes = [rec["code"] for rec in records]
        assert len(codes) == len(set(codes))  # no duplicate codes — Story 5.2 dedupe regression guard

    def test_real_file_exact_code_scores_100(self):
        """AC3: SP_POP_TOTL resolves as top hit with relevance_score 100 from the real catalog."""
        results = indicator_cache.search_local_metadata("SP_POP_TOTL")
        assert results, "SP_POP_TOTL expected in the real metadata catalog"
        assert results[0]["indicator"] == "SP_POP_TOTL"
        assert results[0]["relevance_score"] == 100


class TestOfflineSearchPerformance:
    """AC4: NFR13 (<50ms warm) / NFR14 (<500ms cold) guardrails — generous CI-safe thresholds."""

    def test_cold_load_under_budget(self):
        """NFR14: first load of metadata_indicators.json completes under 1000ms CI-safe threshold."""
        # _reset_cache has nulled the singleton; this call is the first (cold) load.
        start = time.perf_counter()
        indicator_cache.get_metadata_indicators()
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 1000  # NFR14 target is 500ms; 2x margin for CI

    def test_warm_search_under_budget(self):
        """NFR13: warm search_local_metadata completes under 250ms CI-safe threshold."""
        indicator_cache.get_metadata_indicators()  # warm the singleton first
        start = time.perf_counter()
        indicator_cache.search_local_metadata("CO2")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 250  # NFR13 target is 50ms; 5x margin for CI


class TestEdgeCases:
    """AC5: inputs not covered by the 5.3/5.4 happy-path tests."""

    @pytest.fixture
    def scoring_fixture(self, monkeypatch):
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", SCORING_FIXTURE)
        return SCORING_FIXTURE

    def test_unicode_query_matches_non_ascii_record(self, monkeypatch):
        """AC5: non-ASCII query case-folds and matches a non-ASCII record without raising."""
        fixture = [{"code": "C1", "name": "Població total", "description": "d", "source": "s"}]
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        # Lowercase query vs title-case accented name — exercises .lower() over non-ASCII,
        # not just the no-raise path. "població" must match "Població" (word-in-name, score 80).
        results = indicator_cache.search_local_metadata("població")
        assert isinstance(results, list)
        assert [r["indicator"] for r in results] == ["C1"]

    def test_very_long_query_returns_no_match(self, scoring_fixture):
        """AC5: 2000-char query returns [] cleanly without raising."""
        results = indicator_cache.search_local_metadata("x" * 2000)
        assert results == []

    def test_special_chars_treated_as_literal_not_regex(self, monkeypatch):
        """AC5: regex metacharacters are treated as literal substrings, not patterns."""
        fixture = [{"code": "C1", "name": "co2 emissions", "description": "d", "source": "s"}]
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        # "co2.*" would match "co2 emissions" as a regex; as a literal it must NOT match.
        assert indicator_cache.search_local_metadata("co2.*") == []

    def test_plus_pattern_treated_as_literal(self, monkeypatch):
        """AC5: '+' and other regex quantifiers are literal, not pattern operators."""
        fixture = [
            {"code": "C1", "name": "a+b emissions", "description": "d", "source": "s"},
            {"code": "C2", "name": "aaab emissions", "description": "d", "source": "s"},
        ]
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        # As a regex, "a+b" (one-or-more 'a' then 'b') matches "aaab" but NOT the literal "a+b".
        # A literal-substring implementation does the opposite: it matches only C1, never C2.
        # Asserting exactly [C1] proves the search is literal, not a pattern match.
        results = indicator_cache.search_local_metadata("a+b")
        assert [r["indicator"] for r in results] == ["C1"]

    def test_present_but_null_fields_do_not_raise(self, monkeypatch):
        """AC5 / 5.4 hardening: a present-but-None field must not crash (None.lower()).

        Regression guard for the ``(ind.get("k") or "")`` null-coalescing reads — a record
        whose fields are explicitly None is skipped (score 0) without raising, while valid
        records still resolve. This fails against the unguarded ``ind.get("k", "")`` form.
        """
        fixture = [
            {"code": None, "name": None, "description": None, "source": None},
            {"code": "SP_POP_TOTL", "name": "Population", "description": "People", "source": "WDI"},
        ]
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        results = indicator_cache.search_local_metadata("SP_POP_TOTL")
        assert [r["indicator"] for r in results] == ["SP_POP_TOTL"]
        assert results[0]["relevance_score"] == 100
