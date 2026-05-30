# Story 5.5: Offline Indicator Search Test Suite

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want **automated tests for the offline search tools and indicator cache**,
so that **I can verify correctness and catch regressions**.

## Acceptance Criteria

1. **Given** the test suite in `tests/mcp_server/`
   **When** running `uv run pytest tests/mcp_server/test_indicator_cache.py`
   **Then** all tests pass (0 failures, 0 errors)
   **And** the broader `uv run python -m pytest tests/mcp_server` regression suite still passes with no regressions introduced by this story

2. **Given** `test_indicator_cache.py`
   **When** the suite runs
   **Then** it explicitly covers each of the following (this story AUDITS existing coverage from Stories 5.3/5.4 and FILLS any gaps — see Dev Notes → "Coverage audit map"):
   - **Relevance scoring** — exact code match = 100, code substring = 90, word-in-name = 80, substring-in-name = 70, substring-in-description = 40, no match dropped (FR38, FR39)
   - **Result ordering** — results are sorted by `relevance_score` descending (highest relevance first)
   - **Limit parameter** — at most `limit` results are returned; the tool clamps `limit` to `[1, 100]`
   - **Empty/whitespace query** — returns an empty result set / the no-match note (and never scores every record)
   - **Singleton caching** — each data file is read from disk exactly once across multiple calls (FR40); the popular and metadata singletons are independent (no cross-pollution)
   - **`list_popular_indicators`** — returns the correct structure (the standard `{success, data, total_count, returned_count, truncated}` contract, grouped by category)
   - **`search_local_indicators`** — returns the correct response format (the tool-specific `{success, query, total_matches, data, note}` contract; result items have exactly `indicator`/`name`/`description`/`source`/`relevance_score`)

3. **Given** the **real** committed data files (`mcp_server/popular_indicators.json`, `mcp_server/metadata_indicators.json`) — not just in-memory fixtures
   **When** integration-style tests run against them
   **Then** at least one well-known indicator resolves as expected through the real metadata file (e.g. `search_local_metadata("SP_POP_TOTL")[0]["relevance_score"] == 100`)
   **And** the data files satisfy their structural contracts: `popular_indicators.json` has ~25–30 indicators across the 7 documented categories with `category`/`code`/`name`/`description` on every record; `metadata_indicators.json` is a bare list of ≥1500 records each with `code`/`name`/`description`/`source`, with no duplicate codes (regression guard for the Story 5.2 dedupe fix)

4. **Given** the offline-search performance NFRs
   **When** timing tests run
   **Then** a warm call to `search_local_metadata` / `search_local_indicators` (after the singleton is loaded) completes well under the NFR13 budget (assert with a generous CI-safe threshold, recommended ≤250 ms)
   **And** the cold load of `metadata_indicators.json` (first call) completes under the NFR14 budget (assert with a generous CI-safe threshold, recommended ≤1000 ms)
   **And** these timing assertions use generous margins to avoid CI flakiness — correctness assertions are the deliverable; micro-timing is a guardrail, not a precise benchmark

5. **Given** edge-case inputs not exercised by the Story 5.3/5.4 happy-path tests
   **When** the audit gap-fill tests run
   **Then** the suite covers at least: a Unicode query, a very long query (e.g. 1000+ chars), a query containing regex/special characters (must be treated as a literal substring, not a pattern), and the offline tools functioning with no API client (`_client` patched to `None`)
   **And** any genuinely missing happy-path coverage identified in the audit map is added

6. **Given** the test file
   **When** reviewed for style
   **Then** it preserves the existing class structure and naming (`TestGetPopularIndicators`, `TestListPopularIndicatorsTool`, `TestGetMetadataIndicators`, `TestSearchLocalMetadata`, `TestSearchLocalIndicatorsTool`) and follows the file's established conventions (the `_reset_cache` autouse fixture, exact-keys assertions, `unittest.mock.patch(..., wraps=...)` for call-count spying, UTF-8 file reads)
   **And** `uv run ruff check .` and `uv run ruff format --check .` pass

## Tasks / Subtasks

- [x] Task 1: Audit existing coverage against the AC2 checklist (AC: 2)
  - [x] Read `tests/mcp_server/test_indicator_cache.py` in full and build the coverage map in Dev Notes → "Coverage audit map" (which existing test satisfies each AC2 bullet)
  - [x] Identify any AC2 bullet NOT already covered by a Story 5.3/5.4 test and list the gap
  - [x] Record the audit outcome in the Completion Notes (do NOT delete or rewrite passing Story 5.3/5.4 tests — this story extends, it does not churn)
- [x] Task 2: Add real-file integration tests (AC: 3)
  - [x] Add a test class `TestRealDataFiles` (or extend the existing classes) that exercises the **real** committed JSON files, NOT the in-memory fixtures
  - [x] `popular_indicators.json` integrity: load via `indicator_cache.get_popular_indicators()`; assert 25–30 indicators, exactly the 7 documented categories present, every record has `category`/`code`/`name`/`description`
  - [x] `metadata_indicators.json` integrity: load via `indicator_cache.get_metadata_indicators()`; assert it is a list of ≥1500 dicts, every record has `code`/`name`/`description`/`source`, and there are **no duplicate codes** (`len(codes) == len(set(codes))`) — regression guard for the Story 5.2 dedupe
  - [x] Real-file relevance: `indicator_cache.search_local_metadata("SP_POP_TOTL")` returns a non-empty list whose top hit has `relevance_score == 100` and `indicator == "SP_POP_TOTL"` (skip gracefully with a clear message if that code is ever removed from the catalog — but it is a core WDI code and expected to persist)
  - [x] All direct file reads in tests use `encoding="utf-8"` (project rule; the existing file already does this via `POPULAR_INDICATORS_PATH.open(encoding="utf-8")`)
- [x] Task 3: Add performance/NFR tests (AC: 4)
  - [x] Add a `TestOfflineSearchPerformance` class
  - [x] Cold-load test (NFR14): reset the metadata singleton, time the first `get_metadata_indicators()` (or first `search_local_metadata(...)`) call, assert under the generous threshold (≤1000 ms)
  - [x] Warm-search test (NFR13): with the singleton already loaded, time a `search_local_metadata("CO2")` call, assert under the generous threshold (≤250 ms)
  - [x] Use `time.perf_counter()`; keep thresholds generous and comment that they are CI-safe guardrails, not benchmarks
- [x] Task 4: Add edge-case gap-fill tests (AC: 5)
  - [x] Unicode query (e.g. `"població"` / a non-ASCII term) — does not raise; returns a well-formed result set
  - [x] Very long query (1000+ chars) — does not raise; returns `[]` / no-match cleanly
  - [x] Special-character query (e.g. `"co2.*"` or `"a+b"`) — treated as a literal substring, NOT a regex; assert it does not match records it would match as a pattern
  - [x] Confirm `search_local_indicators` works with `_client` patched to `None` (offline guarantee, FR37/NFR9) — extend if not already present
  - [x] Add any happy-path coverage flagged as missing in the Task 1 audit
- [x] Task 5: Quality gate (AC: 1, 6)
  - [x] `uv run python -m pytest tests/mcp_server/test_indicator_cache.py -v` passes
  - [x] `uv run python -m pytest tests/mcp_server` passes (no regressions)
  - [x] `uv run ruff check .` and `uv run ruff format --check .` pass
  - [x] Confirm the file still imports cleanly and the `_reset_cache` autouse fixture covers every new test (singleton isolation)

## Dev Notes

### Scope boundary (read first)

This is a **test-only story**. It delivers test coverage; it does **not** change production code.

**In scope — one file:**
- `tests/mcp_server/test_indicator_cache.py` — audit existing coverage, then ADD: real-file integration tests, performance/NFR tests, and edge-case gap-fill tests.

**Explicitly NOT in scope:**
- Any change to `mcp_server/indicator_cache.py`, `mcp_server/server.py`, or `mcp_server/config.py`. If the audit or a new test surfaces a **real production bug**, STOP and document it in Completion Notes + raise it — do not silently patch production code inside a test story (the 5.4 code review already hardened the null-field path; pre-existing robustness items like the lazy-singleton race and blocking I/O are deferred per `deferred-work.md`).
- Regenerating `popular_indicators.json` or `metadata_indicators.json` (Stories 5.1/5.2 own those).
- Tests for `get_temporal_coverage` (Story 6.2), MCP prompts/resources (Epic 7), or RAG.
- Do **not** delete or rewrite the existing Story 5.3/5.4 tests. They already pass and satisfy most of AC2. This story is additive.

### The key insight: most of AC2 is ALREADY covered

The dev work for Stories 5.3 and 5.4 already produced a comprehensive `test_indicator_cache.py` (the file currently has ~412 lines and the full Epic 5 suite reports 54 passing tests). So this story is primarily an **audit + targeted gap-fill**, not a from-scratch suite. The real net-new value is:
1. **Real-file integration** (existing scoring tests all use in-memory fixtures via `monkeypatch.setattr(indicator_cache, "_metadata_indicators", FIXTURE)`),
2. **NFR13/NFR14 performance guardrails** (no timing test exists yet — Story 5.3/5.4 deliberately omitted them),
3. **Edge cases** (Unicode, very long, special-char/regex-literal),
4. **Data-file structural integrity / no-duplicate-codes** regression guards.

Start by reading the file and confirming this, then add only what's missing.

### Coverage audit map (fill during Task 1)

Map each AC2 bullet to the existing test that satisfies it. Expected starting state (verify by reading the file — line numbers will drift):

| AC2 bullet | Existing test(s) | Gap? |
|---|---|---|
| Relevance scoring 100/90/80/70/40 + drop | `TestSearchLocalMetadata.test_exact_code_match_scores_100`, `test_code_substring_scores_90`, `test_word_in_name_scores_80`, `test_substring_in_name_scores_70`, `test_substring_in_description_scores_40`, `test_no_match_returns_empty_list`, `test_scoring_is_cascading_first_match_wins` | covered (fixture-only → add real-file in Task 2) |
| Result ordering desc | `TestSearchLocalMetadata.test_results_sorted_by_score_desc` | covered |
| Limit parameter + clamp | `TestSearchLocalMetadata.test_limit_truncates_results`; `TestSearchLocalIndicatorsTool.test_limit_clamped_to_max_100`, `test_limit_clamped_to_min_1`, `test_negative_limit_clamped_to_1`, `test_limit_default_equals_config` | covered |
| Empty/whitespace query | `TestSearchLocalMetadata.test_empty_query_returns_empty_list`, `test_whitespace_query_returns_empty_list`; `TestSearchLocalIndicatorsTool.test_empty_query_echoes_original_and_skips_scoring`, `test_whitespace_query_skips_scoring` | covered |
| Singleton caching + independence | `TestGetPopularIndicators.test_singleton_caches_after_first_load`; `TestGetMetadataIndicators.test_singleton_caches_after_first_load`, `test_metadata_and_popular_caches_are_independent` | covered |
| `list_popular_indicators` structure | `TestListPopularIndicatorsTool.test_returns_success_contract`, `test_data_grouped_by_category`, `test_counts_reflect_indicators_not_groups`, `test_categories_match_source_file` | covered |
| `search_local_indicators` response format | `TestSearchLocalIndicatorsTool.test_returns_match_response_shape`, `test_no_match_returns_no_data_note` | covered |

If every row is "covered", AC2 is satisfied by audit alone and your net-new work is Tasks 2–4. Record the final, verified map in Completion Notes.

### Current state of `tests/mcp_server/test_indicator_cache.py`

Established conventions you MUST follow (do not introduce a different style):

- **Imports** (top of file): `import inspect`, `import json`, `from pathlib import Path`, `from unittest.mock import patch`, `import pytest`, then `import mcp_server.config as config`, `import mcp_server.indicator_cache as indicator_cache`, `from mcp_server.server import list_popular_indicators, search_local_indicators`. Add `import time` for the perf tests.
- **Path constants:** `POPULAR_INDICATORS_PATH` and `METADATA_INDICATORS_PATH` are already defined (`Path(__file__).parent.parent.parent / "mcp_server" / "<file>.json"`). Reuse them; do not recompute paths.
- **Key-set constants:** `RESPONSE_KEYS = {"success", "data", "total_count", "returned_count", "truncated"}`, `INDICATOR_KEYS = {"code", "name", "description"}`, `SEARCH_RESPONSE_KEYS = {"success", "query", "total_matches", "data", "note"}`, `SEARCH_RESULT_KEYS = {"indicator", "name", "description", "source", "relevance_score"}`, `NO_MATCH_NOTE`, `MATCH_NOTE`. Reuse these in new assertions.
- **`_reset_cache` autouse fixture** resets BOTH `indicator_cache._popular_indicators` and `indicator_cache._metadata_indicators` to `None` before and after each test. This is what lets your cold-load timing test and real-file tests run in isolation — do NOT bypass it.
- **Async tool tests** use `@pytest.mark.asyncio` (the repo sets `asyncio_mode = "auto"`, so it's redundant, but match the file's style) and `await` the tool directly: `await search_local_indicators(query=...)`.
- **Fixture-based scoring** uses `monkeypatch.setattr(indicator_cache, "_metadata_indicators", FIXTURE)` to bypass file I/O. There is a module-level `SCORING_FIXTURE` list (3 records: `SP_POP_TOTL`, `EN_FUEL_KT`, `EG_ELEC_PC`) crafted so codes don't accidentally collide with the name/description test queries. Reuse it where helpful, but Task 2 tests must hit the REAL files (don't monkeypatch the singleton there — let the loader read disk).
- **Spying for call counts:** `with patch("mcp_server.indicator_cache._load_json", wraps=indicator_cache._load_json) as spy: ...; assert spy.call_count == 1`.
- **Error-path idiom:** `with patch("mcp_server.server.indicator_cache.search_local_metadata", side_effect=RuntimeError("boom")): ...` then assert `{"success": False, "error_type": "api_error"}`.

### Production code under test (for reference — do not modify)

`mcp_server/indicator_cache.py` public surface:
- `get_popular_indicators() -> dict[str, Any]` → `{"indicators": [...], "total": N}`. Loads `popular_indicators.json` once (dict-wrapped under `"indicators"`, unwrapped via `data.get("indicators", data)`).
- `get_metadata_indicators() -> list[dict[str, Any]]` → bare list. Loads `metadata_indicators.json` once (assigned directly, NO `.get` unwrap — it's a bare JSON array).
- `search_local_metadata(query, limit=20) -> list[dict]` → cascading first-match-wins scoring (100/90/80/70/40); empty/whitespace query short-circuits to `[]`; fields read with `(ind.get("k") or "")` null-coalescing (5.4 review hardening); results sorted by score desc; sliced to `limit`. Result keys: `indicator`, `name`, `description` (≤200), `source` (≤100), `relevance_score`.

`mcp_server/server.py` tools (both already imported in the test file):
- `list_popular_indicators()` → standard `{success, data, total_count, returned_count, truncated}` contract, `data` grouped by category.
- `search_local_indicators(query, limit=config.DATA360_LOCAL_SEARCH_LIMIT)` → `{success, query, total_matches, data, note}`; empty-query short-circuit; `limit` clamped to `[1, 100]`; `except Exception` → `{success: False, error, error_type: "api_error"}`.

### Real-file integration tests (Task 2) — patterns

Do NOT monkeypatch the singleton in these — exercise the loader against disk so the real file content is validated. The `_reset_cache` fixture guarantees a clean singleton per test.

```python
class TestRealDataFiles:
    """AC3: validate the committed JSON files and real-file relevance scoring."""

    def test_popular_indicators_file_integrity(self):
        result = indicator_cache.get_popular_indicators()
        indicators = result["indicators"]
        assert 25 <= len(indicators) <= 30
        for ind in indicators:
            assert {"category", "code", "name", "description"} <= set(ind.keys())
        categories = {ind["category"] for ind in indicators}
        expected = {
            "Climate & Environment", "Energy", "Demographics", "Economy",
            "Health", "Infrastructure", "Agriculture & Land Use",
        }
        assert categories == expected

    def test_metadata_indicators_file_integrity(self):
        records = indicator_cache.get_metadata_indicators()
        assert isinstance(records, list)
        assert len(records) >= 1500
        for rec in records:
            assert {"code", "name", "description", "source"} <= set(rec.keys())
        codes = [rec["code"] for rec in records]
        assert len(codes) == len(set(codes))  # no duplicate codes (5.2 dedupe guard)

    def test_real_file_exact_code_scores_100(self):
        results = indicator_cache.search_local_metadata("SP_POP_TOTL")
        assert results, "SP_POP_TOTL expected in the real metadata catalog"
        assert results[0]["indicator"] == "SP_POP_TOTL"
        assert results[0]["relevance_score"] == 100
```

Note `<= set(ind.keys())` (subset) rather than `==` for the real records, because the real files may carry extra fields beyond the documented minimum. Use exact `==` only for the response-contract keys (those are MCP-controlled and fixed).

### Performance tests (Task 3) — patterns

```python
import time

class TestOfflineSearchPerformance:
    """AC4: NFR13 (<50ms warm) / NFR14 (<500ms cold) guardrails — generous CI-safe thresholds."""

    def test_cold_load_under_budget(self):
        # _reset_cache nulled the singleton; this is the first (cold) load.
        start = time.perf_counter()
        indicator_cache.get_metadata_indicators()
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 1000  # NFR14 is 500ms; generous CI margin

    def test_warm_search_under_budget(self):
        indicator_cache.get_metadata_indicators()  # warm the singleton
        start = time.perf_counter()
        indicator_cache.search_local_metadata("CO2")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 250  # NFR13 is 50ms; generous CI margin
```

Keep the thresholds generous and comment them as CI-safe guardrails. The point is to catch an order-of-magnitude regression (e.g. accidental per-call file reads), not to benchmark.

### Edge-case tests (Task 4) — patterns

Use the in-memory fixture for deterministic special-char assertions; use the real file (or fixture) for Unicode/long-query smoke checks.

```python
class TestEdgeCases:
    """AC5: inputs not covered by the 5.3/5.4 happy-path tests."""

    @pytest.fixture
    def scoring_fixture(self, monkeypatch):
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", SCORING_FIXTURE)
        return SCORING_FIXTURE

    def test_unicode_query_does_not_raise(self, scoring_fixture):
        # Must not raise; returns a well-formed (possibly empty) list.
        results = indicator_cache.search_local_metadata("població")
        assert isinstance(results, list)

    def test_very_long_query_returns_no_match(self, scoring_fixture):
        results = indicator_cache.search_local_metadata("x" * 2000)
        assert results == []

    def test_special_chars_treated_as_literal_not_regex(self, monkeypatch):
        fixture = [{"code": "C1", "name": "co2 emissions", "description": "d", "source": "s"}]
        monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
        # "co2.*" would match "co2 emissions" if treated as a regex; as a literal
        # substring it must NOT match.
        assert indicator_cache.search_local_metadata("co2.*") == []
```

### Testing standards (project-context / architecture)

- Tests live in `tests/mcp_server/` mirroring source; ONE file per source module — extend `test_indicator_cache.py`, do not create a parallel file.
- `asyncio_mode = "auto"` is set in `pyproject.toml`. Match the file's `@pytest.mark.asyncio` usage on async tests.
- Python 3.12 style: `X | None`, `dict[str, Any]`, type hints, double quotes, line length 120.
- Group tests in classes with AC-referencing docstrings.
- Direct file reads in tests must pass `encoding="utf-8"` (the #1 repeated review finding across Epic 5).
- Architecture boundary: `indicator_cache.py` is the only module that reads the JSON files; tests should generally go through `indicator_cache.*` rather than re-reading files themselves. Where a test reads a file directly (e.g. to cross-check the source against the loader), it's acceptable as a test-only cross-check — but prefer the loader.

### Previous-story learnings (Epic 5 code reviews)

- **UTF-8 everywhere** — always pass `encoding="utf-8"` when opening files in tests.
- **Exact-keys assertions** — for MCP response/result contracts use `set(x.keys()) == EXPECTED`; for real data records use subset (`EXPECTED <= set(...)`) so extra real-world fields don't fail the test.
- **No-data-found is explicit** — the offline tools surface empties via the `note` field; assert the exact note strings (`NO_MATCH_NOTE`, `MATCH_NOTE`).
- **Timing tests are guardrails, not benchmarks** — Stories 5.3/5.4 omitted them; this story adds them with generous margins precisely so they don't flake on a loaded CI host.
- **Don't churn passing tests** — extend, don't rewrite. The reviewer should see additive diffs.
- **`metadata_indicators.json` is a bare list of 1516 records** (after the Story 5.2 dedupe that removed 17 duplicate idnos). Assert `>= 1500` (not an exact count) so a future regeneration with a slightly different count doesn't break the suite, but DO assert no-duplicate-codes.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.5] — Story statement and ACs: run `tests/mcp_server/test_indicator_cache.py` all pass; tests cover relevance scoring (100/90/80/...), result ordering, limit, empty query, singleton caching, `list_popular_indicators` structure, `search_local_indicators` response format
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5] — Epic goal (instant offline indicator discovery, resilience when API slow/unavailable); FR37–FR40; NFR13 (offline search <50ms), NFR14 (startup load <500ms)
- [Source: tests/mcp_server/test_indicator_cache.py] — Existing Story 5.3/5.4 tests (classes `TestGetPopularIndicators`, `TestListPopularIndicatorsTool`, `TestGetMetadataIndicators`, `TestSearchLocalMetadata`, `TestSearchLocalIndicatorsTool`), `_reset_cache` autouse fixture (resets both singletons), key-set constants, `SCORING_FIXTURE`, `patch(..., wraps=...)` spy idiom, error-path idiom
- [Source: mcp_server/indicator_cache.py] — Functions under test: `get_popular_indicators`, `get_metadata_indicators`, `search_local_metadata`; cascading scoring; null-coalescing field reads; bare-list metadata loader
- [Source: mcp_server/server.py] — Tools under test: `list_popular_indicators` (standard contract, grouped by category), `search_local_indicators` (tool-specific contract, limit clamp, error contract)
- [Source: _bmad-output/implementation-artifacts/5-4-search-local-indicators-mcp-tool.md#Cross-story contract] — Explicit guidance for this story: add a real-file relevance test (`SP_POP_TOTL` → 100), add a generous-threshold timing test (NFR13/NFR14), audit edge cases (Unicode, long queries), keep the existing test class structure intact
- [Source: _bmad-output/implementation-artifacts/5-2-metadata-indicators-data-file.md] — `metadata_indicators.json` is a bare list; the Story 5.2 dedupe (`seen_codes`) brought the count to 1516 (from 1533 with dups) — the no-duplicate-codes test guards this
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — Pre-existing `indicator_cache.py` robustness items (lazy-singleton race, blocking I/O in async, no defensive copy) are explicitly deferred — do NOT fix them in this test story; if a test would expose one, document it rather than patching production code

## Dev Agent Record

### Agent Model Used

- claude-sonnet-4-6

### Debug Log References

- None — straightforward additive test story; no production code changed.

### Completion Notes List

- **Task 1 — Coverage audit:** All 7 AC2 bullets were already covered by the 35-test Story 5.3/5.4 suite. No existing test was deleted or rewritten.

  | AC2 bullet | Existing test(s) | Gap? |
  |---|---|---|
  | Relevance scoring 100/90/80/70/40 + drop | `test_exact_code_match_scores_100`, `test_code_substring_scores_90`, `test_word_in_name_scores_80`, `test_substring_in_name_scores_70`, `test_substring_in_description_scores_40`, `test_no_match_returns_empty_list`, `test_scoring_is_cascading_first_match_wins` | covered |
  | Result ordering desc | `test_results_sorted_by_score_desc` | covered |
  | Limit parameter + clamp | `test_limit_truncates_results`; `test_limit_clamped_to_max_100`, `test_limit_clamped_to_min_1`, `test_negative_limit_clamped_to_1`, `test_limit_default_equals_config` | covered |
  | Empty/whitespace query | `test_empty_query_returns_empty_list`, `test_whitespace_query_returns_empty_list`; `test_empty_query_echoes_original_and_skips_scoring`, `test_whitespace_query_skips_scoring` | covered |
  | Singleton caching + independence | `test_singleton_caches_after_first_load` (×2) + `test_metadata_and_popular_caches_are_independent` | covered |
  | `list_popular_indicators` structure | `test_returns_success_contract`, `test_data_grouped_by_category`, `test_counts_reflect_indicators_not_groups`, `test_categories_match_source_file` | covered |
  | `search_local_indicators` response format | `test_returns_match_response_shape`, `test_no_match_returns_no_data_note` | covered |

- **Task 2 — Real-file integration (3 new tests in `TestRealDataFiles`):**
  - `test_popular_indicators_file_integrity`: 28 indicators, exactly the 7 documented categories, all required fields present.
  - `test_metadata_indicators_file_integrity`: 1516 records ≥ 1500, all 4 required fields, 0 duplicate codes (regression guard for 5.2 dedupe).
  - `test_real_file_exact_code_scores_100`: SP_POP_TOTL top hit scores 100 against the real catalog.

- **Task 3 — Performance/NFR (2 new tests in `TestOfflineSearchPerformance`):**
  - Cold load finished in ~7 s total test run; individual assert < 1000 ms passed comfortably.
  - Warm search assert < 250 ms passed well within margin.

- **Task 4 — Edge cases (4 new tests in `TestEdgeCases`):**
  - Unicode (`"població"`), very long (2000 chars), `co2.*` regex literal, `a+b` plus-literal — all pass.
  - `search_local_indicators` offline (no `_client`) coverage was already present in `TestSearchLocalIndicatorsTool.test_no_api_client_required`; not duplicated.

- **No production bugs found.** The pre-existing deferred items (lazy-singleton race, blocking I/O in async, no defensive copy) were not triggered by any new test and remain deferred per `deferred-work.md`.

- **Final count:** 44 tests in `test_indicator_cache.py`; 202/202 total `tests/mcp_server` pass; ruff clean.
- **Post code-review (2026-05-31):** 3 review patches applied to `test_indicator_cache.py` (added null-field regression guard; strengthened the unicode and plus-pattern literal tests). Count: 44 → 45; 203/203 total `tests/mcp_server` pass; ruff clean. The null-coalesce hardening in `indicator_cache.py` was the lost 5.4 fix — committed separately under `fix(5-4)`, so this story remains test-only.

### File List

- tests/mcp_server/test_indicator_cache.py

### Change Log

- Added `import time` to imports; added `TestRealDataFiles` (3 tests, AC3), `TestOfflineSearchPerformance` (2 tests, AC4), `TestEdgeCases` (4 tests, AC5) to `test_indicator_cache.py`. Test count: 35 → 44. No production code changed. (Date: 2026-05-31)

## Review Findings

_Code review 2026-05-31 (Blind Hunter + Edge Case Hunter + Acceptance Auditor). 1 decision-needed, 3 patch, 6 dismissed as noise._

- [x] [Review][Decision] RESOLVED (option 1: split commits) — Commit `indicator_cache.py` separately under a `fix(5-4)` restoring the lost hardening + correct 5.4's record; commit the 5.5 test file on its own; 5.5 stays genuinely test-only. — Uncommitted 5.4 hardening present in a TEST-ONLY story — The working tree edits `mcp_server/indicator_cache.py:69-99` (six field reads `ind.get("k", "")` → `(ind.get("k") or "")`). HEAD (`3ad1e98`, story 5.4) still has the **unguarded** form — verified via `git show HEAD:mcp_server/indicator_cache.py`. So this is the 5.4 review's null-coalesce fix (marked `[x] FIXED` in `5-4-...md:659`) that was **never committed**, not net-new 5.5 work. Consequence: (a) 5.5's Scope Boundary ("any change to `indicator_cache.py` NOT in scope"), File List ("only the test file"), and Dev Agent Record / Change Log ("No production code changed") are all inaccurate vs the working tree; (b) the 5.4 traceability record claims a fix that isn't in history. Needs Felipe's call on how to reconcile commit + records.

- [x] [Review][Patch] APPLIED — Added `test_present_but_null_fields_do_not_raise`, a regression guard for the `or ""` hardening [tests/mcp_server/test_indicator_cache.py] — feeds a record with `{"code": None, "name": None, ...}`; the all-null record is skipped (score 0) without raising while a valid record still resolves. **Verified it fails against unguarded HEAD** (`AttributeError: 'NoneType' object has no attribute 'lower'`) and passes with the hardening. The hardening is committed separately under `fix(5-4)` per the decision above, so 5.5 stays test-only.
- [x] [Review][Patch] APPLIED — Corrected `test_plus_pattern_treated_as_literal` [tests/mcp_server/test_indicator_cache.py] — added an `"aaab emissions"` record (which a regex `a+b` matches but a literal does not) and now assert exactly `[C1]`, so the regex-vs-literal distinction is proven explicitly instead of passing by accident; comment rewritten to match.
- [x] [Review][Patch] APPLIED — Strengthened the unicode test (now `test_unicode_query_matches_non_ascii_record`) [tests/mcp_server/test_indicator_cache.py] — uses a fixture record named `"Població total"` and asserts `"població"` matches it, exercising non-ASCII `.lower()` case-folding rather than the previous near-vacuous `isinstance(results, list)` over an all-ASCII fixture.
