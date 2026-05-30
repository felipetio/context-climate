"""Validation tests for mcp_server/popular_indicators.json (Story 5.1).

Tests read the file directly via json.load — no dependency on indicator_cache.py
(that module is created in Story 5.3).
"""

import json
import re
import time
from pathlib import Path

POPULAR_INDICATORS_PATH = Path(__file__).parent.parent.parent / "mcp_server" / "popular_indicators.json"

EXPECTED_CATEGORIES = {
    "Climate & Environment",
    "Energy",
    "Demographics",
    "Economy",
    "Health",
    "Infrastructure",
    "Agriculture & Land Use",
}

CLIMATE_CATEGORIES = {"Climate & Environment", "Energy", "Agriculture & Land Use"}

REQUIRED_FIELDS = {"category", "code", "name", "description"}

# Known database prefixes that must NOT appear in a short code
DB_PREFIXES = ("WB_WDI_", "WB_", "WDI_")

# Positive short-code shape: two-letter topic prefix + uppercase/digit segments
SHORT_CODE_PATTERN = re.compile(r"[A-Z]{2}_[A-Z0-9_]+")


class TestPopularIndicatorsFile:
    """AC1/AC6: file exists, parses cleanly, and loads fast."""

    def test_file_exists(self) -> None:
        assert POPULAR_INDICATORS_PATH.exists(), f"Missing: {POPULAR_INDICATORS_PATH}"

    def test_parses_without_error(self) -> None:
        with POPULAR_INDICATORS_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict), "Top-level structure must be a dict"
        assert "indicators" in data, "Top-level dict must have an 'indicators' key"
        assert isinstance(data["indicators"], list), "'indicators' value must be a list"

    def test_load_time_under_100ms(self) -> None:
        """AC6: json.load completes in under 100ms."""
        start = time.perf_counter()
        with POPULAR_INDICATORS_PATH.open(encoding="utf-8") as f:
            json.load(f)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 100, f"Load took {elapsed_ms:.1f}ms (limit 100ms)"

    def _load_indicators(self) -> list[dict]:
        with POPULAR_INDICATORS_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data["indicators"]

    def test_indicator_count_in_range(self) -> None:
        """AC1: ~25-30 indicators (generous bounds: 20–35)."""
        indicators = self._load_indicators()
        count = len(indicators)
        assert 20 <= count <= 35, f"Expected 20–35 indicators, got {count}"

    def test_all_seven_categories_present(self) -> None:
        """AC1: all 7 categories must appear."""
        indicators = self._load_indicators()
        found = {entry["category"] for entry in indicators}
        missing = EXPECTED_CATEGORIES - found
        assert not missing, f"Missing categories: {missing}"

    def test_no_unexpected_categories(self) -> None:
        """AC1: every category must be one of the 7 expected ones."""
        indicators = self._load_indicators()
        found = {entry["category"] for entry in indicators}
        unexpected = found - EXPECTED_CATEGORIES
        assert not unexpected, f"Unexpected categories: {unexpected}"

    def test_each_entry_has_exactly_required_fields(self) -> None:
        """AC2: every entry must have exactly category, code, name, description."""
        indicators = self._load_indicators()
        for i, entry in enumerate(indicators):
            actual = set(entry.keys())
            missing = REQUIRED_FIELDS - actual
            extra = actual - REQUIRED_FIELDS
            assert not missing, f"Entry {i} ({entry.get('code', '?')}) missing fields: {missing}"
            assert not extra, f"Entry {i} ({entry.get('code', '?')}) has extra fields: {extra}"

    def test_all_fields_are_non_empty_strings(self) -> None:
        """AC2: all field values must be non-empty strings."""
        indicators = self._load_indicators()
        for i, entry in enumerate(indicators):
            for field in REQUIRED_FIELDS:
                val = entry.get(field)
                assert isinstance(val, str), f"Entry {i} field '{field}' is not a string: {val!r}"
                assert val.strip(), f"Entry {i} field '{field}' is empty"

    def test_codes_are_short_codes(self) -> None:
        """AC4: codes must be short codes, not fully-qualified database IDs."""
        indicators = self._load_indicators()
        for entry in indicators:
            code = entry["code"]
            # No surrounding whitespace — it would break the downstream `{database}_{code}` join.
            assert code == code.strip(), f"Code '{code}' has surrounding whitespace"
            # Negative guard: reject known database prefixes, case-insensitively.
            for prefix in DB_PREFIXES:
                assert not code.upper().startswith(prefix), (
                    f"Code '{code}' looks like a fully-qualified ID (starts with '{prefix}')"
                )
            # Positive guard: must match the short-code shape (e.g. EN_ATM_CO2E_KT).
            assert SHORT_CODE_PATTERN.fullmatch(code), f"Code '{code}' is not a well-formed short code"

    def test_no_duplicate_codes(self) -> None:
        """Each indicator code must be unique."""
        indicators = self._load_indicators()
        codes = [e["code"] for e in indicators]
        duplicates = {c for c in codes if codes.count(c) > 1}
        assert not duplicates, f"Duplicate codes found: {duplicates}"

    def test_climate_weighting_threshold(self) -> None:
        """AC3: Climate & Environment + Energy + Agriculture & Land Use ≥ 40% of total."""
        indicators = self._load_indicators()
        total = len(indicators)
        climate_count = sum(1 for e in indicators if e["category"] in CLIMATE_CATEGORIES)
        ratio = climate_count / total
        assert ratio >= 0.40, f"Climate-weighted categories are {climate_count}/{total} = {ratio:.0%} (need ≥ 40%)"
