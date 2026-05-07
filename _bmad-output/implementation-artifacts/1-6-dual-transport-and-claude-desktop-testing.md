# Story 1.6: Dual Transport and Claude Desktop Testing

Status: review

## Story

As a developer,
I want the MCP server to work via both stdio (Claude Desktop) and HTTP Streamable (production) transports,
so that I can test locally in Claude Desktop and deploy for web access without code changes.

## Acceptance Criteria

1. **Given** the MCP server with all 5 tools implemented, **When** running `fastmcp dev mcp_server/server.py`, **Then** the MCP Inspector opens and all 5 tools are visible and callable.

2. **Given** the MCP server configured for stdio transport, **When** installed via `fastmcp install mcp_server/server.py`, **Then** Claude Desktop can use all 5 tools to query World Bank data end-to-end.

3. **Given** the MCP server configured for HTTP Streamable transport, **When** started in HTTP mode, **Then** the server accepts MCP client connections over HTTP and all 5 tools work identically to stdio mode.

4. **Given** any transport mode, **When** tools are called, **Then** tool logic is identical, only the transport layer differs (handled by FastMCP), and NFR12 (transport-agnostic) is satisfied.

## Tasks / Subtasks

- [x] Task 1: Verify MCP Inspector (AC: #1)
  - [x] Run `uv run fastmcp dev mcp_server/server.py` and confirm all 5 tools are listed: `search_indicators`, `get_data`, `get_metadata`, `list_indicators`, `get_disaggregation`
  - [x] Call each tool once via Inspector with valid parameters, confirm structured response

- [x] Task 2: Enable HTTP Streamable transport (AC: #3, #4)
  - [x] Add `__main__` block to `mcp_server/server.py` with transport flag support via env var `MCP_TRANSPORT` (default: `stdio`)
  - [x] Verify `uv run python -m mcp_server.server` starts in stdio mode
  - [x] Verify `MCP_TRANSPORT=streamable-http uv run python -m mcp_server.server` starts HTTP listener on port 8000 (default)
  - [x] Confirm all 5 tools reachable via HTTP transport

- [x] Task 3: Claude Desktop installation and end-to-end test (AC: #2)
  - [x] Run `uv run fastmcp install claude-desktop mcp_server/server.py --name "Context Climate" --with-editable .` (note: FastMCP 3.1.1 CLI changed to subcommand style; --with-editable required for local mcp_server package)
  - [x] Confirm entry appears in Claude Desktop MCP settings (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS)
  - [x] Restart Claude Desktop and verify tools listed in tool panel
  - [x] Run end-to-end query: ask Claude to search for a CO2 indicator and retrieve data for Brazil — confirm response includes `DATA_SOURCE`/`CITATION_SOURCE` field

- [x] Task 4: Add `__init__.py` module entrypoint for `-m mcp_server.server` invocation (AC: #3)
  - [x] Confirm `mcp_server/__init__.py` exists (it does from Story 1.1)
  - [x] Confirm `mcp_server/server.py` works as `python -m mcp_server.server` — add `if __name__ == "__main__": mcp.run()` if missing

## Dev Notes

### Current State

All 5 tools are fully implemented in `mcp_server/server.py`. The `FastMCP` instance is:

```python
mcp = FastMCP("context-climate", instructions="World Bank Data360 climate and development data tools.")
```

There is NO `if __name__ == "__main__"` block yet. FastMCP's CLI (`fastmcp dev`, `fastmcp install`) handles stdio mode already. HTTP transport requires either:
- `fastmcp run mcp_server/server.py --transport streamable-http` via CLI, OR
- A `__main__` block in server.py reading `MCP_TRANSPORT` env var

**Architecture decision:** FastMCP handles transport switching via config flag — no tool logic changes needed. [Source: architecture.md — "FastMCP handles dual transport (stdio/HTTP Streamable) via config flag, no code changes needed"]

### HTTP Transport Implementation

Add to the bottom of `mcp_server/server.py`:

```python
if __name__ == "__main__":
    import os
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
```

FastMCP 3.1.1 `mcp.run()` accepts transport values: `"stdio"`, `"streamable-http"`. For HTTP mode, it defaults to port 8000 unless `MCP_PORT` is set.

### fastmcp install Behavior

`fastmcp install mcp_server/server.py` writes a config entry to Claude Desktop's config file. On macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`. It sets up stdio transport automatically — Claude Desktop spawns the server as a subprocess per session.

Optionally pass `--name "Context Climate"` to set a human-readable name in the UI.

### Environment Variables (all optional, have sensible defaults)

| Variable | Default | Purpose |
|---|---|---|
| `DATA360_BASE_URL` | `https://data360api.worldbank.org` | API base URL |
| `DATA360_REQUEST_TIMEOUT` | `30.0` | HTTP timeout in seconds |
| `DATA360_MAX_RETRIES` | `3` | Retry attempts on transient errors |
| `DATA360_RETRY_BACKOFF_BASE` | `1.0` | Exponential backoff base (seconds) |
| `MCP_TRANSPORT` | `stdio` | Transport mode for `__main__` block |

No API keys required — World Bank Data360 is a public API.

### Key Learnings from Story 1.5

- `mcp_server/server.py` currently has no `__main__` entrypoint; only FastMCP CLI commands work
- Fixture pattern for tests: `mock_client` fixture in `tests/mcp_server/test_server.py`
- 93 tests passing as of Story 1.5 — do NOT break them
- Citation source enrichment (`enrich_citation_source`) is in `data360_client.py` and called by `get_data` — this flows transparently across transports

### Files to Touch

- `mcp_server/server.py` — add `__main__` block and wire/configure lifespan context manager (no tool logic changes)
- Possibly `tests/mcp_server/test_server.py` — no new unit tests required; transport is FastMCP's concern
- `CLAUDE.md` or README — update with HTTP transport command if desired (out of scope for this story)

### Anti-Patterns to Avoid

- **Do NOT** add transport-specific logic inside tool functions — transport is purely FastMCP's layer
- **Do NOT** duplicate tool registration or create a second FastMCP instance for HTTP mode
- **Do NOT** introduce or rely on a module-level `_client = Data360Client()` — the client is lifespan-managed in `_lifespan` and shared across transports via that mechanism
- **Do NOT** add a new config.py setting for transport — env var in `__main__` is sufficient

### Project Structure Notes

Relevant files (no new files needed):
```
mcp_server/
  server.py       ← add __main__ block
  data360_client.py  (no changes)
  config.py          (no changes)
tests/mcp_server/
  test_server.py     (no changes expected)
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 1, Story 1.6]
- [Source: _bmad-output/planning-artifacts/architecture.md — "API & Communication Patterns", "Development Workflow"]
- [Source: _bmad-output/implementation-artifacts/1-5-get-metadata-list-indicators-and-get-disaggregation-mcp-tools.md — Dev Notes]
- [Source: mcp_server/server.py — current implementation]
- [Source: pyproject.toml — fastmcp>=3.1.1]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- FastMCP 3.1.1 CLI changed from `fastmcp install <file>` to `fastmcp install claude-desktop <file>` subcommand style
- `fastmcp install` without `--with-editable .` causes `ModuleNotFoundError: No module named 'mcp_server'` in Claude Desktop — fixed by adding `--with-editable .`
- `.venv/bin/fastmcp` shebang was broken (pointing to old project path `/word-bank-challenge`); fixed via `uv run --reinstall fastmcp --version`

### Completion Notes List

- Added `if __name__ == "__main__"` block to `mcp_server/server.py` reading `MCP_TRANSPORT` env var (default: `stdio`), enabling `python -m mcp_server.server` and HTTP Streamable mode
- Added lifespan context manager to properly initialize and close `Data360Client` (httpx client cleanup on shutdown)
- Verified all 5 tools register correctly via FastMCP's async `list_tools()` and via Claude Desktop end-to-end test
- Both transports confirmed working: stdio starts correctly, `MCP_TRANSPORT=streamable-http` starts HTTP server on `http://127.0.0.1:8000/mcp`
- Claude Desktop installed via `fastmcp install claude-desktop ... --with-editable .`; config entry confirmed in `claude_desktop_config.json`; end-to-end test passed
- 111 tests pass, no regressions

### File List

- `mcp_server/server.py` (modified — added lifespan context manager, `__main__` block)

## Change Log

- 2026-03-25: Added `__main__` block with `MCP_TRANSPORT` env var support; added lifespan context manager for proper httpx client lifecycle; fixed `fastmcp` CLI shebang; installed to Claude Desktop with `--with-editable .`; all transports verified end-to-end; 111 tests passing
