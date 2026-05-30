# Story 5.3: list_popular_indicators MCP Tool

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user exploring World Bank data,
I want to see a curated list of popular climate and development indicators,
so that I can quickly discover relevant indicators without knowing exact codes.

## Acceptance Criteria

1. **Given** the MCP server is running
   **When** a user calls `list_popular_indicators()`
   **Then** the tool returns the curated indicator list sourced from `mcp_server/popular_indicators.json` (FR37)
   **And** **no** call is made to the Data360 API (the tool never touches `_client`)

2. **Given** a successful call
   **When** the response is inspected
   **Then** it follows the success contract `{"success": True, "data": [...], "total_count": N, "returned_count": N, "truncated": False}`
   **And** `total_count` and `returned_count` both equal the number of **individual indicators** (28 in the current file), NOT the number of categories
   **And** `truncated` is `False` (the full curated set is always returned)

3. **Given** the response `data` field
   **When** inspected
   **Then** indicators are **grouped by category**: `data` is a list of group objects, each `{"category": <str>, "indicators": [{"code", "name", "description"}, ...]}`
   **And** every indicator from the file appears in exactly one group
   **And** each indicator object preserves the `code`, `name`, and `description` fields (the `category` field is lifted to the group level and not repeated inside each indicator)

4. **Given** the MCP server has not yet loaded the popular indicators file
   **When** `list_popular_indicators()` is called for the first time
   **Then** the file is read from disk **once** and cached in a module-level singleton in `mcp_server/indicator_cache.py` (FR40)
   **And** subsequent calls reuse the cached data without re-reading the file

5. **Given** any call to the tool
   **When** timed
   **Then** the response is returned in well under 50ms (NFR13) — trivially satisfied because the data is in memory after the first load and grouping is an O(n) pass over ≤30 items

6. **Given** an unexpected error while loading or grouping (e.g. the data file is missing or malformed)
   **When** the tool runs
   **Then** it returns the error contract `{"success": False, "error": <str>, "error_type": "api_error"}` and logs the error (matching the pattern used by every existing tool in `server.py`)

## Tasks / Subtasks

- [x] Task 1: Create `mcp_server/indicator_cache.py` with the popular-indicators loader (AC: 1, 4)
  - [x] Add module docstring, `import json`, `import logging`, `from pathlib import Path`, `from typing import Any`, and `logger = logging.getLogger(__name__)`
  - [x] Define `DATA_DIR = Path(__file__).parent` (resolves to the `mcp_server/` package dir where the JSON lives)
  - [x] Define module-level singleton `_popular_indicators: list[dict[str, Any]] | None = None`
  - [x] Implement `_load_json(filename: str) -> list | dict` — opens `DATA_DIR / filename` **with `encoding="utf-8"`** and returns `json.load(f)`. **The encoding kwarg is mandatory** (see Dev Notes → "Critical: UTF-8 encoding")
  - [x] Implement `get_popular_indicators() -> dict[str, Any]`:
    - [x] On first call only (`_popular_indicators is None`), call `_load_json("popular_indicators.json")`, then assign `_popular_indicators = data.get("indicators", data)` (tolerates both the dict-wrapped and bare-list shapes — the committed file is dict-wrapped under `"indicators"`)
    - [x] `logger.info("Loaded %d popular indicators", len(_popular_indicators))` on first load
    - [x] Return `{"indicators": _popular_indicators, "total": len(_popular_indicators)}`
  - [x] **Do NOT** add `get_metadata_indicators` or `search_local_metadata` — those belong to Story 5.4. Keep this module minimal for now.
- [x] Task 2: Add the `list_popular_indicators` MCP tool to `mcp_server/server.py` (AC: 1, 2, 3, 5, 6)
  - [x] Add `from mcp_server import indicator_cache` to the top-level imports (alongside `from mcp_server import config`). It is a lightweight stdlib-only module — register the tool **unconditionally** (NOT behind the `config.RAG_ENABLED` flag)
  - [x] Define `async def list_popular_indicators() -> dict[str, Any]:` decorated with `@mcp.tool()`, placed after `get_disaggregation` and before the `if config.RAG_ENABLED:` block
  - [x] Use the docstring from the architecture addendum (see Dev Notes → "Tool signature & docstring")
  - [x] Body: wrap in `try/except` exactly like the other tools. Inside: call `indicator_cache.get_popular_indicators()`, group the flat indicator list by `category`, and build the grouped `data` list
  - [x] Grouping must preserve first-seen category order (use a plain `dict` accumulator — insertion-ordered in Python 3.12); within each group preserve file order
  - [x] Strip the `category` key out of each per-indicator object (lift it to the group level), keeping only `code`, `name`, `description`
  - [x] Set `total_count` and `returned_count` to the total indicator count (sum across groups), `truncated=False`
  - [x] `except Exception as exc:` → `logger.error("list_popular_indicators failed: %s", exc)` and return `{"success": False, "error": str(exc), "error_type": "api_error"}`
- [x] Task 3: Write tests in `tests/mcp_server/test_indicator_cache.py` (AC: 1, 2, 3, 4, 6)
  - [x] Create the new file (Story 5.4 and 5.5 will extend it — establish the structure now)
  - [x] Add a fixture that **resets the singleton** before and after each test: set `indicator_cache._popular_indicators = None` (otherwise cache state leaks across tests). Apply it to every test that calls the loader/tool
  - [x] `class TestGetPopularIndicators:` — covers the cache loader (AC1, AC4):
    - [x] Returns a dict with `indicators` (list) and `total` (int == len)
    - [x] **Singleton caching:** patch/spy `indicator_cache._load_json` (e.g. `unittest.mock.patch` wrapping the real function) and assert it is called **exactly once** across two consecutive `get_popular_indicators()` calls
  - [x] `class TestListPopularIndicatorsTool:` — covers the tool (AC2, AC3, AC5, AC6):
    - [x] `await list_popular_indicators()` returns `success is True`, exact keys `{success, data, total_count, returned_count, truncated}`
    - [x] `data` is a list of group objects each with keys `{category, indicators}`; every group's `indicators` entries have exactly `{code, name, description}` (assert `category` is NOT present inside per-indicator objects)
    - [x] `total_count == returned_count == ` sum of indicators across groups `== 28` (or assert it equals the count read directly from the JSON file, to avoid coupling to the literal 28)
    - [x] `truncated is False`
    - [x] No duplicate categories in `data`; the set of categories equals the set in the source file
    - [x] **No API call:** assert the tool works with `_client` patched to `None` (or simply do not provide a `mock_client` — the tool must never reference `_client`)
    - [x] **Error path (AC6):** patch `indicator_cache.get_popular_indicators` to raise, assert the tool returns `{"success": False, "error_type": "api_error"}` with a non-empty `error` string
  - [x] Open any direct file reads in tests with `encoding="utf-8"`
- [x] Task 4: Quality gate
  - [x] `uv run ruff check .` and `uv run ruff format --check .` pass
  - [x] `uv run python -m pytest tests/mcp_server/test_indicator_cache.py -v` passes
  - [x] Full regression suite `uv run python -m pytest` passes (no regressions in the existing ~431 tests)

## Dev Notes

### Scope boundary (read first)

This story delivers **exactly two** code artifacts plus tests:
1. `mcp_server/indicator_cache.py` — NEW module, but **only** the `_load_json` helper + `get_popular_indicators()` singleton loader
2. `list_popular_indicators` MCP tool added to `mcp_server/server.py`
3. `tests/mcp_server/test_indicator_cache.py` — NEW test file

It does **NOT** include (these are Story 5.4):
- `get_metadata_indicators()` / `search_local_metadata()` in `indicator_cache.py`
- the `search_local_indicators` MCP tool
- the `DATA360_LOCAL_SEARCH_LIMIT` config value in `config.py` — **do not touch `config.py`** in this story

The data files already exist and are committed: `mcp_server/popular_indicators.json` (Story 5.1, dict-wrapped under `"indicators"`, 28 entries) and `mcp_server/metadata_indicators.json` (Story 5.2, bare list). You are **consuming** `popular_indicators.json`, not creating it.

### Critical: UTF-8 encoding (must deviate from the architecture blueprint)

The architecture addendum's `_load_json` blueprint uses `open(path)` **without** an encoding argument:

```python
def _load_json(filename: str) -> list[dict] | dict:
    path = DATA_DIR / filename
    with open(path) as f:        # ← BUG: no encoding
        return json.load(f)
```

**This is a latent bug.** `popular_indicators.json` contains non-ASCII characters (em-dashes/en-dashes in indicator names and descriptions, e.g. "$3.00 (2021 PPP) — the international (extreme) poverty line"). On a non-UTF-8 locale, `open()` uses the platform default encoding and `json.load` raises `UnicodeDecodeError`. Both the Story 5.1 and Story 5.2 code reviews flagged this exact class of issue. **Always pass `encoding="utf-8"`:**

```python
def _load_json(filename: str) -> list | dict:
    path = DATA_DIR / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)
```

### `indicator_cache.py` — target implementation for THIS story

Implement only the popular-indicators slice. Story 5.4 will append the metadata functions to this same module.

```python
"""Singleton loader and relevance search for offline indicator data."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton state
_popular_indicators: list[dict[str, Any]] | None = None

DATA_DIR = Path(__file__).parent


def _load_json(filename: str) -> list | dict:
    """Load a JSON file from the mcp_server directory (UTF-8)."""
    path = DATA_DIR / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def get_popular_indicators() -> dict[str, Any]:
    """Return curated popular indicators (loaded once, cached in memory)."""
    global _popular_indicators
    if _popular_indicators is None:
        data = _load_json("popular_indicators.json")
        _popular_indicators = data.get("indicators", data)
        logger.info("Loaded %d popular indicators", len(_popular_indicators))
    return {"indicators": _popular_indicators, "total": len(_popular_indicators)}
```

Note the `data.get("indicators", data)` line: the committed file is `{"indicators": [...]}`, so this returns the inner list. It also tolerates a bare-list file. This exactly matches the architecture contract and the Story 5.1 dev notes.

### Tool signature & docstring (use verbatim from the architecture addendum)

```python
@mcp.tool()
async def list_popular_indicators() -> dict[str, Any]:
    """List curated popular climate and development indicators.

    Returns a categorized list of ~25-30 commonly requested indicators
    with codes, names, and descriptions. No API call required - instant results.

    Returns:
        dict with success, data (list of indicators grouped by category),
        total_count, returned_count, truncated.
    """
```

The function is `async def` to match the established tool pattern even though it does no `await` — FastMCP tools in this project are async, and the test suite awaits them directly (see `tests/mcp_server/test_server.py`).

### Response shape — exact target (resolves the "grouped by category" ambiguity)

`get_popular_indicators()` returns a **flat** list wrapped as `{"indicators": [...], "total": N}`. The **tool** must transform that flat list into a category-grouped `data` structure. AC3 requires grouping; the standard contract requires `data` to be a list. The agreed shape is a **list of group objects**:

```json
{
  "success": true,
  "data": [
    {
      "category": "Climate & Environment",
      "indicators": [
        {"code": "EN_GHG_CO2_MT_CE_AR5", "name": "CO2 emissions (total, excl. LULUCF) (Mt CO2e)", "description": "..."},
        {"code": "EN_GHG_ALL_PC_CE_AR5", "name": "Total greenhouse gas emissions per capita (t CO2e/capita)", "description": "..."}
      ]
    },
    {
      "category": "Energy",
      "indicators": [ ... ]
    }
  ],
  "total_count": 28,
  "returned_count": 28,
  "truncated": false
}
```

**Critical count semantics:** `total_count` and `returned_count` count **individual indicators (28)**, not category groups (7). Do not accidentally set them to `len(data)` — that would report 7. Compute the indicator total via `sum(len(g["indicators"]) for g in data)` or by counting before grouping.

A flat-list-sorted-by-category shape was considered and **rejected** — AC3 explicitly says "grouped", and the list-of-groups form is the unambiguous reading. Implement the grouped form above.

### Grouping implementation sketch

```python
@mcp.tool()
async def list_popular_indicators() -> dict[str, Any]:
    """...docstring above..."""
    try:
        result = indicator_cache.get_popular_indicators()
        indicators = result["indicators"]

        groups: dict[str, list[dict[str, Any]]] = {}
        for ind in indicators:
            category = ind.get("category", "Uncategorized")
            groups.setdefault(category, []).append(
                {"code": ind.get("code", ""), "name": ind.get("name", ""), "description": ind.get("description", "")}
            )

        data = [{"category": category, "indicators": items} for category, items in groups.items()]
        total = sum(len(g["indicators"]) for g in data)
        return {
            "success": True,
            "data": data,
            "total_count": total,
            "returned_count": total,
            "truncated": False,
        }
    except Exception as exc:
        logger.error("list_popular_indicators failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}
```

`dict` preserves insertion order in Python 3.12, so categories appear in first-seen file order (the file is already authored category-by-category). This keeps Climate & Environment first, which suits the climate-focused mission.

### server.py integration points

- Add the import near the top with the other package imports:
  ```python
  from mcp_server import config
  from mcp_server import indicator_cache   # NEW
  from mcp_server.data360_client import Data360Client
  ```
  (ruff isort will order these — run `uv run ruff check --fix .` to auto-sort.)
- Register `list_popular_indicators` **unconditionally** — place its `@mcp.tool()` definition after `get_disaggregation` (ends ~line 247) and before the `if config.RAG_ENABLED:` block (~line 250). Do **not** nest it inside the RAG flag.
- This tool does **not** use `_client`, `_db_pool`, `_map_params`, or any HTTP path. It must remain fully functional with the API unreachable — that is the whole point of "offline" discovery (FR37, NFR9).

### Tool response contract (project-context.md)

All tools return one of exactly two shapes:
- **Success:** `{"success": True, "data": [...], "total_count": int, "returned_count": int, "truncated": bool}`
- **Error:** `{"success": False, "error": str, "error_type": "api_error" | "timeout"}` — only `"api_error"` and `"timeout"` are valid `error_type` values. Use `"api_error"` here (there is no network timeout to surface for a local-file tool).

The grouped `data` (list of `{category, indicators}` objects) is an intentional, AC-driven deviation from the flat `data` lists the API-backed tools return. It still satisfies the contract (`data` is a list). Note this in the Completion Notes so the reviewer expects it.

### Singleton testing — avoid cross-test contamination

`_popular_indicators` is module-global state. Without resetting it between tests, the "loaded once" assertion and any test ordering becomes flaky. Provide a reset fixture:

```python
import mcp_server.indicator_cache as indicator_cache

@pytest.fixture(autouse=True)
def _reset_cache():
    indicator_cache._popular_indicators = None
    yield
    indicator_cache._popular_indicators = None
```

To assert "file read exactly once" (AC4), wrap the real loader and count calls:

```python
from unittest.mock import patch

def test_singleton_caches_after_first_load():
    with patch("mcp_server.indicator_cache._load_json", wraps=indicator_cache._load_json) as spy:
        first = indicator_cache.get_popular_indicators()
        second = indicator_cache.get_popular_indicators()
    assert spy.call_count == 1
    assert first["total"] == second["total"]
```

### Testing standards (project-context.md)

- Tests live in `tests/mcp_server/`, mirroring source structure → new file `tests/mcp_server/test_indicator_cache.py`.
- `asyncio_mode = "auto"` is set in `pyproject.toml`; `@pytest.mark.asyncio` is redundant but acceptable (the existing `test_server.py` uses it explicitly — match that style for the async tool tests).
- Group tests in classes with AC-referencing docstrings, e.g. `class TestListPopularIndicatorsTool:` with `"""AC3: indicators grouped by category."""`.
- Import the tool directly: `from mcp_server.server import list_popular_indicators` and `await` it — this is the established pattern (`test_server.py:10`). FastMCP's `@mcp.tool()` leaves the function directly callable in this project's version.
- This tool needs **no** `mock_client` fixture — it does not touch `_client`. (If a test imports `list_popular_indicators`, importing `server` triggers no client construction; `_client` is only set in `_lifespan`.)
- Open any direct JSON reads with `encoding="utf-8"`.

### Architecture compliance & boundaries

- **New Boundary (architecture addendum):** `indicator_cache.py` is the ONLY module that reads the local JSON data files; `server.py` calls `indicator_cache` functions and never reads JSON directly. Honor this — the tool must call `indicator_cache.get_popular_indicators()`, not open the file itself.
- `indicator_cache.py` reads local files only, never makes API calls.
- **Location:** `indicator_cache.py` is a sibling of `server.py` in `mcp_server/`; `DATA_DIR = Path(__file__).parent` resolves the JSON files correctly.
- **No new dependencies.** `json`, `logging`, `pathlib`, `typing` are stdlib.
- **Python 3.12 style (project-context.md):** `X | None` not `Optional[X]`; `dict[str, Any]` not `Dict`; type hints on all signatures; double quotes; line length 120.

### Previous story learnings (Stories 5.1 & 5.2 reviews)

- **UTF-8 everywhere** — the #1 repeated review finding. Already covered above; non-negotiable for `_load_json` and any test file reads.
- **Exact-keys assertions** — assert the per-indicator objects have *exactly* `{code, name, description}` (no stray `category`), and the response has exactly the 5 contract keys. Both prior reviews rewarded precise shape assertions over loose ones.
- **Don't over-scope** — 5.1 and 5.2 both explicitly fenced off later-story work. Resist implementing `search_local_metadata` or `get_metadata_indicators` here; 5.4 owns them.
- **Load-time / perf assertions are optional and prone to CI flakiness** — NFR13 (<50ms) is trivially met in memory. A timing test is acceptable with a generous margin, but the cache + O(n≤30) grouping makes it a guard, not a benchmark. Prefer asserting correctness over micro-timing.

### Cross-story contract (for Story 5.4 / 5.5)

- Story 5.4 will append `get_metadata_indicators()` and `search_local_metadata()` to this same `indicator_cache.py`, add `_metadata_indicators` singleton state, add the `DATA360_LOCAL_SEARCH_LIMIT` config, and register the `search_local_indicators` tool. Leave the module cleanly extensible (module-level singleton pattern, `_load_json` already generic).
- Story 5.5 will expand `tests/mcp_server/test_indicator_cache.py` into the full Epic 5 suite (relevance scoring, ordering, limit, empty query, plus the popular-indicators tests you write here). Author your test classes so they coexist cleanly with that expansion.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.3] — Acceptance criteria: curated list from `popular_indicators.json`, no API call, standard format, grouped by category, <50ms, singleton caching (FR37, FR40, NFR13)
- [Source: _bmad-output/planning-artifacts/architecture.md#Architecture Addendum: Epics 5-7] — `list_popular_indicators` tool signature + docstring (lines 793–803), `indicator_cache.py` design (`_load_json`, `get_popular_indicators`, lines 973–1015), architectural boundaries (`indicator_cache` is the only JSON reader, lines 1166–1171), implementation sequence step 9–10 (lines 1133–1134)
- [Source: mcp_server/server.py] — Established `@mcp.tool()` async pattern, `try/except` → `{"success": False, "error": ..., "error_type": "api_error"}`, top-level `from mcp_server import config` import, success contract shape
- [Source: mcp_server/popular_indicators.json] — The data file being consumed: dict-wrapped under `"indicators"`, 28 entries, fields `category`/`code`/`name`/`description`, 7 categories
- [Source: _bmad-output/implementation-artifacts/5-1-popular-indicators-data-file.md#Review Findings] — UTF-8 encoding bug, exact-keys assertion guidance, scope-fencing precedent
- [Source: _bmad-output/implementation-artifacts/5-2-metadata-indicators-data-file.md#Dev Notes] — `indicator_cache.py` loader contract, bare-list vs dict-wrap distinction, singleton pattern
- [Source: tests/mcp_server/test_server.py] — Tool-test pattern: direct import + `await`, `mock_client` fixture (not needed here), exact-shape assertions
- [Source: _bmad-output/project-context.md] — Tool response contract, Python 3.12 style rules, testing rules, "no API call in indicator_cache" boundary

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (Claude Opus 4.7, 1M context) via Claude Code dev-story workflow.

### Debug Log References

None — RED → GREEN cycle was clean on first run after creating `indicator_cache.py` and the `list_popular_indicators` tool. No HALT conditions hit.

### Completion Notes List

- Implemented Story 5.3 scope exactly — `indicator_cache.py` contains only the popular-indicators slice (`_load_json` + `_popular_indicators` singleton + `get_popular_indicators()`). Story 5.4's metadata helpers are deliberately deferred.
- `_load_json` uses `encoding="utf-8"` per Dev Notes — `popular_indicators.json` contains em-dashes (e.g. "$3.00 (2021 PPP) — the international (extreme) poverty line") that would crash on non-UTF-8 locales otherwise. UTF-8 also used in the test's direct file read.
- The tool's `data` shape is intentionally a list of `{category, indicators}` group objects (AC3). This is a deliberate, AC-driven deviation from the flat `data` lists the API-backed tools return; it still satisfies the contract (`data` is a list). `total_count` and `returned_count` count **individual indicators** (28), not group count (7) — a `test_counts_reflect_indicators_not_groups` test guards against the group-count bug.
- `get_popular_indicators` extracts the inner list with `data.get("indicators", data) if isinstance(data, dict) else data` — supports both the committed dict-wrapped shape and a hypothetical bare-list shape.
- Tool is registered unconditionally (not under `config.RAG_ENABLED`) and lives between `get_disaggregation` and the RAG block in `server.py`. It does not touch `_client` — verified by the `test_no_api_client_required` test that patches `_client` to `None`.
- 8 new tests added, all passing. Full regression suite: 431 passed, 1 warning (pre-existing pydantic deprecation, unrelated). Ruff lint + format: clean.

### File List

**New:**
- `mcp_server/indicator_cache.py`
- `tests/mcp_server/test_indicator_cache.py`

**Modified:**
- `mcp_server/server.py` (added `indicator_cache` import; added `list_popular_indicators` tool after `get_disaggregation`)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status: ready-for-dev → in-progress → review)
- `_bmad-output/implementation-artifacts/5-3-list-popular-indicators-mcp-tool.md` (status, task checkboxes, Dev Agent Record)

### Change Log

- 2026-05-30: Story 5.3 implemented and marked for review. Added `indicator_cache` module (popular-indicators slice only) and `list_popular_indicators` MCP tool returning category-grouped data. 8 new tests; full regression suite (431 tests) passes; ruff clean.
- 2026-05-30: Code review passed (no patches, no decision-needed). 7 items deferred (project-pattern-consistent or out of scope); 12 dismissed (spec-mandated behavior the context-blind reviewers flagged as bugs). See Review Findings section.

### Review Findings

_Code review 2026-05-30 (bmad-code-review): Blind Hunter + Edge Case Hunter + Acceptance Auditor._

**Triage:** 0 decision-needed · 0 patch · 7 defer · 12 dismissed.

The implementation is faithful to the spec. All 6 ACs satisfied, the UTF-8 critical constraint honored, count-semantics correctly counts indicators (not groups), exact-keys assertions present, scope fence vs Story 5.4 respected. Two cosmetic "deviations" from the auditor (narrowed docstring, `isinstance(data, dict)` guard) are positive — both already documented in Completion Notes.

- [x] [Review][Defer] Singleton race on first load [`mcp_server/indicator_cache.py:25-29`] — deferred, project-pattern-consistent
- [x] [Review][Defer] Blocking file I/O inside async tool (cold call only) [`mcp_server/indicator_cache.py:18`] — deferred, cold-cache only
- [x] [Review][Defer] Malformed JSON shapes propagate via cache [`mcp_server/indicator_cache.py:26-29`] — deferred, requires intentional data corruption
- [x] [Review][Defer] `logger.error` without `exc_info` [`mcp_server/server.py:286`] — deferred, established project pattern across all tools
- [x] [Review][Defer] Cache returns same list reference — no defensive copy [`mcp_server/indicator_cache.py:29`] — deferred, no caller mutates today
- [x] [Review][Defer] Empty `data` not surfaced as "no data found" [`mcp_server/server.py:281-285`] — deferred, convention targets API-backed tools
- [x] [Review][Defer] `groups` dict accumulator recomputed every call [`mcp_server/server.py:266-274`] — deferred, O(28) micro-perf

All defer items also appended to `_bmad-output/implementation-artifacts/deferred-work.md`.
