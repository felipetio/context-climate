---
project_name: 'context-climate'
user_name: 'Felipe'
date: '2026-03-26'
sections_completed:
  ['technology_stack', 'language_rules', 'framework_rules', 'citation_integrity', 'tool_response_contract', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 43
optimized_for_llm: true
---

# Project Context for AI Agents

_Critical rules and patterns AI agents must follow when implementing code in this project. Focused on unobvious details that agents commonly miss._

---

## Technology Stack & Versions

- Python 3.12+
- FastMCP 3.1.1+ — MCP server framework (lifespan, tool registration, transport)
- httpx 0.28.1+ — async HTTP client (AsyncClient, timeout, retry)
- python-dotenv 1.2.2+ — env config via `.env` file
- pytest 9.0.2+ + pytest-asyncio 1.3.0+ — test runner (`asyncio_mode = "auto"`)
- ruff 0.15.7+ — linting (E/F/W/I) + formatting, line-length 120
- pre-commit 4.5.1+ — enforces ruff on commit

## Critical Implementation Rules

### Language-Specific Rules

- Target Python 3.12+; use `X | Y` union syntax — never `Optional[X]` or `Union[X, Y]`
- All I/O methods must be `async`; no blocking calls inside tool handlers
- Type hints required on all function signatures; use `dict[str, Any]` not `Dict`
- Double quotes enforced by ruff; line length 120

### Framework-Specific Rules

- All tools registered via `@mcp.tool()` on the module-level `mcp = FastMCP(...)` instance
- `_client: Data360Client | None` is a **module-level singleton** — never instantiate per-request
  - Required so `_db_name_cache` persists across tool calls for `CITATION_SOURCE` enrichment
- `Data360Client` lifecycle managed by `_lifespan` async context manager — always `await _client.close()` on teardown
- Transport controlled by `MCP_TRANSPORT` env var (`stdio` | `streamable-http`); tools are transport-agnostic
- API param mapping: use `Data360Client._map_params()` for snake_case → UPPERCASE conversion
  - **camelCase exceptions — pass these directly, NOT through `_map_params()`:**
    `timePeriodFrom`, `timePeriodTo`, `datasetId`, `indicatorId`
- Pagination: `_paginated_get()` auto-pages at PAGE_SIZE=1000, caps at MAX_RECORDS=5000

### Citation Integrity Rules

- `DATA_SOURCE` field from API response must **never** be modified or removed
- Always call `await _client.enrich_citation_source(result["data"])` after any `get_data` response
- `CITATION_SOURCE` enrichment logic: `DATA_SOURCE` (if present) → `_db_name_cache[DATABASE_ID]` → `DATABASE_ID` string
- Call `_client.cache_db_names(results)` after `search_indicators` to populate the name cache for future enrichment
- Downstream code (Epic 3+) must use `CITATION_SOURCE`, not `DATA_SOURCE`, for citation display

### Tool Response Contract

All tools MUST return one of exactly two shapes:

**Success:**
```python
{"success": True, "data": [...], "total_count": int, "returned_count": int, "truncated": bool}
```

**Error:**
```python
{"success": False, "error": str, "error_type": "api_error" | "timeout"}
# Only "api_error" and "timeout" are used. Values like "no_data" or "validation_error"
# appear in older planning artifacts but were never implemented — treat them as obsolete.
```

- Never return empty `data` list without explicit "no data found" logging
- `truncated=True` when `total_count > returned_count`

### Testing Rules

- Tests in `tests/mcp_server/` mirror source structure
- `asyncio_mode = "auto"` in pyproject.toml — `@pytest.mark.asyncio` is redundant but acceptable
- Group tests in classes: `class TestToolName:` with docstrings referencing AC numbers (e.g., `"""AC1: ..."""`)
- JSON fixtures in `tests/mcp_server/fixtures/` — load via `_load_fixture("name.json")`
- Mock the module-level singleton by patching `mcp_server.server._client`:
  ```python
  with patch("mcp_server.server._client", instance):
  ```
- Always preserve real `_map_params` on mocks so param mapping assertions work:
  ```python
  instance._map_params = Data360Client._map_params
  ```
- Tests in `test_data360_client.py` mock the httpx client — no real API calls are made

### Code Quality & Style Rules

- Run `uv run ruff check .` and `uv run ruff format .` before every commit (pre-commit enforces)
- Never add `# noqa` or `# fmt: off` without explicit approval
- Ruff excludes `.claude/` and `_bmad/` — do not add rules targeting those paths
- All config via env vars with defaults in `config.py` — no hardcoded URLs, timeouts, or limits in source code

### Development Workflow Rules

- Always run with `uv run` — never call `python` directly
- Branch naming: `story/{{story_key}}` for story work; `feat/`, `fix/`, `chore/` otherwise
- Commit format: `feat(story-key): description` for story branches
- Story branches → PR → GitHub Copilot review → `/bmad-code-review` → merge

### RAG Module Rules (when DATA360_RAG_ENABLED=true)

- RAG tools (`search_documents`, `list_documents`) only registered when `DATA360_RAG_ENABLED=true`
- Embedding model loaded once at startup via singleton pattern (same approach as `_db_name_cache`)
- Document citations use `CITATION_SOURCE` field following existing pattern: `"{filename} (uploaded {date}), p. {page}"`
- Never store raw file content in pgvector, only chunked text + embeddings
- Vector search uses pgvector `<=>` cosine distance operator (lower = more similar); convert to similarity score (`1 - distance`) before applying `min_score` thresholds
- All RAG config via `DATA360_RAG_*` env vars in `config.py`, no hardcoded values
- RAG module lives in `mcp_server/rag/` (embeddings.py, chunker.py, store.py, processor.py)

### Citation Pipeline Rules (Server-Side Registry)

- Citations are pipeline-guaranteed: `app/citations.py` builds a structured citation registry from MCP tool responses server-side
- The LLM's only citation responsibility is placing `[n]` markers in prose — it does NOT generate the reference list
- `app/citations.py` handles: extraction from tool responses, deduplication (one ref per database+indicator), IEEE-light formatting
- `app/prompts.py` contains the system prompt with grounding boundary and citation marker instructions — keep decoupled from `app/chat.py`
- The `references: list[dict]` is attached to Chainlit message metadata for downstream UI consumption (Epic 9)
- Each reference entry: `id`, `source`, `indicator_code`, `indicator_name`, `database_id`, `years`, `type` ("api" | "document")
- Document references additionally include: `filename`, `upload_date`, `page`/`chunk` fields
- Reference list title adapts to conversation language ("References", "Referências", "Referencias")
- If a response has no data points (clarification, "no data found"), no reference list is appended

### Critical Anti-Patterns (Never Do)

- **DON'T** recreate `Data360Client` per tool call — breaks `_db_name_cache` across calls
- **DON'T** pass `timePeriodFrom`/`timePeriodTo` through `_map_params()` — API rejects `TIMEPERIODFROM`
- **DON'T** mutate `DATA_SOURCE` — always add `CITATION_SOURCE` as a separate field
- **DON'T** return empty `data` silently — always surface "no data found" explicitly
- **DON'T** use `Optional[X]` or `Union[X, Y]` — use `X | None` and `X | Y`
- **DON'T** add `# noqa` without approval
- **DON'T** construct OData filters with unvalidated strings — use `re.fullmatch(r"[A-Za-z0-9_]+", ...)` to prevent injection
- **DON'T** import sentence-transformers at module level — lazy-load behind `DATA360_RAG_ENABLED` feature flag
- **DON'T** process uploads synchronously in the message handler — use async
- **DON'T** store embeddings without source metadata (filename, page, chunk index)
- **DON'T** skip the feature flag check when registering RAG tools
- **DON'T** let the LLM generate the reference list — the server appends it via `app/citations.py`
- **DON'T** put system prompt text in `app/chat.py` — it belongs in `app/prompts.py`

---

## Usage Guidelines

**For AI Agents:** Read this file before implementing any code. Follow all rules exactly. When in doubt, prefer the more restrictive option.

**For Humans:** Keep lean and focused. Update when tech stack or patterns change.

Last Updated: 2026-04-02
