# Story 1.2: Data360 API Client with Error Handling

Status: review

## Story

As a developer,
I want an async HTTP client that wraps the World Bank Data360 API with retry logic and structured error handling,
so that all MCP tools have a reliable, consistent way to call the API.

## Acceptance Criteria

1. Given a successful API call to any Data360 endpoint, then the client maps Python snake_case parameters to API UPPERCASE parameters (e.g., `database_id` -> `DATABASE_ID`), preserves all API field names exactly (`DATA_SOURCE`, `COMMENT_TS`, `OBS_VALUE`, etc.), and uses `httpx.AsyncClient` with configurable timeout.
2. Given a Data360 API call that returns 429 or 5xx, then it retries with exponential backoff (1s, 2s, 4s, max 3 attempts). If all retries fail, returns `{"success": False, "error": "<message>", "error_type": "api_error"}`.
3. Given a Data360 API call that returns 4xx (not 429), then it does NOT retry and returns a structured error immediately.
4. Given a request returning more than 1000 records, then the client auto-paginates using the `skip` parameter in increments of 1000, stops at 5000 records total, and sets `truncated: True` in the response.
5. Given any API interaction, the client uses `logging.getLogger(__name__)`, logs request/response at DEBUG level, and failures at ERROR level. No `print()` statements.

## Tasks / Subtasks

- [x] Task 1: Implement parameter mapping helper (AC: #1)
  - [x] Create `_map_params(kwargs)` that converts snake_case keys to UPPERCASE
  - [x] Skip `None` values so optional params are omitted
- [x] Task 2: Implement `_request` method with retry logic (AC: #1, #2, #3, #5)
  - [x] Accept method (GET/POST), endpoint path, and params/json body
  - [x] Build full URL from `self.base_url + endpoint`
  - [x] Log request at DEBUG level (method, URL, params)
  - [x] On 429/5xx: retry with exponential backoff (`retry_backoff_base * 2^attempt`), log WARNING on each retry
  - [x] On 4xx (not 429): return structured error immediately, no retry
  - [x] On `httpx.TimeoutException`: return `{"success": False, "error": "...", "error_type": "timeout"}`
  - [x] On `httpx.RequestError` (network): return `{"success": False, "error": "...", "error_type": "api_error"}`
  - [x] On success (2xx): return parsed JSON
  - [x] Log failures at ERROR level
- [x] Task 3: Implement `_paginated_get` method (AC: #4)
  - [x] Accept endpoint and params dict
  - [x] Loop: add `skip` param in increments of `PAGE_SIZE` (1000)
  - [x] Accumulate results until empty page or `MAX_RECORDS` (5000) reached
  - [x] Return `{"success": True, "data": [...], "total_count": N, "returned_count": M, "truncated": bool}`
  - [x] `truncated: True` when stopped by `MAX_RECORDS` cap
- [x] Task 4: Implement public API methods (AC: #1)
  - [x] `async def get(endpoint, **kwargs)` -- single GET request, maps params
  - [x] `async def post(endpoint, **kwargs)` -- single POST request, maps body
  - [x] `async def get_paginated(endpoint, **kwargs)` -- paginated GET, maps params
- [x] Task 5: Write tests (AC: #1-#5)
  - [x] `tests/mcp_server/test_data360_client.py`
  - [x] Test parameter mapping (snake_case -> UPPERCASE, None skipped)
  - [x] Test successful GET/POST returns parsed JSON
  - [x] Test retry on 429 and 503 (verify backoff timing with mock)
  - [x] Test no retry on 400/404
  - [x] Test auto-pagination accumulates results
  - [x] Test pagination truncation at 5000 records
  - [x] Test timeout returns structured error
  - [x] Test network error returns structured error
  - [x] Add fixture files in `tests/mcp_server/fixtures/` (e.g., `data_response.json`, `searchv2_response.json`)

## Dev Notes

### Existing Code to Extend

`mcp_server/data360_client.py` already has the `Data360Client` class skeleton from Story 1.1:
- Constructor with `base_url`, `timeout`, `max_retries`, `retry_backoff_base`
- Lazy `httpx.AsyncClient` behind `asyncio.Lock` in `_get_client()`
- Async context manager (`__aenter__`/`__aexit__`)
- Imports: `asyncio`, `logging`, `httpx`, config values

Add all new methods to this existing class. Do NOT recreate or restructure it.

### Response Format (Mandatory)

```python
# Success (single request)
{"success": True, "data": <parsed_json>}

# Success (paginated)
{"success": True, "data": [...], "total_count": N, "returned_count": M, "truncated": False}

# Error
{"success": False, "error": "Data360 API returned 503: Service Unavailable", "error_type": "api_error"}
# error_type values: api_error | validation_error | timeout | no_data
```

### Parameter Mapping

Only inside `data360_client.py`. Maps snake_case to UPPERCASE:
```python
{"database_id": "WB_WDI", "ref_area": "BRA"}  ->  {"DATABASE_ID": "WB_WDI", "REF_AREA": "BRA"}
```

### Field Name Preservation (Critical)

NEVER rename API response fields. `DATA_SOURCE`, `OBS_VALUE`, `COMMENT_TS`, `TIME_PERIOD`, `LATEST_DATA`, `INDICATOR`, `REF_AREA` must pass through unmutated. This is the citation trust core.

### Retry Backoff Formula

```python
delay = self.retry_backoff_base * (2 ** attempt)  # 1s, 2s, 4s for base=1.0
await asyncio.sleep(delay)
```

### Pagination: `skip` Parameter

The `/data360/data` endpoint uses `skip` for offset pagination. Note: `/data360/searchv2` uses `pageSize`/`pageNumber` instead, but that's handled in Story 1.3 at the tool level.

### Config Values (from config.py)

- `BASE_URL` = `https://data360api.worldbank.org`
- `REQUEST_TIMEOUT` = 30.0 (float)
- `MAX_RETRIES` = 3
- `RETRY_BACKOFF_BASE` = 1.0
- `PAGE_SIZE` = 1000 (fixed)
- `MAX_RECORDS` = 5000 (fixed)

### Testing Approach

- Use `pytest` with `httpx` mocking (consider `respx` or manual `httpx.MockTransport`)
- Add `pytest-asyncio` dev dependency for async test support
- Fixture files: `tests/mcp_server/fixtures/data_response.json` etc.
- Test the client methods directly, not through MCP tools

### Anti-Patterns to Avoid

- Do NOT add `print()` statements, use `logger` only
- Do NOT raise exceptions from public methods, always return structured dict
- Do NOT rename API response fields (e.g., `data_source` instead of `DATA_SOURCE`)
- Do NOT hardcode URLs or magic numbers, use config values
- Do NOT import `PAGE_SIZE`/`MAX_RECORDS` from config at the function-call default level (import at module top)

### Project Structure Notes

```
mcp_server/
  config.py          # Already complete, use PAGE_SIZE and MAX_RECORDS from here
  data360_client.py  # EXTEND this file (skeleton exists)
  server.py          # Do not modify in this story
tests/
  mcp_server/
    test_data360_client.py  # NEW
    fixtures/
      data_response.json    # NEW - sample API response
```

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture > API Client Design]
- [Source: _bmad-output/planning-artifacts/architecture.md#Process Patterns > Retry Strategy]
- [Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns > MCP Tool Response Format]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2]
- [Source: _bmad-output/planning-artifacts/research/technical-context-climate-stack-research-2026-03-23.md]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Implemented `_map_params` static method: snake_case to UPPERCASE with None filtering
- Implemented `_request` with full retry logic: retries on 429/5xx with exponential backoff, no retry on other 4xx, structured error dicts for timeout and network errors
- Implemented `_paginated_get`: auto-pagination via `skip` param, PAGE_SIZE=1000 increments, MAX_RECORDS=5000 cap with truncation flag
- Implemented public API: `get()`, `post()`, `get_paginated()` with automatic param mapping
- Added pytest-asyncio dev dependency for async test support
- 19 tests covering all acceptance criteria (param mapping, retry, no-retry, pagination, truncation, timeout, network error)
- Added fixture files for sample API responses
- All 55 tests pass (19 new + 36 existing), zero regressions

### File List

- mcp_server/data360_client.py (modified)
- tests/mcp_server/test_data360_client.py (new)
- tests/mcp_server/fixtures/data_response.json (new)
- tests/mcp_server/fixtures/searchv2_response.json (new)
- pyproject.toml (modified - added pytest-asyncio)
- uv.lock (modified)
