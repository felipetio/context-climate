# Story 5.1: Popular Indicators Data File

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want a curated JSON file of ~25-30 popular climate and development indicators,
so that the MCP server can offer instant indicator discovery without API calls.

## Acceptance Criteria

1. **Given** the file `mcp_server/popular_indicators.json`
   **When** loaded by the MCP server
   **Then** it contains ~25-30 indicators across 7 categories: Climate & Environment, Energy, Demographics, Economy, Health, Infrastructure, Agriculture & Land Use

2. **Given** each indicator entry in the file
   **When** inspected
   **Then** it has exactly these fields: `category`, `code`, `name`, `description` (all non-empty strings)

3. **Given** the full set of indicators
   **When** the category distribution is measured
   **Then** climate/environment-weighted topics make up at least 40% of indicators (i.e. the combined count of the Climate & Environment, Energy, and Agriculture & Land Use categories is ≥ 40% of all entries)

4. **Given** an indicator `code` field
   **When** compared to the Data360 API convention
   **Then** it is the **short** code (e.g. `EN_ATM_CO2E_KT`), NOT the fully-qualified indicator ID, and maps to a full ID via the `{database}_{code}` convention (e.g. `WB_WDI_EN_ATM_CO2E_KT`)

5. **Given** every `code` in the file
   **When** verified against the live Data360 API (via `search_indicators` or a known WDI lookup)
   **Then** each short code resolves to a real, existing Data360 indicator — no invented or hallucinated codes

6. **Given** the JSON file
   **When** parsed with `json.load`
   **Then** it parses without error and loads in under 100ms

## Tasks / Subtasks

- [x] Task 1: Author `mcp_server/popular_indicators.json` (AC: 1, 2, 3, 4)
  - [x] Use the top-level shape `{"indicators": [ {...}, ... ]}` (see Dev Notes — the Story 5.3 loader reads `data.get("indicators", data)`, so a wrapping `"indicators"` key is the expected schema)
  - [x] Include ~25-30 entries spread across all 7 categories
  - [x] Each entry has exactly `category`, `code`, `name`, `description` (no extra fields, no missing fields)
  - [x] Ensure climate-weighting: Climate & Environment + Energy + Agriculture & Land Use ≥ 40% of entries
  - [x] Use short codes only (e.g. `EN_ATM_CO2E_KT`), never fully-qualified IDs (`WB_WDI_...`)
- [x] Task 2: Verify every indicator code against the live Data360 API (AC: 5)
  - [x] For each code, confirm it resolves to a real indicator (run the MCP server and call `search_indicators`, or query `https://data360api.worldbank.org` directly)
  - [x] Replace any code that does not resolve with a valid equivalent in the same category
  - [x] Record the verification result (which codes were confirmed / swapped) in Completion Notes
- [x] Task 3: Write a validation test in `tests/mcp_server/test_popular_indicators.py` (AC: 1, 2, 3, 6)
  - [x] Load the JSON directly with `json.load` (do NOT depend on `indicator_cache.py` — that module is created in Story 5.3)
  - [x] Assert the file parses and the indicator list length is in the ~25-30 range (assert `20 <= count <= 35` to allow curation latitude)
  - [x] Assert all 7 expected category names are present
  - [x] Assert every entry has exactly the 4 required fields, all non-empty strings
  - [x] Assert codes are short codes (no entry's `code` starts with a known database prefix like `WB_WDI_`)
  - [x] Assert the climate-weighting threshold (≥ 40% in the three climate-related categories)
  - [x] Assert load time < 100ms (time a `json.load` of the file)
- [x] Task 4: Quality gate
  - [x] `uv run ruff check .` and `uv run ruff format --check .` pass
  - [x] `uv run python -m pytest tests/mcp_server/test_popular_indicators.py -v` passes
  - [x] Full regression suite `uv run python -m pytest` passes

## Dev Notes

### Scope boundary (read first)

This story delivers the **data file only** (`mcp_server/popular_indicators.json`) plus a standalone validation test. It does **NOT** create the loader/cache module or any MCP tool:

- `mcp_server/indicator_cache.py` (singleton loader + relevance search) → **Story 5.3 / 5.4**
- `list_popular_indicators` MCP tool (FR37, FR40 caching, <50ms, category grouping) → **Story 5.3**
- `search_local_indicators` + `metadata_indicators.json` → **Story 5.2 / 5.4**

Do not pre-build the loader here. The validation test must read the file directly via `json.load`, so it has no dependency on code that doesn't exist yet.

### File schema (must match the Story 5.3 loader contract)

The planned loader in `indicator_cache.py` (architecture addendum) does:
```python
data = _load_json("popular_indicators.json")
_popular_indicators = data.get("indicators", data)
```
So author the file as a dict with an `"indicators"` list to match the expected shape:
```json
{
  "indicators": [
    {
      "category": "Climate & Environment",
      "code": "EN_ATM_CO2E_KT",
      "name": "CO2 emissions (kt)",
      "description": "Carbon dioxide emissions from the burning of fossil fuels and the manufacture of cement, in kilotons."
    }
  ]
}
```
`data.get("indicators", data)` also tolerates a bare top-level list, but the dict-with-`"indicators"` form is the intended, documented schema — use it.

### Recommended seed list (~28 indicators)

These are real WDI short codes covering all 7 categories with climate weighting at 14/28 = 50% (Climate & Environment + Energy + Agriculture & Land Use). **Task 2 still requires verifying each against the live API** — treat this as a strong starting point, not gospel. Swap any that don't resolve.

**Climate & Environment (6)**
- `EN_ATM_CO2E_KT` — CO2 emissions (kt)
- `EN_ATM_CO2E_PC` — CO2 emissions (metric tons per capita)
- `EN_ATM_GHGT_KT_CE` — Total greenhouse gas emissions (kt of CO2 equivalent)
- `ER_PTD_TOTL_ZS` — Terrestrial and marine protected areas (% of total territorial area)
- `EN_CLC_MDAT_ZS` — Droughts, floods, extreme temperatures (% of population, average)
- `ER_H2O_FWTL_ZS` — Annual freshwater withdrawals, total (% of internal resources)

**Energy (4)**
- `EG_ELC_ACCS_ZS` — Access to electricity (% of population)
- `EG_FEC_RNEW_ZS` — Renewable energy consumption (% of total final energy consumption)
- `EG_ELC_RNEW_ZS` — Renewable electricity output (% of total electricity output)
- `EG_USE_PCAP_KG_OE` — Energy use (kg of oil equivalent per capita)

**Agriculture & Land Use (4)**
- `AG_LND_FRST_K2` — Forest area (sq. km)
- `AG_LND_FRST_ZS` — Forest area (% of land area)
- `AG_LND_AGRI_ZS` — Agricultural land (% of land area)
- `AG_PRD_FOOD_XD` — Food production index (2014-2016 = 100)

**Demographics (4)**
- `SP_POP_TOTL` — Population, total
- `SP_POP_GROW` — Population growth (annual %)
- `SP_URB_TOTL_IN_ZS` — Urban population (% of total population)
- `SP_DYN_LE00_IN` — Life expectancy at birth, total (years)

**Economy (4)**
- `NY_GDP_MKTP_CD` — GDP (current US$)
- `NY_GDP_PCAP_CD` — GDP per capita (current US$)
- `NY_GDP_MKTP_KD_ZG` — GDP growth (annual %)
- `SI_POV_DDAY` — Poverty headcount ratio at $2.15 a day (2017 PPP) (% of population)

**Health (3)**
- `SH_DYN_MORT` — Mortality rate, under-5 (per 1,000 live births)
- `SH_H2O_SMDW_ZS` — People using safely managed drinking water services (% of population)
- `SH_STA_BASS_ZS` — People using at least basic sanitation services (% of population)

**Infrastructure (3)**
- `IT_NET_USER_ZS` — Individuals using the Internet (% of population)
- `IT_CEL_SETS_P2` — Mobile cellular subscriptions (per 100 people)
- `EG_ELC_ACCS_RU_ZS` — Access to electricity, rural (% of rural population)

Note: the architecture's `country_profile` prompt (architecture.md ~line 881) references `EG_FNL_RNEW_ZS` for renewable energy — the canonical WDI code is `EG_FEC_RNEW_ZS`. Verify which the Data360 API actually serves and prefer the resolving one.

### Architecture Compliance

- **Location:** `mcp_server/popular_indicators.json` sits directly in the `mcp_server/` package dir. The Story 5.3 loader resolves it via `DATA_DIR = Path(__file__).parent` (architecture addendum), so the file must be a package sibling of `server.py` / `indicator_cache.py`.
- **No hardcoded values in source code rule** does not apply to a data file — this file IS the data. No env vars needed for 5.1.
- **Short-code convention:** Data360 fully-qualified IDs follow `{database}_{code}` (e.g. `WB_WDI_EN_ATM_CO2E_KT`). `get_data` takes the full `indicator` ID; this file stores the short `code` so a later tool can pair it with a database to form the full ID. Keep the short form. [Source: project-context.md framework rules; epics.md#Story 5.1]
- **Ruff:** JSON is not linted by ruff, but the new test file is — Python 3.12 style, double quotes, line length 120, type hints on any helper.

### Testing Standards

- Tests live in `tests/mcp_server/`, mirroring source structure → new file `tests/mcp_server/test_popular_indicators.py`. [Source: project-context.md testing rules]
- `asyncio_mode = "auto"` is set; this story's tests are synchronous (plain `json.load`) so no async fixtures needed.
- Group tests in a class with AC-referencing docstrings, e.g. `class TestPopularIndicatorsFile:` with `"""AC1: ~25-30 indicators across 7 categories."""`. [Source: project-context.md]
- Resolve the file path in the test via `Path(__file__)` relative navigation or `importlib.resources` — do not hardcode an absolute path.
- For the <100ms load assertion: read+parse the file a few times and assert the parse step stays well under 100ms. Keep the threshold generous to avoid CI flakiness (the file is tiny; this is a guard against accidental bloat, not a tight benchmark).

### Project Structure Notes

- New files only — no edits to `server.py`, `config.py`, or `data360_client.py` in this story.
  - `mcp_server/popular_indicators.json` (NEW)
  - `tests/mcp_server/test_popular_indicators.py` (NEW)
- No new dependencies. `json` and `pathlib` are stdlib.
- `config.py` change `DATA360_LOCAL_SEARCH_LIMIT` mentioned in the architecture addendum belongs to the search tool (Story 5.4), not here.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.1] — Acceptance criteria, category list, climate weighting, short-code convention, <100ms load
- [Source: _bmad-output/planning-artifacts/architecture.md#Architecture Addendum: Epics 5-7] — File location, `indicator_cache.py` loader contract (`data.get("indicators", data)`), `DATA_DIR` resolution
- [Source: _bmad-output/planning-artifacts/prd.md#Offline Indicator Discovery] — FR37–FR40; NFR13 (<50ms search), NFR14 (<500ms load)
- [Source: mcp_server/server.py] — `get_data(database_id, indicator, ...)` shows the full-ID consumer; confirms short-code vs full-ID split
- [Source: mcp_server/rag/embeddings.py] — Reference singleton-cache pattern that Story 5.3's loader will follow (not implemented here)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was straightforward.

### Completion Notes List

- Created `mcp_server/popular_indicators.json` with 28 indicators across all 7 categories using the `{"indicators": [...]}` top-level schema.
- Climate weighting: 14/28 = 50% (Climate & Environment 6 + Energy 4 + Agriculture & Land Use 4) ✓
- **API verification results (queried `https://data360api.worldbank.org/data360/searchv2` with OData filter `series_description/idno eq 'WB_WDI_{code}'`):**
  - 25/28 seed codes confirmed directly.
  - 3 codes from the seed list did NOT resolve under `WB_WDI_*` and were swapped:
    - `EN_ATM_CO2E_KT` → `EN_GHG_CO2_MT_CE_AR5` (CO2 emissions total excl. LULUCF, Mt CO2e)
    - `EN_ATM_CO2E_PC` → `EN_GHG_ALL_PC_CE_AR5` (Total GHG emissions per capita excl. LULUCF)
    - `EN_ATM_GHGT_KT_CE` → `EN_GHG_ALL_MT_CE_AR5` (Total GHG emissions excl. LULUCF, Mt CO2e)
  - All 28 final codes verified against live Data360 API ✓
- Created `tests/mcp_server/test_popular_indicators.py` with 11 test cases covering all ACs (count range, 7 categories, field schema, short-code enforcement, climate weighting, <100ms load time, duplicate-free).
- All 415 tests pass; ruff clean.

### File List

- `mcp_server/popular_indicators.json` (NEW)
- `tests/mcp_server/test_popular_indicators.py` (NEW)

### Review Findings

_Adversarial code review 2026-05-30 (Blind Hunter + Edge Case Hunter + Acceptance Auditor). All 6 ACs PASS — the Acceptance Auditor independently queried the live Data360 API and confirmed all 28 codes resolve under `WB_WDI_*` (AC5 materially satisfied). Findings below are quality/robustness items, not AC failures._

**Patch (unambiguous fixes):**

- [x] [Review][Patch] `SI_POV_DDAY` description misnames the poverty line [mcp_server/popular_indicators.json:133] — Description calls $3.00/2021-PPP "the lower-middle-income poverty line"; $3.00 (2021 PPP) is the World Bank **international/extreme** poverty line (the lower-middle-income line is ~$4.20). Factual error in a journalist-facing tool. The `name` field is correct (mirrors the official API name); only the description gloss is wrong. — ✅ FIXED 2026-05-30: changed gloss to "the international (extreme) poverty line."
- [x] [Review][Patch] Test opens JSON without explicit encoding [tests/mcp_server/test_popular_indicators.py:38,47,53] — `POPULAR_INDICATORS_PATH.open()` relies on the platform default encoding, but the file contains non-ASCII em/en-dashes. On a non-UTF-8 locale `json.load` raises `UnicodeDecodeError`. Pass `encoding="utf-8"`. — ✅ FIXED 2026-05-30: all three `open()` calls now pass `encoding="utf-8"`.
- [x] [Review][Patch] `test_codes_are_short_codes` is a weak/near-tautological guard [tests/mcp_server/test_popular_indicators.py:96-104] — Only rejects three literal prefixes (`WB_WDI_`/`WB_`/`WDI_`), is case-sensitive (`wb_wdi_…` slips through), and never asserts a positive short-code shape, so `""` or `"hello world"` would pass. Also no `code == code.strip()` check (leading/trailing whitespace would break the downstream `{database}_{code}` join). Replace with a positive `re.fullmatch(r"[A-Z]{2}_[A-Z0-9_]+", code)` + strip assertion. (Sources: blind+edge) — ✅ FIXED 2026-05-30: added `code == code.strip()`, case-insensitive prefix check, and positive `SHORT_CODE_PATTERN.fullmatch` assertion.

**Deferred (real but low-priority / by-design for this story):**

- [x] [Review][Defer] AC5 has no automated regression guard [tests/mcp_server/test_popular_indicators.py] — deferred; by design (Task 3 scopes AC 1/2/3/6 only). Code resolution is verified manually + confirmed live today, but a code retired/renamed by Data360 later would not be caught by a green build. Consider a network-gated test in Story 5.3/5.4.
- [x] [Review][Defer] Load-time assertion can flake under CI load [tests/mcp_server/test_popular_indicators.py:44-50] — deferred; single un-warmed `perf_counter` wall-clock sample. Risk is very low (9 KB file, 100 ms budget) and the spec explicitly accepted a generous threshold. Could warm-read once or use median-of-N.
- [x] [Review][Defer] Empty `indicators` list raises `ZeroDivisionError` before a clear message [tests/mcp_server/test_popular_indicators.py:113-119] — deferred; `climate_count / total` divides by zero if the list is emptied, masking the count assertion's message. File is never empty; trivial `assert indicators` guard would fix.
