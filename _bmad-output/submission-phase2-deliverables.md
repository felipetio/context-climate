# Context Climate — Phase 2 Final Deliverables

> Challenge: **Data360 Global Challenge** (Media Party + World Bank) · Track: Data Dialogue
> Company: InfoAmazonia · Project: **Context Climate**
> Copy-paste content for the Media Party Projects "Final Deliverables" form.

---

## 1. Working Prototype

### Code Repository URL
```
https://github.com/felipetio/context-climate
```
> ⚠️ Make sure the repo is public (or invite the jury) before final submission.

### Installation Instructions
```
PREREQUISITES
- Python 3.12+
- uv (https://docs.astral.sh/uv) — package manager
- Docker + Docker Compose (for PostgreSQL / pgvector)
- An Anthropic API key (for the conversational web app)

A) QUICK START — MCP server with Claude Desktop (no database, no keys)
1. git clone https://github.com/felipetio/context-climate && cd context-climate
2. uv sync
3. uv run fastmcp install claude-desktop mcp_server/server.py \
       --name "Context Climate" --with-editable .
4. Restart Claude Desktop. The 5 World Bank Data360 tools appear under the
   tools (hammer) icon. Ask: "Search for CO2 emissions indicators."
   (World Bank Data360 is a public API — no key required.)

B) FULL WEB APP — conversational UI + journalist dossier
1. uv sync
2. cp .env.example .env
   - set DATABASE_URL (PostgreSQL connection string)
   - set ANTHROPIC_API_KEY
   - optional: CLAUDE_MODEL (default claude-haiku-4-5), DATA360_RAG_ENABLED=true
3. docker compose up -d            # starts PostgreSQL 16 + pgvector, runs db/*.sql
4. just start                      # starts PostgreSQL, FastMCP (HTTP), Chainlit
   (or run components manually — see README "Running Locally")
5. Open http://localhost:8000

Useful commands:
- just status   — show service health
- just logs     — tail FastMCP / Chainlit / PostgreSQL logs
- just restart chainlit
- uv run python -m pytest         — run the full test suite (400+ tests)
```

---

> **2. 5-Minute Demo Video** — handled separately (not part of this draft).

---

## 3. Technical Documentation

### Architecture Overview
```
Context Climate is a Python full-stack conversational AI system with five
components, designed around one principle: every data point is citable by
design.

  World Bank Data360 API
        │  (async httpx, retry, pagination, citation enrichment)
        ▼
  Data360Client ──► FastMCP Server ──► MCP tools (stdio OR HTTP Streamable)
                                            │
                                            ▼
       Claude API (agentic tool-use loop)  ◄──►  Chainlit + FastAPI web app
                                            │
                                            ▼
                          PostgreSQL 16 + pgvector
                  (conversation persistence + RAG document store)

1. MCP Server (FastMCP) — exposes 5 World Bank tools, transport-agnostic:
   stdio for Claude Desktop, HTTP Streamable for the web app. Same code, same
   tools, switched by the MCP_TRANSPORT env var. A lifespan context manager
   owns the Data360Client (clean httpx pooling/teardown).

2. Data360Client — async httpx client handling snake_case→UPPERCASE param
   mapping, auto-pagination (1000/page, 5000 cap per call), retry with
   exponential backoff on 429/5xx, and citation enrichment.

3. Web App (Chainlit + FastAPI) — runs the agentic loop against the Claude API
   (Haiku 4.5 default, configurable), connects to the MCP server as a client,
   streams responses, and renders the journalist dossier in a split-panel
   canvas. Citations are pipeline-guaranteed (see below).

4. Citation pipeline (app/citations.py) — a server-side registry is built
   deterministically from tool responses; the LLM only places [n] markers, so
   source attribution can never be hallucinated.

5. Data layer — PostgreSQL 16 with pgvector. Stores Chainlit conversations
   (resumable from the sidebar) and, when RAG is enabled, document embeddings
   for semantic search.

Journalist dossier: a 10-item investigation checklist drives a conversational
interview. The dossier is a live markdown document edited by the LLM through
surgical patch operations (apply_ops), never pasted inline in chat. An
investigation state machine gates the transition into dossier mode.

Tech stack: Python 3.12, FastMCP 3.x, httpx, Chainlit 2.x, FastAPI, Anthropic
SDK, SQLAlchemy (async) + asyncpg, sentence-transformers, pymupdf4llm.
Quality: ruff lint+format (pre-commit enforced), 400+ pytest tests, CI on
GitHub Actions. Built with the BMAD methodology (PRD, architecture, epics and
retrospectives in _bmad-output/).
```

### Data360 API Integration Methodology
```
Context Climate integrates the World Bank Data360 API through a dedicated async
client (mcp_server/data360_client.py) wrapped by five MCP tools. World Bank
Data360 is a public API, so no authentication or API key is required.

Endpoints used:
- POST /data360/searchv2     → search_indicators  (full-text indicator search)
- GET  /data360/data         → get_data           (time-series, paginated)
- GET  /data360/metadata     → get_metadata       (OData metadata queries)
- GET  /data360/indicators   → list_indicators    (all indicators in a dataset)
- GET  /data360/disaggregation → get_disaggregation (dimension info)

Client behavior:
- Parameter mapping: tool args (snake_case) are mapped to the API's UPPERCASE
  convention; None values are dropped.
- Auto-pagination: results are fetched 1000 records/page up to a 5000-record
  safety cap per tool call, so the LLM never has to manage paging.
- Resilience: requests retry with exponential backoff on transient failures
  (HTTP 429, 500, 502, 503, 504); configurable timeout, retry count and backoff
  base via DATA360_* env vars.
- Citation enrichment: the API's DATA_SOURCE field flows through UNMODIFIED.
  When absent (non-WDI databases), CITATION_SOURCE is enriched from a cached
  database-name lookup (_db_name_cache populated from search results). The
  resolved attribution is always exposed as CITATION_SOURCE.
- Transparent failure: an empty result is returned as an explicit "no data
  found", never a silent empty payload — a trustworthy "I don't have that" is
  more valuable than a confident wrong answer.
- Data freshness: every data response surfaces the most recent available year;
  the app warns when data is older than a configurable threshold (default 2y).

In the web app, the citation registry (app/citations.py) consumes these tool
responses server-side and assigns stable [n] indices; the LLM only places the
markers, guaranteeing each [n] resolves to a real World Bank source.
```

### Security & Data Handling Protocols
```
Secrets & configuration:
- All configuration is via environment variables with safe defaults; no
  secrets are hardcoded. .env is git-ignored and never committed (.env.example
  documents every variable).
- Data360 requires no credentials (public API). The only secret is the
  Anthropic API key for the web app, supplied via env var.

Transport & network:
- External communication is HTTPS-only (World Bank Data360 + Anthropic API).
- The MCP server runs locally/over a private HTTP Streamable endpoint; in the
  hosted demo it sits behind a reverse proxy with auth.

Data minimization & privacy:
- No PII is required or collected to use the tool. The system queries
  country-level public statistics only — no personal data is processed.
- Conversation history is persisted in PostgreSQL solely to let users resume
  chats; it can be wiped at any time (just reset). No third-party analytics or
  tracking.
- Uploaded documents (RAG, opt-in feature flag, OFF by default) are processed
  locally: text extraction (pymupdf4llm), chunking, and embedding with a
  locally-run sentence-transformers model (all-MiniLM-L6-v2, 384-dim) — file
  contents are never sent to any third party for embedding. Upload size is
  capped (default 20 MB) and file types are restricted (PDF/CSV/TXT/MD).

Integrity & safety:
- Citation integrity is enforced server-side: source attribution is derived
  from API responses, not generated by the LLM, so it cannot be fabricated.
- Input to the Data360 client is parameterized; the patch-engine for the
  dossier rejects malformed/empty operations.
- Dependencies are pinned via uv.lock; code passes ruff lint/format gates in CI
  before merge.
```

---

## 4. User Guide / Documentation

### Link to user guide or docs
```
https://github.com/felipetio/context-climate/blob/main/README.md
```
The README covers installation, Claude Desktop integration (automatic + manual),
local run modes (MCP Inspector, HTTP Streamable), the full environment-variable
reference, and the tool catalog. Architecture, PRD and epics live in
`_bmad-output/`.

> Optional: if you want a friendlier end-user guide (journalist-facing, with the
> dossier walkthrough), say the word and I'll draft one to host alongside.

---

## 5. Sustainability / Maintenance Plan
```
Built to last beyond the challenge:

- Public good, public stack. Context Climate is built entirely on free/public
  foundations — the World Bank Data360 public API (no key, no quota tier) and
  open-source components (FastMCP, Chainlit, PostgreSQL/pgvector,
  sentence-transformers). There is no proprietary dependency to renew and no
  per-seat licensing, so the marginal cost of keeping it running is low.

- Low operational footprint. The MCP server is stateless and aggressively
  cached; auto-pagination and retry/backoff keep it resilient to API hiccups.
  The only recurring cost is LLM inference, controlled by defaulting to Claude
  Haiku, prompt caching, and configurable token/history caps.

- Resilience to API change. The Data360 API is in beta; we isolated all API
  contact behind a single abstracted client (Data360Client), so a breaking
  change is a one-file fix, not a rewrite. A 400+ test suite guards behavior.

- Maintainability & contribution. Open-source on GitHub, developed with the
  BMAD methodology — PRD, architecture decisions, epics, stories and
  retrospectives are versioned in the repo, so a new maintainer can understand
  the "why" behind every decision. ruff + pre-commit + CI keep quality
  consistent across contributors.

- Roadmap. Near-term: Fact-Check mode (paste a climate claim → data-backed
  verdict), offline indicator discovery, and temporal-coverage tooling are
  already specified as epics. Mid-term: deepen the journalist dossier
  (data-validated investigation, editorial intelligence) and roll it out within
  InfoAmazonia's newsroom, then to partner outlets, with working journalists as
  design partners.

- Stewardship. The project is stewarded by InfoAmazonia — an established
  environmental-journalism newsroom — which anchors it in a real editorial
  workflow and gives it an institutional home beyond the challenge. The open
  repo and BMAD-documented methodology lower the bus-factor and make community
  or institutional hand-off straightforward.
```

---

### Items that still need YOUR input before submitting
1. **YouTube demo video link** (Section 2) — record using the script above.
2. **Repository visibility** — confirm `felipetio/context-climate` is public or
   the jury is invited.
3. **User guide link** — README is the default; tell me if you want a dedicated
   journalist-facing guide.
4. **Hosted demo** — confirm `https://felipet.io/demos/context-climate/` is up
   (demo/demo) if you list it.
