# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A conversational AI tool that enables querying World Bank climate and development data with verified citations. Built using FastMCP and httpx, it supports dual transport modes: stdio for Claude Desktop integration and HTTP Streamable for web UI (Chainlit, planned).

This project was developed using the BMAD methodology.


## Commands

```bash
# Start PostgreSQL (required for Chainlit conversation persistence)
docker compose up -d

# Run all tests
uv run python -m pytest

# Run a single test file
uv run python -m pytest tests/mcp_server/test_project_setup.py -v

# Run MCP server in dev mode (opens MCP Inspector)
uv run fastmcp dev mcp_server/server.py

# Run server in stdio mode (default)
uv run python -m mcp_server.server

# Run server in HTTP Streamable mode (port 8001)
MCP_TRANSPORT=streamable-http uv run python -m mcp_server.server

# Install to Claude Desktop
uv run fastmcp install claude-desktop mcp_server/server.py --name "Context Climate" --with-editable .

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --group dev <package>

# Lint check
uv run ruff check .

# Format check
uv run ruff format --check .

# Auto-fix lint issues
uv run ruff check --fix .

# Auto-format
uv run ruff format .

# Install pre-commit hooks (first time setup)
uv run pre-commit install

# Run pre-commit on all files
uv run pre-commit run --all-files
```

## Code Quality

- All code must pass `uv run ruff check .` and `uv run ruff format .` — pre-commit hooks enforce this automatically.
- Never add `# noqa` or `# fmt: off` without explicit approval.
- Ruff config is in `pyproject.toml`: line length 120, rules E/F/W/I (isort).

## Architecture

```
mcp_server/
  config.py          # ENV-based config with defaults (DATA360_* vars)
  data360_client.py  # Async httpx client: param mapping, pagination, retry, citation enrichment
  server.py          # FastMCP server instance, lifespan, and tool definitions
app/                 # Web application (planned, Epic 2+)
  chat.py            # Chainlit handlers, agentic loop
  citations.py       # Citation registry pipeline (extraction, dedup, formatting)
  prompts.py         # System prompt for LLM grounding and citation markers
  config.py          # Web app settings and environment variables
```

**Data flow:** World Bank Data360 API -> Data360Client -> MCP tools -> Claude Desktop / Chainlit

**MCP Tools (5 implemented):**
- `search_indicators` — full-text search via `/data360/searchv2` (POST)
- `get_data` — paginated data fetch via `/data360/data` with citation enrichment
- `get_metadata` — OData metadata queries via `/data360/metadata`
- `list_indicators` — list all indicators for a dataset via `/data360/indicators`
- `get_disaggregation` — dimension/disaggregation info via `/data360/disaggregation`

**Key design decisions:**
- Citation integrity: `DATA_SOURCE` flows unmutated from API response; non-WDI databases get `CITATION_SOURCE` enriched from cached DB metadata. In the web app, citations are pipeline-guaranteed: `app/citations.py` builds a server-side registry from tool responses; the LLM only places `[n]` markers
- All config via environment variables with sensible defaults, no hardcoded values
- Auto-pagination (1000/page, 5000 cap per tool call)
- Retry with exponential backoff on transient failures (429/5xx)
- "No data found" must be explicit, never silently empty
- Transport-agnostic tools: FastMCP handles stdio/HTTP Streamable switching via `MCP_TRANSPORT` env var
- Lifespan context manager manages `Data360Client` lifecycle (proper httpx cleanup)


## Environment Variables

All optional with sensible defaults — no API keys required (World Bank Data360 is a public API).

| Variable | Default | Purpose |
|---|---|---|
| `DATA360_BASE_URL` | `https://data360api.worldbank.org` | API base URL |
| `DATA360_REQUEST_TIMEOUT` | `30.0` | HTTP timeout in seconds |
| `DATA360_MAX_RETRIES` | `3` | Retry attempts on transient errors |
| `DATA360_RETRY_BACKOFF_BASE` | `1.0` | Exponential backoff base (seconds) |
| `MCP_TRANSPORT` | `stdio` | Transport mode (`stdio` or `streamable-http`) |
| `MCP_PORT` | `8001` | HTTP port (only used with `streamable-http`) |


## BMAD Artifacts

Architecture decisions, PRD, epics, and research reports live in `_bmad-output/`. Reference these for the "why" behind design choices.
