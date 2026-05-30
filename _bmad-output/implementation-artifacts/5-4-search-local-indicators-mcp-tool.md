# Story 5.4: search_local_indicators MCP Tool

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user querying World Bank data,
I want to search indicator metadata offline with instant results,
so that I can quickly find relevant indicators before making API calls.

## Acceptance Criteria

1. **Given** the MCP server is running
   **When** a user calls `search_local_indicators(query="CO2 emissions")`
   **Then** the tool searches the local metadata cache (`mcp_server/metadata_indicators.json`, 1533 records) using a **cascading, first-match-wins relevance score** (FR38):
   - Exact code match (case-insensitive equality of full code): **100**
   - Code substring (case-insensitive `query in code`): **90**
   - Word in indicator name (any whitespace-split query word equals any whitespace-split name word, lowercase): **80**
   - Substring in indicator name (`query in name`, lowercase): **70**
   - Substring in description (`query in description`, lowercase): **40**
   - No match: **0** (record dropped from results)
   **And** scoring is evaluated top-down — the first rule that matches assigns the score and no later rule overrides it
   **And** the search is fully offline — no call is made to the Data360 API (the tool never references `_client`)

2. **Given** a successful search with matches
   **When** the response is inspected
   **Then** it follows this exact shape:
   ```json
   {
     "success": true,
     "query": "<echoed query string>",
     "total_matches": <int, count after limit applied>,
     "data": [<result objects, sorted by relevance_score desc>],
     "note": "Local search - instant results from cached metadata"
   }
   ```
   **And** each result object has exactly these five keys: `indicator`, `name`, `description`, `source`, `relevance_score`
   **And** `description` is truncated to 200 chars max, `source` is truncated to 100 chars max
   **And** results are sorted by `relevance_score` descending (FR39); ties are broken by encounter order in the source file (Python `list.sort` is stable)
   **And** this response shape is an **intentional, AC-driven deviation** from the standard tool contract (`{success, data, total_count, returned_count, truncated}`) — it does NOT include those keys

3. **Given** `search_local_indicators(query="xyz", limit=5)`
   **When** more than 5 results match
   **Then** only the top 5 results by relevance score are returned and `total_matches` equals 5 (the count of *returned* results, after truncation)
   **And** the default `limit` is sourced from `config.DATA360_LOCAL_SEARCH_LIMIT` (default 20, env-overridable via `DATA360_LOCAL_SEARCH_LIMIT`)
   **And** the tool clamps the caller-supplied `limit` to the range `[1, 100]` defensively (out-of-range values are coerced to the nearest bound, not rejected)

4. **Given** a search with no matches (e.g. `search_local_indicators(query="xyz123nomatch")`) **or** an empty/whitespace-only query
   **When** the tool runs
   **Then** it returns:
   ```json
   {
     "success": true,
     "query": "<echoed query>",
     "total_matches": 0,
     "data": [],
     "note": "No local matches found. Try search_indicators for API-based search."
   }
   ```
   **And** the tool logs the no-match event at INFO level (e.g. `logger.info("search_local_indicators: no matches for query=%r", query)`) so empty results are surfaced explicitly (project-context rule: "No data found must be explicit, never silently empty")
   **And** an empty/whitespace-only query short-circuits **before** the scoring loop (i.e. it does not run scoring with `query_lower == ""`, which would otherwise match every record at score 90 via the substring rule)

5. **Given** the metadata file has not been loaded yet
   **When** `search_local_indicators()` is called for the first time
   **Then** `mcp_server/metadata_indicators.json` is read from disk **once** via `indicator_cache._load_json` and cached in a new module-level singleton `indicator_cache._metadata_indicators: list[dict[str, Any]] | None` (FR40)
   **And** subsequent calls reuse the cached list without re-reading the file
   **And** the existing `_popular_indicators` singleton from Story 5.3 is untouched and continues to function (no regression)

6. **Given** any successful call
   **When** timed
   **Then** the response is returned in well under 50ms after the first load (NFR13) — trivially satisfied because the data is in memory after the first load and scoring is an O(n) pass over ≤3000 records with cheap string operations
   **And** the cold-load cost (first call only) is under 500ms (NFR14, inherited from Story 5.2's file-size budget; the 1533-record file is ~1.7 MB)
   **And** any *automated* timing assertion uses a generous budget (recommended ≥250ms warm, ≥1000ms cold) to avoid CI flakiness — correctness assertions are mandatory; micro-timing is optional and bounded

7. **Given** an unexpected error in the scoring loop, in the loader, or anywhere inside the tool body (e.g. metadata file missing, malformed, or non-list)
   **When** the tool runs
   **Then** it returns the standard error contract `{"success": False, "error": <str>, "error_type": "api_error"}` and logs the error via `logger.error("search_local_indicators failed: %s", exc)` (matching the pattern used by every existing tool in `server.py`)

## Tasks / Subtasks

- [ ] Task 1: Extend `mcp_server/indicator_cache.py` with metadata loader + relevance search (AC: 1, 5, 7)
  - [ ] Add a second module-level singleton: `_metadata_indicators: list[dict[str, Any]] | None = None` (alongside the existing `_popular_indicators`)
  - [ ] Implement `get_metadata_indicators() -> list[dict[str, Any]]`:
    - [ ] On first call only, call `_load_json("metadata_indicators.json")` and assign the result **directly** to `_metadata_indicators` — **DO NOT** add a `.get("indicators", data)` unwrap (the metadata file is a bare list, unlike `popular_indicators.json` which is dict-wrapped under `"indicators"`)
    - [ ] `logger.info("Loaded %d metadata indicators", len(_metadata_indicators))` on first load
    - [ ] Return `_metadata_indicators`
  - [ ] Implement `search_local_metadata(query: str, limit: int = 20) -> list[dict[str, Any]]`:
    - [ ] If `query` is empty after `.strip()`, return `[]` immediately (no scoring; empty/whitespace query short-circuits)
    - [ ] Call `get_metadata_indicators()` to materialise the cached list
    - [ ] For each record, compute `score` using the cascading `if/elif` chain in the order from AC1 (exact code → code substring → word in name → name substring → description substring). Use the **exact** algorithm from the architecture addendum (see Dev Notes → "Scoring algorithm" for the canonical implementation)
    - [ ] Skip records with `score == 0` (do not include them in results)
    - [ ] Build result dicts with **exactly** these keys: `indicator` (= record's `code`), `name`, `description` (truncated to 200 chars), `source` (truncated to 100 chars), `relevance_score`
    - [ ] Sort results by `relevance_score` descending (stable sort preserves file order on ties)
    - [ ] Slice to `[:limit]` and return
  - [ ] Reuse the existing `_load_json` helper — DO NOT redefine it; it already opens files with `encoding="utf-8"` (Story 5.3 contract)
- [ ] Task 2: Add `DATA360_LOCAL_SEARCH_LIMIT` to `mcp_server/config.py` (AC: 3)
  - [ ] Add `DATA360_LOCAL_SEARCH_LIMIT: int = _int_env("DATA360_LOCAL_SEARCH_LIMIT", 20, min_val=1)` near the other `_int_env` settings (e.g. after `MAX_RETRIES` or with the pagination block)
  - [ ] No other config changes — do **not** add a `DATA360_LOCAL_SEARCH_MAX` cap; the in-tool clamp at `[1, 100]` is enough
- [ ] Task 3: Add the `search_local_indicators` MCP tool to `mcp_server/server.py` (AC: 1, 2, 3, 4, 7)
  - [ ] No new imports needed — `indicator_cache` is already imported (Story 5.3) and `config` is already imported. The tool uses `config.DATA360_LOCAL_SEARCH_LIMIT` as the default for `limit`
  - [ ] Place the new tool **immediately after** `list_popular_indicators` and **before** the `if config.RAG_ENABLED:` block (~line 290). Keep registration **unconditional** (not behind `RAG_ENABLED`)
  - [ ] Function signature:
    ```python
    @mcp.tool()
    async def search_local_indicators(
        query: str,
        limit: int = config.DATA360_LOCAL_SEARCH_LIMIT,
    ) -> dict[str, Any]:
    ```
    The `config.DATA360_LOCAL_SEARCH_LIMIT` default is bound at module import time — exactly what FastMCP expects, and lets ops change the default via env without code change
  - [ ] Use the docstring from the architecture addendum (see Dev Notes → "Tool signature & docstring" for the verbatim string)
  - [ ] Body sequence (wrap in `try/except`):
    1. Clamp `limit`: `limit = max(1, min(int(limit), 100))` (handles non-int via the `int()` cast — TypeError would bubble to the outer except)
    2. Check `if not query or not query.strip():` — return the no-match response with `data=[]`, `total_matches=0`, the explicit no-match note, and log at INFO. Echo the **original** `query` (do not strip) in the response so the caller sees what they sent
    3. Call `results = indicator_cache.search_local_metadata(query, limit=limit)`
    4. If `len(results) == 0`: log at INFO `"search_local_indicators: no matches for query=%r"`, return the no-match-note response
    5. Else return the matches response: `{"success": True, "query": query, "total_matches": len(results), "data": results, "note": "Local search - instant results from cached metadata"}`
  - [ ] `except Exception as exc:` → `logger.error("search_local_indicators failed: %s", exc)` and return `{"success": False, "error": str(exc), "error_type": "api_error"}`
- [ ] Task 4: Extend `tests/mcp_server/test_indicator_cache.py` with test classes for the new functionality (AC: 1, 2, 3, 4, 5, 7)
  - [ ] **Update the existing `_reset_cache` fixture** to also reset `_metadata_indicators` (currently only resets `_popular_indicators`). Both before and after each test:
    ```python
    @pytest.fixture(autouse=True)
    def _reset_cache():
        indicator_cache._popular_indicators = None
        indicator_cache._metadata_indicators = None
        yield
        indicator_cache._popular_indicators = None
        indicator_cache._metadata_indicators = None
    ```
  - [ ] Add `class TestGetMetadataIndicators:` (AC5): covers the loader and singleton caching
    - [ ] Returns a `list[dict]` with length matching the file (≥500)
    - [ ] Singleton: patch/spy `indicator_cache._load_json` (using `wraps=indicator_cache._load_json` like Story 5.3 did) and assert `spy.call_count == 1` across two consecutive `get_metadata_indicators()` calls
    - [ ] **Independence from the popular cache:** call `get_metadata_indicators()` and `get_popular_indicators()` in the same test; assert both succeed and neither pollutes the other's singleton (regression guard for Task 1)
  - [ ] Add `class TestSearchLocalMetadata:` (AC1, AC3): covers the pure scoring function
    - [ ] Use a **small in-memory fixture list** patched into `_metadata_indicators` (do NOT exercise the real 1533-record file here — that file's contents drift over time). Example fixture:
      ```python
      FIXTURE = [
          {"code": "SP_POP_TOTL", "name": "Population, total", "description": "Total population...", "source": "WDI"},
          {"code": "EN_ATM_CO2E_KT", "name": "CO2 emissions (kt)", "description": "Carbon dioxide emissions from fuel combustion.", "source": "WDI"},
          {"code": "EG_USE_ELEC_KH_PC", "name": "Electric power consumption", "description": "kWh per capita.", "source": "WDI"},
      ]
      ```
      Set `indicator_cache._metadata_indicators = FIXTURE` directly in the test (or fixture) and bypass file I/O
    - [ ] `test_exact_code_match_scores_100`: `query="SP_POP_TOTL"` → top result has `relevance_score == 100`
    - [ ] `test_code_substring_scores_90`: `query="POP"` → matches `SP_POP_TOTL` with score 90 (substring of code, not exact match)
    - [ ] `test_word_in_name_scores_80`: `query="CO2"` → matches `EN_ATM_CO2E_KT` (whose name "CO2 emissions (kt)" splits to include the word "co2") with score 80. Counter-fixture: ensure the same query does **not** match a record whose name has "co2e" but not "co2" as a whitespace-separated word (e.g. add a record `{"code": "X_X", "name": "CO2e per capita", ...}` — depending on whether the dev splits on whitespace alone or also strips punctuation, this is a sharp edge: the canonical implementation in the architecture addendum uses `.split()` which splits on whitespace only, leaving punctuation attached. Document the chosen behavior in the test)
    - [ ] `test_substring_in_name_scores_70`: `query="population, t"` → matches `SP_POP_TOTL` (name "Population, total" contains substring "population, t" lowercase) with score 70 (not 80, because no whitespace-split word in the query equals a word in the name)
    - [ ] `test_substring_in_description_scores_40`: `query="kilowatt"` (or whatever appears only in a description) → matches with score 40
    - [ ] `test_no_match_returns_empty_list`: `query="xxxnomatchxxx"` → returns `[]`
    - [ ] `test_results_sorted_by_score_desc`: fixture with mixed scores; assert returned order is monotonically non-increasing on `relevance_score`
    - [ ] `test_limit_truncates_results`: fixture with 10 matching records; `search_local_metadata(query=..., limit=3)` returns exactly 3 records
    - [ ] `test_description_truncated_to_200_chars`: fixture with description longer than 200 chars; result has `len(description) <= 200`
    - [ ] `test_source_truncated_to_100_chars`: fixture with source longer than 100 chars; result has `len(source) <= 100`
    - [ ] `test_empty_query_returns_empty_list`: `search_local_metadata("")` returns `[]` (no error; short-circuit)
    - [ ] `test_whitespace_query_returns_empty_list`: `search_local_metadata("   ")` returns `[]`
    - [ ] `test_scoring_is_cascading_first_match_wins`: build a record where multiple rules would match (e.g. query="CO2" with a record whose code is `CO2` exactly → score 100, not 80) — assert the higher-priority rule wins
  - [ ] Add `class TestSearchLocalIndicatorsTool:` (AC2, AC4, AC7): covers the MCP tool wrapper
    - [ ] `test_returns_match_response_shape`: with a fixture that yields ≥1 match, assert response has **exactly** the 5 keys `{success, query, total_matches, data, note}`; `success is True`; `note == "Local search - instant results from cached metadata"`; `query` is echoed verbatim
    - [ ] `test_no_match_returns_no_data_note`: with a fixture that yields 0 matches, assert `data == []`, `total_matches == 0`, `note == "No local matches found. Try search_indicators for API-based search."`
    - [ ] `test_empty_query_echoes_original_and_returns_no_match`: call with `query=""`; response echoes the empty string in `query`, returns the no-match note, and never calls `search_local_metadata` (patch and assert call_count == 0)
    - [ ] `test_limit_default_uses_config`: monkey-patch `mcp_server.config.DATA360_LOCAL_SEARCH_LIMIT = 5` (set then restore) and assert the tool returns at most 5 results when `limit` is unspecified. **OR** simply assert the tool's signature default equals `config.DATA360_LOCAL_SEARCH_LIMIT` by inspecting `inspect.signature(search_local_indicators).parameters["limit"].default` — pick whichever is less brittle in this codebase
    - [ ] `test_limit_clamped_to_max_100`: call with `limit=999`; underlying `search_local_metadata` is called with `limit=100` (patch and inspect the call)
    - [ ] `test_limit_clamped_to_min_1`: call with `limit=0` or `limit=-5`; underlying call uses `limit=1`
    - [ ] `test_no_api_client_required`: patch `_client` to `None` and assert the tool succeeds (mirrors Story 5.3's `test_no_api_client_required`)
    - [ ] `test_error_path_returns_api_error_type`: patch `indicator_cache.search_local_metadata` to raise `RuntimeError("boom")`; assert response is `{"success": False, "error": "boom", "error_type": "api_error"}`
  - [ ] Match Story 5.3's testing style: use `@pytest.mark.asyncio` decorators on async tests for clarity (the `asyncio_mode = "auto"` setting makes them redundant but the existing file uses them — be consistent)
  - [ ] Match the file's import order — `import json`, `from pathlib import Path`, `from unittest.mock import patch`, `import pytest`, then `import mcp_server.indicator_cache as indicator_cache`, then `from mcp_server.server import list_popular_indicators, search_local_indicators`
- [ ] Task 5: Quality gate
  - [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
  - [ ] `uv run python -m pytest tests/mcp_server/test_indicator_cache.py -v` passes (Story 5.3 tests + new Story 5.4 tests all green)
  - [ ] Full regression suite `uv run python -m pytest` passes (no regressions in the ~431 existing tests)
  - [ ] Smoke-test the tool end-to-end (optional but recommended): start the server with `uv run python -m mcp_server.server`, call `search_local_indicators(query="CO2")` via `fastmcp dev` or MCP Inspector, verify response shape and that results are sorted by relevance

## Dev Notes

### Scope boundary (read first)

This story delivers **exactly four** code changes:

1. `mcp_server/indicator_cache.py` — **extend** with `_metadata_indicators` singleton, `get_metadata_indicators()`, and `search_local_metadata(query, limit)`
2. `mcp_server/config.py` — **add** `DATA360_LOCAL_SEARCH_LIMIT` env-driven int default (one line)
3. `mcp_server/server.py` — **add** the `search_local_indicators` MCP tool (after `list_popular_indicators`)
4. `tests/mcp_server/test_indicator_cache.py` — **extend** with three new test classes covering the metadata loader, the pure scoring function, and the MCP tool wrapper

It does **NOT** include (these belong to later stories):

- Any `get_temporal_coverage` tool work (Story 6.1) — explicitly out of scope; do not touch `data360_client.py`
- Any MCP prompt or resource definitions (Stories 7.1, 7.2)
- A separate end-to-end test suite story (Story 5.5 will further audit/extend the test coverage)
- Re-curating or regenerating `popular_indicators.json` or `metadata_indicators.json` (Stories 5.1, 5.2)

The data files **already exist and are committed**: `mcp_server/popular_indicators.json` (28 entries, dict-wrapped) and `mcp_server/metadata_indicators.json` (1533 entries, bare list). You are **consuming** them.

### Critical contract deviation — the response shape is NOT the standard tool contract

The project-context rule (and `mcp_server/server.py` precedent for every other tool) is:

> All tools MUST return one of exactly two shapes — Success: `{success, data, total_count, returned_count, truncated}`

**Story 5.4's ACs override that with a tool-specific shape:**

```python
# Match response (AC2):
{
    "success": True,
    "query": "<echoed>",
    "total_matches": <int>,
    "data": [...],
    "note": "Local search - instant results from cached metadata",
}

# No-match / empty-query response (AC4):
{
    "success": True,
    "query": "<echoed>",
    "total_matches": 0,
    "data": [],
    "note": "No local matches found. Try search_indicators for API-based search.",
}

# Error response (AC7) — UNCHANGED from the project standard:
{"success": False, "error": str, "error_type": "api_error"}
```

This is an **intentional, AC-driven deviation** — same pattern as Story 5.3 (which returned grouped `data` instead of a flat list). It is **not** a bug. **Do not** sneak in `total_count`/`returned_count`/`truncated` to make it "compliant" — those keys are absent by design. Note this in the Completion Notes so the code reviewer expects it.

The error contract (AC7) is unchanged — `error_type` is `"api_error"` (the only valid value here; `"timeout"` doesn't apply to a local-file tool).

### Scoring algorithm — canonical implementation (use verbatim, with two corrections)

The architecture addendum (lines 1018–1064) provides a blueprint. Use it, but apply two corrections:

```python
def search_local_metadata(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search indicator metadata with cascading relevance scoring."""
    query_clean = query.strip()
    if not query_clean:
        return []                                # AC4: short-circuit empty/whitespace

    indicators = get_metadata_indicators()
    query_lower = query_clean.lower()
    query_words = query_lower.split()
    results: list[dict[str, Any]] = []

    for ind in indicators:
        code = ind.get("code", "").lower()
        name = ind.get("name", "").lower()
        desc = ind.get("description", "").lower()
        name_words = name.split()

        if query_lower == code:
            score = 100
        elif query_lower in code:
            score = 90
        elif any(word in name_words for word in query_words):
            score = 80
        elif query_lower in name:
            score = 70
        elif query_lower in desc:
            score = 40
        else:
            score = 0

        if score == 0:
            continue

        description = ind.get("description", "")[:200]
        source = ind.get("source", "")[:100]
        results.append({
            "indicator": ind.get("code", ""),
            "name": ind.get("name", ""),
            "description": description,
            "source": source,
            "relevance_score": score,
        })

    results.sort(key=lambda r: r["relevance_score"], reverse=True)
    return results[:limit]
```

**Corrections vs. the architecture blueprint:**

1. **Empty-query short-circuit added** — the blueprint would assign score 90 to every record because `"" in code` is always `True`. AC4 mandates an explicit short-circuit.
2. **Truncation simplified** — the blueprint has redundant `if/else` around the `[:200]` slice; the slice itself is idempotent on shorter strings, so the conditional is dead code. Just slice.
3. **`name.split()` cached as `name_words`** — micro-perf; pre-split once instead of inside the `any()` generator per word (1500 records × ~3 query words × ~5 name words = no big deal, but the cleaner form is the same line count).

Otherwise, **do not** restructure the cascade — the rule ordering and the `if/elif` priority is the AC.

### "Word in name" — exact semantics for the trickiest rule

Score 80 is `any(word in name.split() for word in query_words)`. This means:

- Both `query_words` and `name.split()` are **whitespace-split lowercase tokens** — punctuation is **not** stripped
- A query word matches only if it appears as a **whole token** in the name, not as a substring of a token
- Examples (with metadata records' actual names):
  - `query="CO2"`, name="CO2 emissions (kt)" → name.split() = `["co2", "emissions", "(kt)"]`. `"co2"` is in that list → score 80 ✓
  - `query="emissions"`, name="CO2 emissions (kt)" → `"emissions"` in `["co2", "emissions", "(kt)"]` → score 80 ✓
  - `query="kt"`, name="CO2 emissions (kt)" → `"kt"` in `["co2", "emissions", "(kt)"]` → **False** because `(kt)` keeps its parens → fall through to substring-in-name rule: `"kt" in "co2 emissions (kt)"` → **True** → score 70
  - `query="CO2 emissions"`, name="CO2 emissions (kt)" → query_words = `["co2", "emissions"]`; both are in name.split() → first one to match triggers `any()` → score 80
  - `query="population growth"`, name="Population, total" → query_words = `["population", "growth"]`; name.split() = `["population,", "total"]`. `"population"` is **NOT** in `["population,", "total"]` because of the trailing comma → fall through to substring-in-name: `"population growth" in "population, total"` → False → fall through to description.

This is consistent with the architecture blueprint and prior Data360 search semantics. Tests must use this exact behavior.

### Empty / whitespace-only query — handle in two places

Defense in depth:

1. **Inside `search_local_metadata`** (Task 1): early return `[]` if `query.strip()` is empty
2. **Inside the MCP tool wrapper** (Task 3): same check, return the AC4 no-match-note response without calling `search_local_metadata`

The wrapper-level check exists so the no-match *note* is surfaced (the underlying `search_local_metadata` returns just `[]` — it doesn't know about response shapes).

### `DATA360_LOCAL_SEARCH_LIMIT` — what it controls

It is the **default value** for the tool's `limit` parameter, sourced from an env var at module-import time:

```python
# config.py
DATA360_LOCAL_SEARCH_LIMIT: int = _int_env("DATA360_LOCAL_SEARCH_LIMIT", 20, min_val=1)
```

```python
# server.py
@mcp.tool()
async def search_local_indicators(
    query: str,
    limit: int = config.DATA360_LOCAL_SEARCH_LIMIT,  # default of 20, env-overridable
) -> dict[str, Any]:
```

It is NOT a hard cap. The defensive clamp `max(1, min(int(limit), 100))` inside the tool enforces the architecture's "1-100" range regardless of what config or caller pass — this guards against a misconfigured env (`DATA360_LOCAL_SEARCH_LIMIT=999`) and against a malicious or buggy caller.

`min_val=1` in `_int_env` prevents `DATA360_LOCAL_SEARCH_LIMIT=0` from breaking the default. No `max_val` argument is needed in `_int_env`; the tool-level clamp covers that side.

### Tool signature & docstring (use verbatim from the architecture addendum)

```python
@mcp.tool()
async def search_local_indicators(
    query: str,
    limit: int = config.DATA360_LOCAL_SEARCH_LIMIT,
) -> dict[str, Any]:
    """Search indicator metadata offline using local cached data.

    Performs instant substring matching against ~1500 indicator codes,
    names, and descriptions. Results are ranked by relevance score.
    Use this for fast discovery before calling search_indicators for
    full API results.

    Note: Results include indicator codes but NOT database IDs.
    Call search_indicators to get the database_id needed for get_data.

    Args:
        query: Search term (case-insensitive). Matches against code, name, description.
        limit: Maximum results to return (1-100, default 20).

    Returns:
        dict with success, query, total_matches, data (list with indicator,
        name, description, source, relevance_score), note.
    """
```

The function is `async def` to match the established tool pattern even though it does no `await` — FastMCP tools in this project are async, and tests `await` them directly (see `tests/mcp_server/test_server.py`, Story 5.3 tests).

### `indicator_cache.py` — target final shape after this story

```python
"""Singleton loader and relevance search for offline indicator data."""

import json  # noqa: F401 — kept implicit through the existing module
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent

_popular_indicators: list[dict[str, Any]] | None = None
_metadata_indicators: list[dict[str, Any]] | None = None         # NEW


def _load_json(filename: str) -> list | dict:                    # UNCHANGED
    """Load a JSON file from the mcp_server directory using UTF-8."""
    path = DATA_DIR / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def get_popular_indicators() -> dict[str, Any]:                  # UNCHANGED
    """Return curated popular indicators (loaded once, cached in memory)."""
    global _popular_indicators
    if _popular_indicators is None:
        data = _load_json("popular_indicators.json")
        _popular_indicators = data.get("indicators", data) if isinstance(data, dict) else data
        logger.info("Loaded %d popular indicators", len(_popular_indicators))
    return {"indicators": _popular_indicators, "total": len(_popular_indicators)}


def get_metadata_indicators() -> list[dict[str, Any]]:           # NEW
    """Return full metadata indicator list (loaded once, cached in memory)."""
    global _metadata_indicators
    if _metadata_indicators is None:
        _metadata_indicators = _load_json("metadata_indicators.json")
        logger.info("Loaded %d metadata indicators", len(_metadata_indicators))
    return _metadata_indicators


def search_local_metadata(query: str, limit: int = 20) -> list[dict[str, Any]]:   # NEW
    """Search indicator metadata with cascading relevance scoring.

    Scoring (first match wins):
      100 — exact code match
       90 — code substring
       80 — query word in name (whitespace-split tokens)
       70 — query substring in name
       40 — query substring in description
    """
    # See Dev Notes → "Scoring algorithm" for the full body.
    ...
```

**Critical:** the metadata loader assigns the file content **directly** to `_metadata_indicators` (no `.get("indicators", data)` unwrap). The file is a **bare list**, unlike `popular_indicators.json`. Story 5.2 specifically committed it as a bare list so this loader doesn't need to disambiguate. If you mirror the popular-indicators unwrap pattern here, `_metadata_indicators` becomes a `list[int]` of list indices (because `list.get` doesn't exist) — actually it raises `AttributeError: 'list' object has no attribute 'get'`. Don't do it.

### server.py integration — exact placement

Place the new tool after `list_popular_indicators` (currently ends ~line 287) and before the `if config.RAG_ENABLED:` block (currently ~line 290). The block ordering becomes:

```
search_indicators           # line ~42
get_data                    # line ~86
get_metadata                # line ~130
list_indicators             # line ~171
get_disaggregation          # line ~208
list_popular_indicators     # line ~250  (Story 5.3)
search_local_indicators     # line ~290  (THIS STORY)
[blank line]
if config.RAG_ENABLED:      # ~line 293+
    ...
```

No new imports needed — `indicator_cache` and `config` are already imported. `Data360Client` does not appear in this tool (offline only).

This tool does **not** use `_client`, `_db_pool`, `_map_params`, or any HTTP path. It must remain fully functional with the API unreachable — that is the whole point of "offline" discovery (FR37, NFR9). Verify with the `test_no_api_client_required` test that patches `_client` to `None`.

### Tool body (use as starting point)

```python
@mcp.tool()
async def search_local_indicators(
    query: str,
    limit: int = config.DATA360_LOCAL_SEARCH_LIMIT,
) -> dict[str, Any]:
    """...docstring from above..."""
    try:
        # Defensive clamp — guards against misconfigured env and bad callers
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = config.DATA360_LOCAL_SEARCH_LIMIT
        limit = max(1, min(limit, 100))

        # AC4: empty/whitespace query short-circuits to no-match
        if not query or not query.strip():
            logger.info("search_local_indicators: empty query")
            return {
                "success": True,
                "query": query,
                "total_matches": 0,
                "data": [],
                "note": "No local matches found. Try search_indicators for API-based search.",
            }

        results = indicator_cache.search_local_metadata(query, limit=limit)

        if not results:
            logger.info("search_local_indicators: no matches for query=%r", query)
            return {
                "success": True,
                "query": query,
                "total_matches": 0,
                "data": [],
                "note": "No local matches found. Try search_indicators for API-based search.",
            }

        return {
            "success": True,
            "query": query,
            "total_matches": len(results),
            "data": results,
            "note": "Local search - instant results from cached metadata",
        }
    except Exception as exc:
        logger.error("search_local_indicators failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}
```

Echo the **original** `query` (not the stripped/lowered form) so the caller sees what they sent. This matches established UX in `search_indicators`-type tools.

### Singleton testing — extend, don't replace

Story 5.3 already has the cache reset fixture in `tests/mcp_server/test_indicator_cache.py`:

```python
@pytest.fixture(autouse=True)
def _reset_cache():
    indicator_cache._popular_indicators = None
    yield
    indicator_cache._popular_indicators = None
```

**Extend it in-place** to also reset `_metadata_indicators` (both before and after). Do not create a parallel fixture — that would split responsibility and risk a state leak. The fixture's `autouse=True` already covers every test in the file, including the existing Story 5.3 tests, which is what we want.

To assert "metadata file read exactly once":

```python
def test_metadata_singleton_caches_after_first_load():
    with patch(
        "mcp_server.indicator_cache._load_json",
        wraps=indicator_cache._load_json,
    ) as spy:
        first = indicator_cache.get_metadata_indicators()
        second = indicator_cache.get_metadata_indicators()
    assert spy.call_count == 1
    assert first is second  # same list reference
```

### Tests for the pure scoring function — use a fixture list, not the real file

`search_local_metadata` is a pure function (given the cached list). Test it by **patching the singleton directly** with a small fixture list rather than exercising the real 1533-record metadata file. Rationale:

- Stable: file contents drift as the catalog regenerates; brittle to depend on specific real codes
- Fast: no I/O, no JSON parse
- Precise: you can construct records that exercise each scoring rule unambiguously

Example pattern:

```python
@pytest.fixture
def fixture_indicators(monkeypatch):
    fixture = [
        {"code": "SP_POP_TOTL", "name": "Population, total",
         "description": "Total population midyear.", "source": "WDI"},
        {"code": "EN_ATM_CO2E_KT", "name": "CO2 emissions (kt)",
         "description": "Carbon dioxide emissions from fuel combustion.", "source": "WDI"},
        # ...
    ]
    monkeypatch.setattr(indicator_cache, "_metadata_indicators", fixture)
    return fixture


def test_exact_code_match_scores_100(fixture_indicators):
    results = indicator_cache.search_local_metadata("SP_POP_TOTL")
    assert results[0]["relevance_score"] == 100
    assert results[0]["indicator"] == "SP_POP_TOTL"
```

`monkeypatch.setattr` restores automatically; combined with the `_reset_cache` autouse fixture, isolation is guaranteed.

### Previous story learnings (Stories 5.1, 5.2, 5.3 code reviews)

- **UTF-8 everywhere** — already covered by reusing `_load_json`. Don't open files manually anywhere; go through the helper. Tests that read files directly (e.g. for cross-check fixtures) must pass `encoding="utf-8"`. This is the #1 repeated review finding across Epic 5.
- **Exact-keys assertions** — assert that response objects have **exactly** the expected key set (use `set(result.keys()) == {...}`), and that result items have **exactly** their five keys. Story 5.3 used `INDICATOR_KEYS = {"code", "name", "description"}` with `assert set(ind.keys()) == INDICATOR_KEYS`. Do the same here with `RESULT_KEYS = {"indicator", "name", "description", "source", "relevance_score"}`.
- **Don't over-scope** — Stories 5.1/5.2/5.3 all explicitly fenced off later-story work. Story 5.4 owns metadata loader + scoring + the tool + the config var. Story 5.5 owns the broader test audit. Do not add new functionality outside the four listed deliverables.
- **Load-time / perf assertions are optional and prone to CI flakiness** — NFR13 (<50ms warm) is trivially met. A timing test is acceptable with a generous margin (≥250ms warm, ≥1000ms cold) but is not the point — correctness assertions are the deliverable. Story 5.3 omitted a timing test entirely; that is acceptable here too.
- **Error path tests via `patch(...).side_effect = RuntimeError(...)`** — Story 5.3 used this exact idiom for AC6; reuse it for AC7 here (patch `indicator_cache.search_local_metadata` to raise).
- **`logger.error` without `exc_info` is the project pattern** — every existing tool uses `logger.error("X failed: %s", exc)`. Match that. (A project-wide migration to `logger.exception` is a separate concern; was deferred in the Story 5.3 code review.)
- **`logger.info` for "no data found"** — the project rule "no data found must be explicit, never silently empty" applies. For this tool, the `note` field surfaces it in the response; an `INFO` log adds an additional ops signal. Both belong.

### Testing standards (project-context.md)

- Tests live in `tests/mcp_server/`, mirroring source structure — extend the existing `test_indicator_cache.py`, do not create a separate file (one file per source module is the convention)
- `asyncio_mode = "auto"` is set in `pyproject.toml`; `@pytest.mark.asyncio` is redundant but the existing file uses it for clarity on async tests — match that style
- Group tests in classes with AC-referencing docstrings, e.g. `class TestSearchLocalMetadata:` with `"""AC1: cascading relevance scoring."""`
- Import the tool directly: `from mcp_server.server import search_local_indicators` and `await` it — established pattern (`test_server.py:10`, `test_indicator_cache.py:10`). FastMCP's `@mcp.tool()` leaves the function directly callable in this project's version.
- This tool needs **no** `mock_client` fixture — it does not touch `_client`. (Test `test_no_api_client_required` should patch `_client` to `None` to prove this.)
- Python 3.12 style (project-context.md): `X | None` not `Optional[X]`; `dict[str, Any]` not `Dict`; type hints on all signatures; double quotes; line length 120.

### Architecture compliance & boundaries

- **New Boundary (architecture addendum, lines 1166–1171):** `indicator_cache.py` is the ONLY module that reads the local JSON data files; `server.py` calls `indicator_cache` functions and never reads JSON directly. Honor this — the tool must call `indicator_cache.search_local_metadata()` and `indicator_cache.get_metadata_indicators()`, not open the file itself.
- `indicator_cache.py` reads local files only, never makes API calls. The new `search_local_metadata` function is pure (apart from the singleton load) — no network, no DB, no side effects beyond the singleton population.
- **Location:** `indicator_cache.py` is a sibling of `server.py` in `mcp_server/`; `DATA_DIR = Path(__file__).parent` resolves the JSON files correctly. Already in place from Story 5.3.
- **No new dependencies.** `json`, `logging`, `pathlib`, `typing` are stdlib; everything else is already imported.

### Cross-story contract (for Story 5.5 and Epic 6)

- Story 5.5 (test suite audit) will likely:
  - Add a fixture-based test of relevance scoring against the **real** `metadata_indicators.json` for at least one well-known indicator (e.g. `SP_POP_TOTL` → exact code → 100)
  - Add a regression-style "tool returns within 50ms after cold load" timing test with a generous threshold
  - Audit edge cases not covered here (Unicode in query, very long queries, etc.)
  - Leave your test class structure intact — name them `TestGetMetadataIndicators`, `TestSearchLocalMetadata`, `TestSearchLocalIndicatorsTool` so 5.5 can extend cleanly.
- Epic 6 will add `get_temporal_coverage`. That tool **does** make an API call and **does** belong inside the `data360_client.py` boundary. Do not preemptively add temporal-coverage helpers to `indicator_cache.py` — that module stays offline-only.

### Smoke testing (optional but recommended before marking review-ready)

Once implementation passes the quality gate, exercise the tool end-to-end:

```bash
uv run fastmcp dev mcp_server/server.py
# In MCP Inspector: invoke search_local_indicators({"query": "CO2", "limit": 5})
```

Expected: 5 results, all with `relevance_score >= 70` (CO2 is in many WDI codes and names), `note` starts with "Local search". Then try `{"query": "asdfqwer"}` — expect 0 matches with the "No local matches" note. Then try `{"query": ""}` — same no-match shape, with the empty string echoed back. Verify response time is sub-second.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.4] — Acceptance criteria: cascading relevance scoring 100/90/80/70/40, results sorted desc, response shape (`success`/`query`/`total_matches`/`data`/`note`), result-level keys (`indicator`/`name`/`description`/`source`/`relevance_score`), 200/100 char truncation, limit param, empty-result note "No local matches found. Try search_indicators for API-based search.", singleton metadata caching (FR38, FR39, FR40, NFR13)
- [Source: _bmad-output/planning-artifacts/architecture.md#Architecture Addendum: Epics 5-7] — `search_local_indicators` tool signature + docstring (lines 805–827), `indicator_cache.py` design (`get_metadata_indicators`, `search_local_metadata`, lines 1009–1064), `config.py` addendum (line 784, "add DATA360_LOCAL_SEARCH_LIMIT default"), implementation sequence step 9–10 (lines 1133–1134), architectural boundary (`indicator_cache.py` is the only JSON reader, lines 1166–1171)
- [Source: mcp_server/server.py] — Established `@mcp.tool()` async pattern, `try/except` → `{"success": False, "error": ..., "error_type": "api_error"}`, top-level `from mcp_server import config, indicator_cache` imports, position of `list_popular_indicators` (~line 250)
- [Source: mcp_server/indicator_cache.py] — Existing `_load_json` helper (UTF-8, do not redefine), `_popular_indicators` singleton precedent for the new `_metadata_indicators` singleton
- [Source: mcp_server/metadata_indicators.json] — The data file being consumed: bare JSON array, 1533 entries, fields `code`/`name`/`description`/`source`. Source field is e.g. "World Development Indicators (WDI)" (~33 chars — well under the 100-char truncation budget)
- [Source: mcp_server/config.py] — Established `_int_env` helper with `min_val` param; placement convention for env-driven constants
- [Source: tests/mcp_server/test_indicator_cache.py] — Story 5.3's test patterns: `_reset_cache` fixture (extend in-place), `INDICATOR_KEYS = {...}` exact-keys assertion idiom, `unittest.mock.patch(..., wraps=...)` for singleton-call counting, error-path test with `side_effect=RuntimeError("boom")`, `_client` patched to `None` for "no API needed" proof
- [Source: _bmad-output/implementation-artifacts/5-1-popular-indicators-data-file.md#Review Findings] — UTF-8 encoding, exact-keys assertion guidance, scope-fencing precedent
- [Source: _bmad-output/implementation-artifacts/5-2-metadata-indicators-data-file.md#Dev Notes] — `metadata_indicators.json` is a **bare list** (not dict-wrapped); the loader must NOT call `.get("indicators", data)` on it
- [Source: _bmad-output/implementation-artifacts/5-3-list-popular-indicators-mcp-tool.md] — Singleton pattern, AC-driven response-shape deviation precedent (grouped `data`), error path test idiom, `@pytest.mark.asyncio` style choice
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — Known deferred items in `indicator_cache.py` (singleton race, blocking I/O in async, no defensive copy) — do not silently fix them in this story; they have explicit deferral context. If you address one, document the change and the rationale in Completion Notes.
- [Source: _bmad-output/project-context.md] — Tool response contract (and the rule that this story intentionally deviates from), Python 3.12 style rules, testing rules ("no API call in indicator_cache" boundary, "no data found must be explicit"), env-var pattern

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
