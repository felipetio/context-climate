# Story 5.2: Metadata Indicators Data File

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want a comprehensive JSON file of ~1500 indicator metadata records,
So that users can search the full indicator catalog offline.

## Acceptance Criteria

1. **Given** the file `mcp_server/metadata_indicators.json`
   **When** loaded by the MCP server
   **Then** it contains ~1500 indicator metadata records extracted from the Data360 API (WB_WDI)

2. **Given** each indicator record in the file
   **When** inspected
   **Then** it has exactly these fields: `code`, `name`, `description`, `source` (all strings). `code`, `name`, and `source` are non-empty; `description` may be an empty string (some WDI indicators have no `definition_long`/`definition_short`).

3. **Given** an indicator `code` field
   **When** compared to the Data360 API convention
   **Then** it is the **short** code (e.g. `SP_POP_TOTL`), NOT the fully-qualified indicator ID (`WB_WDI_SP_POP_TOTL`)

4. **Given** the JSON file
   **When** parsed with `json.load`
   **Then** it is a **bare JSON array** (not a dict), parses without error, and loads in under 500ms (NFR14)

5. **Given** the script `scripts/generate_metadata_indicators.py`
   **When** run with `uv run python scripts/generate_metadata_indicators.py`
   **Then** it regenerates `mcp_server/metadata_indicators.json` from the live Data360 API

## Tasks / Subtasks

- [x] Task 1: Write `scripts/generate_metadata_indicators.py` (AC: 1, 2, 3, 5)
  - [x] Use `POST /data360/searchv2` with `"search": "*"`, `"filter": "series_description/database_id eq 'WB_WDI'"`, paging via `"top": 1000, "skip": 0/1000/...`
  - [x] For each result, extract: short code (`series_description.idno` stripped of `WB_WDI_` prefix), `name` (`series_description.name`), `description` (`definition_long` fallback to `definition_short`, fallback to `""`), `source` (`series_description.database_name`)
  - [x] Collect into a bare list `[{"code": ..., "name": ..., "description": ..., "source": ...}, ...]`
  - [x] Write the list as a JSON array to `mcp_server/metadata_indicators.json` (compact, UTF-8, no extra whitespace inside each record is fine; pretty-printed at top-level for readability is fine too)
  - [x] Script is runnable standalone: `uv run python scripts/generate_metadata_indicators.py` from project root
  - [x] Print progress to stdout (e.g., how many fetched so far) and final count
- [x] Task 2: Run the script to generate `mcp_server/metadata_indicators.json` (AC: 1, 2, 3, 4)
  - [x] Run `uv run python scripts/generate_metadata_indicators.py` and verify it completes
  - [x] Confirm the generated file has at least 500 records (WDI typically has ~1400)
  - [x] Confirm all records have all 4 fields, all non-empty
  - [x] Confirm codes are short codes (no `WB_WDI_` prefix)
- [x] Task 3: Write validation tests in `tests/mcp_server/test_metadata_indicators.py` (AC: 2, 3, 4)
  - [x] Load the JSON directly with `json.load(open(..., encoding="utf-8"))` (do NOT depend on `indicator_cache.py` — that module is created in Story 5.3)
  - [x] Assert the parsed result is a list (not a dict)
  - [x] Assert count is in a generous range (assert `500 <= count <= 3000`) to allow API catalog variation
  - [x] Assert every entry has **exactly** the 4 required keys (`code`, `name`, `description`, `source`), all non-empty strings
  - [x] Assert codes are short codes — use positive regex `re.fullmatch(r"[A-Z][A-Z0-9_]+", code)` AND assert `code == code.strip()` AND case-insensitive assert `not code.upper().startswith("WB_")`
  - [x] Assert no duplicate codes
  - [x] Assert load time < 500ms (time a `json.load` of the file; single sample is fine given the generous budget)
- [x] Task 4: Quality gate
  - [x] `uv run ruff check .` and `uv run ruff format --check .` pass
  - [x] `uv run python -m pytest tests/mcp_server/test_metadata_indicators.py -v` passes
  - [x] Full regression suite `uv run python -m pytest` passes

### Review Findings

_Code review 2026-05-30 (Blind Hunter + Edge Case Hunter + Acceptance Auditor). Quality gate verified clean: ruff ✓, 8/8 tests pass, 1533 records, 0 empty descriptions, 0 dup codes._

- [x] [Review][Decision→Patch] Script and test/AC2 disagreed on empty `description`. **Resolved (option 2): relaxed AC2 and the test to allow an empty `description`.** AC2 now requires only `code`/`name`/`source` non-empty; `description` may be empty. `test_all_fields_are_non_empty_strings` renamed to `test_all_fields_are_strings` — all four must be strings, only `code`/`name`/`source` must be non-empty (`NON_EMPTY_FIELDS`). [blind+edge+auditor] [tests/mcp_server/test_metadata_indicators.py:65-74]
- [x] [Review][Patch] Hardened script guards to match the test invariants [scripts/generate_metadata_indicators.py:48-66] — code/name/source now `.strip()`-ed; record skipped (with a printed warning) when the code is empty, still `WB_`-prefixed, or fails `SHORT_CODE_PATTERN`, and when name/source are empty after stripping. The script can no longer emit a record its own tests reject. [blind+edge]
- [x] [Review][Patch] Guard against overwriting the committed file with an empty result [scripts/generate_metadata_indicators.py] — `main()` now aborts via `SystemExit` when `len(records) < MIN_EXPECTED_RECORDS` (500), refusing to clobber the committed file with a likely-incomplete run. [edge]
- [x] [Review][Defer] Pagination relies on `len(batch) < PAGE_SIZE` and ignores the requested `count` [scripts/generate_metadata_indicators.py:38,71-74] — a short non-final page would terminate paging early and silently truncate the catalog. Deferred: manual run prints progress/total so under-fetch is observable; current data is complete. [blind+edge]
- [x] [Review][Defer] No retry/backoff on transient API errors mid-pagination [scripts/generate_metadata_indicators.py:40-41] — a single 429/5xx aborts the run. Deferred: standalone manual script (scope forbids importing the client's retry); the write only happens after a full successful fetch, so no partial-file corruption. [blind+edge]
- [x] [Review][Defer] No post-fetch assertion that every record belongs to `WB_WDI` [scripts/generate_metadata_indicators.py:33-35] — if the server-side filter were ignored, non-WDI records would be written undetected. Deferred: the `search:"*"`+filter pattern is proven in `data360_client.resolve_db_name`; low risk. [blind]
- Dismissed (6): positive short-code regex doesn't itself distinguish short from fully-qualified codes (AC3 still enforced by the combined `not startswith("WB_")` + strip + shape checks); non-atomic file write (manual script, git-recoverable); 500ms load-time test "flakiness" (validates a real NFR with a large margin — loads in ~0.14s); tests reparse the file per method (perf nit); OData filter f-string (interpolates a hardcoded constant, not user input); count bounds 500–3000 "too wide" (intentional per spec to allow catalog drift).

## Dev Notes

### Scope boundary (read first)

This story delivers **two** artifacts:
1. `mcp_server/metadata_indicators.json` — the data file committed to the repo
2. `scripts/generate_metadata_indicators.py` — the regeneration script committed alongside it

It does **NOT** create the loader/cache module or any MCP tool:
- `mcp_server/indicator_cache.py` (singleton loader + relevance search) → **Story 5.3 / 5.4**
- `search_local_indicators` + `list_popular_indicators` MCP tools → **Story 5.3 / 5.4**

The test must read the file directly via `json.load`, with **no dependency** on `indicator_cache.py` (it doesn't exist yet).

### File schema — critical: bare list, not a dict

**`metadata_indicators.json` must be a bare JSON array**, unlike `popular_indicators.json` which uses a dict wrapper:

```json
[
  {
    "code": "SP_POP_TOTL",
    "name": "Population, total",
    "description": "Total population is based on the de facto definition ...",
    "source": "World Development Indicators (WDI)"
  },
  ...
]
```

The Story 5.3 loader in `indicator_cache.py` (architecture addendum) does:
```python
def get_metadata_indicators() -> list[dict]:
    global _metadata_indicators
    if _metadata_indicators is None:
        _metadata_indicators = _load_json("metadata_indicators.json")
    return _metadata_indicators
```

There is **no `.get("indicators", data)` call** here (compare: `popular_indicators.json` uses `data.get("indicators", data)`). The `_load_json` return value is assigned directly to a `list[dict]`. If the file is a dict, `get_metadata_indicators()` returns a dict where a list is expected — the Story 5.3/5.4 tools will break silently.

**DO NOT wrap the array in a dict. The file MUST be a bare JSON array.**

### Short code extraction

Data360 fully-qualified IDs follow `{database_id}_{short_code}`:
- `WB_WDI_SP_POP_TOTL` → strip `WB_WDI_` → `SP_POP_TOTL`
- `WB_WDI_EN_GHG_CO2_MT_CE_AR5` → strip `WB_WDI_` → `EN_GHG_CO2_MT_CE_AR5`

Extraction logic in the script:
```python
idno = sd["idno"]           # e.g. "WB_WDI_SP_POP_TOTL"
db_id = sd["database_id"]   # e.g. "WB_WDI"
code = idno.removeprefix(f"{db_id}_")  # e.g. "SP_POP_TOTL"
```

This pattern generalises if the script is ever extended to cover other databases (WB_HNP etc.).

### Description field mapping

`definition_long` is preferred; `definition_short` is the fallback; empty string if both are absent/null:

```python
description = sd.get("definition_long") or sd.get("definition_short") or ""
```

Some WDI indicators have `definition_short: null` and `definition_long: null` — handle gracefully (empty string is acceptable per AC 2, but you may want to log a warning for these).

### Regeneration script — API approach

The `data360_client.py` `resolve_db_name` method proves `"search": "*"` works with a database filter:
```python
body = {"search": "*", "filter": f"series_description/database_id eq '{database_id}'", "top": 1}
```

Use this same pattern in the generation script, paginating with `"skip"`:

```python
import asyncio
import json
from pathlib import Path
import httpx

BASE_URL = "https://data360api.worldbank.org"
DATABASE_ID = "WB_WDI"
OUTPUT_PATH = Path(__file__).parent.parent / "mcp_server" / "metadata_indicators.json"

async def fetch_all() -> list[dict]:
    records = []
    skip = 0
    top = 1000
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            body = {
                "search": "*",
                "filter": f"series_description/database_id eq '{DATABASE_ID}'",
                "top": top,
                "skip": skip,
                "count": True,
            }
            resp = await client.post(f"{BASE_URL}/data360/searchv2", json=body)
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("value", [])
            if not batch:
                break
            for item in batch:
                sd = item.get("series_description", {})
                idno = sd.get("idno", "")
                db_id = sd.get("database_id", DATABASE_ID)
                code = idno.removeprefix(f"{db_id}_")
                records.append({
                    "code": code,
                    "name": sd.get("name", ""),
                    "description": sd.get("definition_long") or sd.get("definition_short") or "",
                    "source": sd.get("database_name", ""),
                })
            print(f"Fetched {len(records)} records so far...")
            skip += top
            if len(batch) < top:
                break
    return records

if __name__ == "__main__":
    records = asyncio.run(fetch_all())
    print(f"Total: {len(records)} records")
    OUTPUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written to {OUTPUT_PATH}")
```

This is a blueprint — the actual script should follow this pattern. Key points:
- Standalone: no imports from `mcp_server.*` (so it can be run without the package context)
- Async with `asyncio.run`
- Uses `httpx.AsyncClient` directly (httpx is already a project dependency)
- Breaks out of the loop when `len(batch) < top` (last page)
- Writes with `ensure_ascii=False` so non-ASCII characters (em-dash in names etc.) are preserved
- UTF-8 encoding explicitly set

### Architecture compliance

- **Location:** `mcp_server/metadata_indicators.json` sits directly in the `mcp_server/` package dir, alongside `popular_indicators.json`. The Story 5.3 loader resolves it via `DATA_DIR = Path(__file__).parent`.
- **Script location:** `scripts/` at project root — this directory does not exist yet; create it.
- **No changes to existing files:** `server.py`, `config.py`, `data360_client.py` — no edits in this story.
- **No new package dependencies** — `httpx` is already in `pyproject.toml`; `asyncio`, `json`, `pathlib` are stdlib.
- **`config.py` change `DATA360_LOCAL_SEARCH_LIMIT`** — belongs to Story 5.4, not here.

### Ruff compliance for the script

The script at `scripts/generate_metadata_indicators.py` IS linted by ruff. Follow the same style as the rest of the project:
- Python 3.12+: use `X | Y` not `Optional[X]`, type hints on all function signatures
- Double quotes, line length 120, imports sorted (stdlib, then third-party)

Add `# scripts/ path` entry to ruff's `exclude` config if needed — but typically `scripts/` is not excluded. Just keep the code clean.

### Testing standards

- Tests live in `tests/mcp_server/test_metadata_indicators.py`, mirroring the source structure.
- Group tests in `class TestMetadataIndicatorsFile:` with AC-referencing docstrings (e.g. `"""AC1: ~1500 records from Data360 API"""`).
- Resolve the file path via `Path(__file__)` relative navigation — not an absolute path.
- Load with explicit `encoding="utf-8"` (the file contains non-ASCII characters):
  ```python
  with METADATA_INDICATORS_PATH.open(encoding="utf-8") as f:
      indicators = json.load(f)
  ```
- The `asyncio_mode = "auto"` setting is in `pyproject.toml`; these tests are synchronous, so no async fixtures needed.

### Cross-story contract

Story 5.3 (`indicator_cache.py`) will depend on this file. The exact contract:
```python
# indicator_cache.py (Story 5.3) does:
def get_metadata_indicators() -> list[dict]:
    global _metadata_indicators
    if _metadata_indicators is None:
        _metadata_indicators = _load_json("metadata_indicators.json")  # expects bare list
    return _metadata_indicators
```

And `search_local_metadata` (Story 5.4) reads from this list using keys `"code"`, `"name"`, `"description"`, `"source"`. Any field name deviation here will silently break searches in Story 5.4.

### Previous story learnings (from Story 5.1)

The 5.1 code review found these issues that apply here too:

- **Encoding:** Always open files with `encoding="utf-8"`. The 5.1 review found that `open()` without encoding fails in non-UTF-8 locale when the JSON has non-ASCII characters. The metadata file will have non-ASCII characters (indicator names with accents, em-dashes, etc.) — use `encoding="utf-8"` everywhere.
- **Short-code validation in tests:** Use a **positive regex** pattern (e.g. `re.fullmatch(r"[A-Z][A-Z0-9_]+", code)`) in addition to a negative prefix check. The 5.1 review found that prefix-only checks are near-tautological and miss edge cases.
- **Strip check:** Always assert `code == code.strip()` — whitespace in codes would break the downstream `{database_id}_{code}` join.
- **Zero-division guard:** If your test computes a ratio (e.g. climate_count / total), add `assert indicators` before the division to get a clean failure message if the list is empty.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.2] — Acceptance criteria, ~1500 records, `code/name/description/source` fields, 500ms load, regeneration script
- [Source: _bmad-output/planning-artifacts/architecture.md#Architecture Addendum: Epics 5-7] — `indicator_cache.py` loader contract, `DATA_DIR` resolution, bare-list expectation vs dict-wrap in popular_indicators
- [Source: mcp_server/data360_client.py:200-201] — Proof that `"search": "*"` + filter works against Data360 searchv2
- [Source: tests/mcp_server/fixtures/searchv2_response.json] — Full shape of searchv2 API response (series_description fields: idno, database_id, database_name, name, definition_short, definition_long)
- [Source: tests/mcp_server/fixtures/metadata_response.json] — Confirms `definition_short` can be null; `definition_long` is the preferred field
- [Source: _bmad-output/implementation-artifacts/5-1-popular-indicators-data-file.md#Review Findings] — encoding issue, positive regex for codes, strip check learnings

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Script failed on first run with `AttributeError: 'NoneType' has no attribute 'removeprefix'` — `series_description` or `idno` can be null in some API records. Fixed by using `or` fallback: `sd.get("idno") or ""` and `sd.get("series_description") or {}`.

### Completion Notes List

- Created `scripts/generate_metadata_indicators.py` — standalone async script using `POST /data360/searchv2` with `"search": "*"` + `database_id eq 'WB_WDI'` filter, paginating in batches of 1000. Handles null `series_description` fields gracefully.
- Generated `mcp_server/metadata_indicators.json` — **1533 WB_WDI records**, bare JSON array (not dict-wrapped). All records have non-empty `code`, `name`, `description`, `source`. Verified: 0 records with empty description.
- Short code extraction: `idno.removeprefix(f"{db_id}_")` (e.g. `WB_WDI_SP_POP_TOTL` → `SP_POP_TOTL`). Pattern is general — works for any database.
- Created `tests/mcp_server/test_metadata_indicators.py` with 8 tests covering: file existence, bare-list structure, 500ms load time, count range (500–3000), exact field schema, all non-empty strings, short-code shape (positive regex + strip + no `WB_` prefix), no duplicate codes.
- One ruff fix applied: extracted `code_hint` variable to keep assertion message line under 120 chars.
- All 423 tests pass (415 pre-existing + 8 new), ruff clean.

### File List

- `mcp_server/metadata_indicators.json` (NEW)
- `scripts/generate_metadata_indicators.py` (NEW)
- `tests/mcp_server/test_metadata_indicators.py` (NEW)

### Change Log

- Implemented Story 5.2: metadata indicators data file (2026-05-30)
