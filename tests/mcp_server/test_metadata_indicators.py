"""Validation tests for mcp_server/metadata_indicators.json (Story 5.2).

Tests read the file directly via json.load — no dependency on indicator_cache.py
(that module is created in Story 5.3).
"""

import json
import re
import time
from pathlib import Path

METADATA_INDICATORS_PATH = Path(__file__).parent.parent.parent / "mcp_server" / "metadata_indicators.json"

REQUIRED_FIELDS = {"code", "name", "description", "source"}

# AC2: code/name/source must be non-empty; description is allowed to be empty
# (some WDI indicators have no definition_long/definition_short).
NON_EMPTY_FIELDS = {"code", "name", "source"}

# Positive short-code shape: starts with 2+ uppercase letters, then underscore-separated segments
SHORT_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]+")


class TestMetadataIndicatorsFile:
    """AC1: ~1500 indicator records from Data360 API (WB_WDI)."""

    def test_file_exists(self) -> None:
        assert METADATA_INDICATORS_PATH.exists(), f"Missing: {METADATA_INDICATORS_PATH}"

    def test_parses_as_bare_list(self) -> None:
        """AC4: top-level structure must be a bare JSON array, not a dict."""
        with METADATA_INDICATORS_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list), (
            f"Top-level structure must be a list, got {type(data).__name__}. "
            "Do NOT wrap in a dict with an 'indicators' key — indicator_cache.py assigns "
            "_load_json() directly to list[dict]."
        )

    def test_load_time_under_500ms(self) -> None:
        """AC4: json.load completes in under 500ms (NFR14)."""
        start = time.perf_counter()
        with METADATA_INDICATORS_PATH.open(encoding="utf-8") as f:
            json.load(f)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"Load took {elapsed_ms:.1f}ms (limit 500ms)"

    def _load_indicators(self) -> list[dict]:
        with METADATA_INDICATORS_PATH.open(encoding="utf-8") as f:
            return json.load(f)

    def test_indicator_count_in_range(self) -> None:
        """AC1: ~1500 records — generous bounds allow API catalog variation."""
        indicators = self._load_indicators()
        assert indicators, "Indicator list must not be empty"
        count = len(indicators)
        assert 500 <= count <= 3000, f"Expected 500–3000 indicators, got {count}"

    def test_each_entry_has_exactly_required_fields(self) -> None:
        """AC2: every entry must have exactly code, name, description, source."""
        indicators = self._load_indicators()
        for i, entry in enumerate(indicators):
            actual = set(entry.keys())
            missing = REQUIRED_FIELDS - actual
            extra = actual - REQUIRED_FIELDS
            assert not missing, f"Entry {i} ({entry.get('code', '?')}) missing fields: {missing}"
            assert not extra, f"Entry {i} ({entry.get('code', '?')}) has extra fields: {extra}"

    def test_all_fields_are_strings(self) -> None:
        """AC2: all fields are strings; code/name/source non-empty, description may be empty."""
        indicators = self._load_indicators()
        for i, entry in enumerate(indicators):
            code_hint = entry.get("code", "?")
            for field in REQUIRED_FIELDS:
                val = entry.get(field)
                assert isinstance(val, str), f"Entry {i} ({code_hint}) field '{field}' is not a string: {val!r}"
            for field in NON_EMPTY_FIELDS:
                assert entry[field].strip(), f"Entry {i} ({code_hint}) field '{field}' is empty"

    def test_codes_are_short_codes(self) -> None:
        """AC3: codes must be short codes, not fully-qualified database IDs."""
        indicators = self._load_indicators()
        for entry in indicators:
            code = entry["code"]
            # No surrounding whitespace — breaks the downstream `{database_id}_{code}` join.
            assert code == code.strip(), f"Code '{code}' has surrounding whitespace"
            # Negative guard: must not start with a known database prefix.
            assert not code.upper().startswith("WB_"), (
                f"Code '{code}' looks like a fully-qualified ID (starts with 'WB_')"
            )
            # Positive guard: must match the short-code shape (e.g. SP_POP_TOTL).
            assert SHORT_CODE_PATTERN.fullmatch(code), f"Code '{code}' is not a well-formed short code"

    def test_no_duplicate_codes(self) -> None:
        """Each indicator code must be unique within the file."""
        indicators = self._load_indicators()
        codes = [e["code"] for e in indicators]
        seen: set[str] = set()
        duplicates: set[str] = set()
        for c in codes:
            if c in seen:
                duplicates.add(c)
            seen.add(c)
        assert not duplicates, f"Duplicate codes found: {duplicates}"
