# Context Climate

A conversational AI tool that lets you query World Bank climate and development data using natural language, with verified citations. Powered by the [World Bank Data360 API](https://data360api.worldbank.org) and exposed as an MCP server for use with Claude Desktop or any MCP-compatible client.

No API keys required — Data360 is a public API.


## What It Does

Context Climate gives Claude (or any MCP client) five tools to interact with World Bank data:

| Tool | Description |
|---|---|
| `search_indicators` | Full-text search across thousands of indicators |
| `get_data` | Retrieve time-series data for an indicator by country and year range |
| `get_metadata` | Query detailed metadata about indicators, datasets, and topics |
| `list_indicators` | List all indicators available in a given dataset |
| `get_disaggregation` | Get available disaggregation dimensions for a dataset or indicator |

Responses from the `get_data` tool include citation fields (`DATA_SOURCE` / `CITATION_SOURCE`) so answers can be grounded in verifiable sources. In the [web app](#web-app-conversational-ui--journalist-dossier), citations are pipeline-guaranteed: the server builds a structured citation registry from tool responses, so the LLM never fabricates source attribution. Other tools return raw API data that may not include these fields.


## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Claude Desktop (for desktop integration)


## Installation

```bash
git clone https://github.com/felipetio/context-climate
cd context-climate
uv sync
```


## Connect to Claude Desktop

### Option 1 — Automatic install (recommended)

Run this once from the project directory:

```bash
uv run fastmcp install claude-desktop mcp_server/server.py --name "Context Climate" --with-editable .
```

This writes the server config to Claude Desktop's config file automatically. Then:

1. Restart Claude Desktop
2. Look for the tools icon (hammer) in the chat input area
3. You should see 5 tools listed under "Context Climate"

### Option 2 — Manual config

If you prefer to configure Claude Desktop manually, add the following entry to your Claude Desktop config file:

**Config file location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "Context Climate": {
      "command": "/absolute/path/to/context-climate/.venv/bin/fastmcp",
      "args": [
        "run",
        "/absolute/path/to/context-climate/mcp_server/server.py"
      ],
      "env": {}
    }
  }
}
```

Replace `/absolute/path/to/context-climate` with the actual path on your machine. Then restart Claude Desktop.

### Verifying the connection

Open Claude Desktop and ask:

> "Search for CO2 emissions indicators using the Data360 tools"

Claude should call `search_indicators` and return a list of matching indicators with their dataset IDs.


## Running Locally (without Claude Desktop)

### MCP Inspector (browser-based tool testing)

```bash
uv run fastmcp dev mcp_server/server.py
```

Opens a browser UI where you can call each tool directly and inspect responses.

### HTTP Streamable mode

```bash
MCP_TRANSPORT=streamable-http uv run python -m mcp_server.server
```

Starts an HTTP server at `http://127.0.0.1:8001/mcp`. Any MCP-compatible client can connect to this endpoint.


## Web App (conversational UI + journalist dossier)

The full experience is a Chainlit web app that runs an agentic loop against the Claude API, connects to the MCP server as a client, and renders a live, publishable journalist dossier alongside the chat.

**Prerequisites:** Docker + Docker Compose (for PostgreSQL / pgvector) and an Anthropic API key.

```bash
uv sync
cp .env.example .env
#   set DATABASE_URL (PostgreSQL connection string)
#   set ANTHROPIC_API_KEY
#   optional: CLAUDE_MODEL (default claude-haiku-4-5), DATA360_RAG_ENABLED=true
docker compose up -d   # PostgreSQL 16 + pgvector, runs db/*.sql on first boot
just start             # starts PostgreSQL, FastMCP (HTTP), and Chainlit
```

Open `http://localhost:8000`.

Useful commands:

| Command | Description |
|---|---|
| `just status` | Show service health (PostgreSQL / FastMCP / Chainlit) |
| `just logs` | Tail FastMCP / Chainlit / PostgreSQL logs |
| `just restart chainlit` | Restart only the Chainlit app |
| `just reset` | Wipe the database volume (erases all conversations) |


## Configuration

All settings are optional — defaults work out of the box.

| Environment Variable | Default | Description |
|---|---|---|
| `DATA360_BASE_URL` | `https://data360api.worldbank.org` | API base URL |
| `DATA360_REQUEST_TIMEOUT` | `30.0` | HTTP timeout in seconds |
| `DATA360_MAX_RETRIES` | `3` | Retry attempts on 429/5xx errors |
| `DATA360_RETRY_BACKOFF_BASE` | `1.0` | Exponential backoff base (seconds) |
| `MCP_TRANSPORT` | `stdio` | Transport mode (`stdio` or `streamable-http`) |
| `MCP_PORT` | `8001` | HTTP port (only used with `streamable-http`) |

You can set these in a `.env` file in the project root.


## Running Tests

```bash
uv run python -m pytest
```


## Architecture

Context Climate is a Python full-stack conversational AI system built around one principle: **every data point is citable by design.** It has five components:

```
  World Bank Data360 API
        │  (async httpx — retry, pagination, citation enrichment)
        ▼
  Data360Client ──► FastMCP Server ──► MCP tools (stdio OR HTTP Streamable)
                                            │
                                            ▼
       Claude API (agentic tool-use loop)  ◄──►  Chainlit + FastAPI web app
                                            │
                                            ▼
                          PostgreSQL 16 + pgvector
                  (conversation persistence + RAG document store)
```

1. **MCP Server (FastMCP)** — exposes the 5 World Bank tools, transport-agnostic: stdio for Claude Desktop, HTTP Streamable for the web app. Same code, switched by `MCP_TRANSPORT`. A lifespan context manager owns the `Data360Client` (clean httpx pooling/teardown).
2. **Data360Client** — async httpx client handling `snake_case` → `UPPERCASE` param mapping, auto-pagination (1000/page, 5000 cap per call), retry with exponential backoff on 429/5xx, and citation enrichment.
3. **Web App (Chainlit + FastAPI)** — runs the agentic loop against the Claude API (Haiku 4.5 default, configurable), connects to the MCP server as a client, streams responses, and renders the journalist dossier in a split-panel canvas.
4. **Citation pipeline (`app/citations.py`)** — a server-side registry is built deterministically from tool responses; the LLM only places `[n]` markers, so source attribution can never be hallucinated.
5. **Data layer** — PostgreSQL 16 with pgvector. Stores Chainlit conversations (resumable from the sidebar) and, when RAG is enabled, document embeddings for semantic search.

**Journalist dossier:** a 10-item investigation checklist drives a conversational interview. The dossier is a live markdown document edited by the LLM through surgical patch operations (`apply_ops`), never pasted inline in chat. An investigation state machine gates the transition into dossier mode.

```
mcp_server/
  config.py          # ENV-based config
  data360_client.py  # Async httpx client (retry, pagination, citation enrichment)
  server.py          # FastMCP server + tool definitions
  rag/               # Document processing pipeline (chunk, embed, store) — feature-flagged
app/
  chat.py            # Chainlit handlers + agentic loop
  citations.py       # Server-side citation registry
  prompts.py         # System prompts (grounding, dossier phases)
tests/               # 400+ unit and integration tests
```

**Tech stack:** Python 3.12, FastMCP 3.x, httpx, Chainlit 2.x, FastAPI, Anthropic SDK, SQLAlchemy (async) + asyncpg, sentence-transformers, pymupdf4llm. Quality gates: ruff lint+format (pre-commit enforced) and CI on GitHub Actions. Developed with the BMAD methodology — PRD, architecture, epics and retrospectives live in `_bmad-output/`.


## Data360 API Integration

Context Climate talks to the World Bank Data360 API through a single async client (`mcp_server/data360_client.py`) wrapped by the five MCP tools. Data360 is a public API, so **no authentication or API key is required.**

Endpoints used:

| Endpoint | Tool | Purpose |
|---|---|---|
| `POST /data360/searchv2` | `search_indicators` | Full-text indicator search |
| `GET /data360/data` | `get_data` | Time-series data (paginated) |
| `GET /data360/metadata` | `get_metadata` | OData metadata queries |
| `GET /data360/indicators` | `list_indicators` | All indicators in a dataset |
| `GET /data360/disaggregation` | `get_disaggregation` | Dimension / disaggregation info |

Client behavior:

- **Auto-pagination** — results fetched 1000 records/page up to a 5000-record safety cap per call, so the LLM never manages paging.
- **Resilience** — retry with exponential backoff on transient failures (429, 500, 502, 503, 504); timeout, retry count, and backoff base are all configurable via `DATA360_*` env vars.
- **Citation integrity** — the API's `DATA_SOURCE` field flows through **unmodified**. When absent (non-WDI databases), `CITATION_SOURCE` is enriched from a cached database-name lookup. The resolved attribution is always exposed as `CITATION_SOURCE`.
- **Transparent failure** — an empty result is returned as an explicit "no data found", never a silent empty payload.
- **Data freshness** — every data response surfaces the most recent available year; the app warns when data is older than a configurable threshold (default 2 years).


## Security & Data Handling

- **Secrets** — all configuration is via environment variables with safe defaults; nothing is hardcoded. `.env` is git-ignored and never committed. Data360 needs no credentials; the only secret is the Anthropic API key.
- **Network** — external communication is HTTPS-only (World Bank Data360 + Anthropic API).
- **Privacy** — no PII is required or collected; the system queries country-level public statistics only. Conversation history is persisted in PostgreSQL solely to let users resume chats, and can be wiped at any time (`just reset`). No third-party analytics or tracking.
- **Uploaded documents (RAG, opt-in, off by default)** — processed locally: text extraction (pymupdf4llm), chunking, and embedding with a locally-run sentence-transformers model (`all-MiniLM-L6-v2`, 384-dim). File contents are never sent to any third party for embedding. Upload size is capped (default 20 MB) and file types are restricted (PDF/CSV/TXT/MD).


## Roadmap & Sustainability

Context Climate is built to last beyond the Data360 Global Challenge:

- **Public good, public stack** — built entirely on the free World Bank Data360 public API (no key, no quota tier) and open-source components. No proprietary dependency to renew, no per-seat licensing.
- **Low operational footprint** — the MCP server is stateless and cached; the only recurring cost is LLM inference, controlled by defaulting to Claude Haiku, prompt caching, and configurable token/history caps.
- **Resilience to API change** — the Data360 API is in beta; all API contact is isolated behind a single abstracted client, so a breaking change is a one-file fix, guarded by a 400+ test suite.
- **Stewardship** — stewarded by **InfoAmazonia**, anchoring the project in a real editorial workflow. The open repo and BMAD-documented methodology lower the bus-factor and make institutional hand-off straightforward.
- **Roadmap** — near-term: Fact-Check mode (paste a climate claim → data-backed verdict), offline indicator discovery, temporal-coverage tooling. Mid-term: deepen the journalist dossier (data-validated investigation, editorial intelligence) and roll out within InfoAmazonia's newsroom, then to partner outlets.

Data flow: `World Bank Data360 API -> Data360Client -> MCP tools -> Claude Desktop / Chainlit`
