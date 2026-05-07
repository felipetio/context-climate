---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - prd.md
  - architecture.md
status: 'complete'
completedAt: '2026-03-23'
---

# Context Climate - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Context Climate, decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Users can ask climate and development data questions in natural language via a conversational interface
FR2: The system can map natural language queries to relevant World Bank Data360 indicators using vector search
FR3: The system can retrieve country-level data values for matched indicators from the Data360 API
FR4: The system can retrieve indicator metadata (descriptions, topics, data sources) from the Data360 API
FR5: Users can query indicators beyond climate (any of the 10,000+ Data360 indicators)
FR6: Users can specify countries, regions, or use global comparisons (WLD area code) in their queries
FR7: Users can ask follow-up questions that build on previous conversation context
FR8: The system can include DATA_SOURCE attribution from the API on every data-bearing response
FR9: The system can format citations for direct use in publications (publication-ready format)
FR10: The system can display the most recent data year available for every data point
FR11: The system can warn users when data is older than 2 years
FR12: The system can display the indicator code alongside source attribution
FR13: The system can generate contextual narrative responses that describe data values, trends, and comparisons
FR14: The system can compare data across multiple countries in a single response
FR15: The system can identify and describe trends over time (rising, falling, stable, accelerating)
FR16: The system can flag data gaps and missing years transparently within responses
FR17: The system can respond with "no relevant data found" when no matching indicators exist
FR18: The system can restrict LLM responses to narrate only data returned by the Data360 API
FR19: The system can prevent the LLM from adding causal explanations not present in API data
FR20: The system can prevent the LLM from generating predictions or forecasts
FR21: The system can prevent the LLM from adding external knowledge or editorial judgment
FR22: The system can respond to "why?" questions by stating it can only report what the data shows
FR23: Users can paste a climate or data claim for verification
FR24: The system can identify relevant indicators to evaluate the claim
FR25: The system can calculate actual values and compare them against the claimed values
FR26: The system can return a verdict (supported, not supported, partially supported) with source citations
FR27: The system can persist conversation history across sessions
FR28: Users can start new conversations
FR29: Users can access previous conversations
FR30: The system can stream responses token-by-token in real time
FR31: The MCP server can search indicators from natural language via the Data360 /searchv2 endpoint
FR32: The MCP server can fetch data values via the Data360 /data endpoint
FR33: The MCP server can retrieve indicator metadata via the Data360 /metadata endpoint
FR34: The MCP server can handle pagination for large result sets (>1000 records)
FR35: The MCP server can operate via stdio transport (for Claude Desktop development)
FR36: The MCP server can operate via HTTP Streamable transport (for web production)
FR37: The MCP server can return a curated list of popular climate and development indicators without any API call
FR38: The MCP server can search local indicator metadata offline using relevance-scored substring matching
FR39: Offline search results include relevance scores so the LLM can prioritize the best matches
FR40: Indicator metadata and popular indicator data are loaded once and cached in memory for the server lifetime
FR41: The MCP server can check the temporal coverage (start year, end year, available years) for a given indicator and database
FR42: Temporal coverage extraction uses the existing metadata endpoint with OData filtering
FR43: The MCP server enforces a 3-step data retrieval workflow: search indicators → check temporal coverage → retrieve data
FR44: The MCP server provides a compare_countries prompt that guides multi-country indicator comparison
FR45: The MCP server provides a country_profile prompt that generates a comprehensive country summary across key indicators
FR46: The MCP server provides a trend_analysis prompt that guides time-series trend exploration for an indicator
FR47: The MCP server exposes discoverable resources for popular indicators and available databases
FR48: The MCP server exposes a workflow resource documenting the recommended 3-step data retrieval process

### NonFunctional Requirements

NFR1: Streaming responses must deliver first token within 3 seconds (uncached) or 1 second (cached)
NFR2: Full response completion must occur within 15 seconds (uncached) or 5 seconds (cached)
NFR3: The system must support 10-50 concurrent user sessions without degradation
NFR4: World Bank API response caching must reduce repeat query latency to <100ms
NFR5: Claude API key must be stored as environment variable, never in source code or client-side assets
NFR6: Database connection credentials must be stored as environment variables
NFR7: All external API communication (Claude API, Data360 API) must use HTTPS
NFR8: No user PII is collected or stored beyond conversation content
NFR9: The system must handle Data360 API unavailability gracefully with clear user messaging
NFR10: The system must handle Claude API rate limits with exponential backoff
NFR11: Cached API responses must have configurable TTL (default: 24 hours for data, indefinite for metadata)
NFR12: The MCP server must be transport-agnostic, supporting both stdio and HTTP Streamable without code changes to tool logic
NFR13: Offline indicator search must return results in under 50ms (no network calls)
NFR14: Popular indicators and metadata files must load into memory in under 500ms at server startup

### Document Upload & RAG Search Requirements

FR49: Users can upload PDF, TXT, MD, and CSV documents via the Chainlit chat interface
FR50: The system can extract text from uploaded documents and split into chunks for vector search
FR51: The system can generate embeddings for document chunks and store them in pgvector
FR52: The MCP server can search uploaded documents via vector similarity (search_documents tool)
FR53: The MCP server can list all uploaded documents with metadata (list_documents tool)
FR54: The system can cross-reference Data360 API quantitative data with uploaded document context in a single response
FR55: Document-sourced citations follow the CITATION_SOURCE pattern (e.g., "CEMADEM Report (uploaded 2026-03-30), p. 12")
FR56: RAG functionality is gated behind DATA360_RAG_ENABLED env var (default: false)

### Citation UI & Journalist Export Requirements

FR57: The UI can render clickable/hoverable citation markers `[n]` that display source details (database, indicator, year range) in a tooltip
FR58: The UI can copy response text with citations preserved, including the reference list in a selectable format (IEEE, ABNT, APA)
FR59: The UI can generate a verification deep link for each citation that points to the Data360 indicator page

### Additional Requirements

- Manual project setup with uv (no starter template): `uv init context-climate`, `uv add fastmcp chainlit fastapi uvicorn asyncpg anthropic httpx`
- 5 MCP tools mapping 1:1 with Data360 API endpoints: search_indicators, get_data, get_metadata, list_indicators, get_disaggregation
- Dual transport from day 1: stdio (Claude Desktop dev) and HTTP Streamable (Chainlit production)
- Auto-pagination strategy: loop in 1000 increments, hard cap at 5000 records per tool call
- Structured error responses from MCP tools (success/error format), never raise exceptions
- httpx async client with exponential backoff retry (1s, 2s, 4s, max 3 attempts) for 429 and 5xx errors
- Python stdlib logging (structured JSON in prod), logger per module, no print statements
- Parameter mapping: Python snake_case in tool signatures, UPPERCASE for Data360 API, mapped in data360_client.py
- Preserve Data360 API field names exactly (DATA_SOURCE, COMMENT_TS, OBS_VALUE, etc.) for citation integrity
- PostgreSQL with pgvector for persistence and caching (Week 2+)
- Chainlit mounted as FastAPI sub-application via mount_chainlit
- Docker single container deployment on Railway or Render (deferred past Week 1)
- Tests with pytest + httpx, MCP Inspector for debugging, Claude Desktop for e2e
- Project structure: organize by component (mcp_server/, app/), not by type

### UX Design Requirements

No UX Design document was provided. Chainlit handles all frontend concerns for MVP per Architecture decision.

### FR Coverage Map

FR1: Epic 2 - Natural language query input via Chainlit chat interface
FR2: Epic 1 - Vector search via MCP search_indicators tool
FR3: Epic 1 - Data retrieval via MCP get_data tool
FR4: Epic 1 - Metadata retrieval via MCP get_metadata tool
FR5: Epic 1 - All Data360 indicators accessible through MCP tools
FR6: Epic 1 - Country/region/global filtering in get_data tool
FR7: Epic 2 - Multi-turn conversation with context via Chainlit
FR8: Epic 3 - DATA_SOURCE passthrough in system prompt and response formatting
FR9: Epic 3 - Publication-ready citation formatting via system prompt
FR10: Epic 3 - Data year display in every response
FR11: Epic 3 - Stale data warnings (>2 years)
FR12: Epic 3 - Indicator code display with source attribution
FR13: Epic 2 - Narrative response generation via LLM
FR14: Epic 2 - Multi-country comparison responses
FR15: Epic 2 - Trend description in responses
FR16: Epic 2 - Data gap flagging in responses
FR17: Epic 2 - "No data found" transparent responses
FR18: Epic 3 - LLM grounding boundary via system prompt
FR19: Epic 3 - Causal explanation prevention
FR20: Epic 3 - Prediction/forecast prevention
FR21: Epic 3 - External knowledge prevention
FR22: Epic 3 - "Why?" question handling
FR23: Epic 4 - Claim input for verification
FR24: Epic 4 - Indicator identification for claims
FR25: Epic 4 - Actual vs. claimed value comparison
FR26: Epic 4 - Verdict generation with sources
FR27: Epic 2 - Conversation persistence via Chainlit datalayer
FR28: Epic 2 - New conversation creation
FR29: Epic 2 - Previous conversation access
FR30: Epic 2 - Token-by-token streaming
FR31: Epic 1 - search_indicators MCP tool
FR32: Epic 1 - get_data MCP tool
FR33: Epic 1 - get_metadata MCP tool
FR34: Epic 1 - Pagination handling in data360_client.py
FR35: Epic 1 - stdio transport for Claude Desktop
FR36: Epic 1 - HTTP Streamable transport for production
FR37: Epic 5 - Popular indicators list via list_popular_indicators tool
FR38: Epic 5 - Offline indicator search via search_local_indicators tool
FR39: Epic 5 - Relevance scoring in offline search results
FR40: Epic 5 - Singleton caching for indicator data files
FR41: Epic 6 - Temporal coverage check via get_temporal_coverage tool
FR42: Epic 6 - OData filter-based year extraction from metadata endpoint
FR43: Epic 6 - 3-step workflow enforcement (search → coverage → data)
FR44: Epic 7 - compare_countries MCP prompt
FR45: Epic 7 - country_profile MCP prompt
FR46: Epic 7 - trend_analysis MCP prompt
FR47: Epic 7 - MCP resources for indicator and database discovery
FR48: Epic 7 - Workflow documentation resource
FR49: Epic 8 - Document upload via Chainlit file attachment
FR50: Epic 8 - Text extraction and chunking pipeline
FR51: Epic 8 - Embedding generation and pgvector storage
FR52: Epic 8 - search_documents MCP tool
FR53: Epic 8 - list_documents MCP tool
FR54: Epic 8 - Cross-referencing API + document data in responses
FR55: Epic 8 - Document CITATION_SOURCE pattern
FR56: Epic 8 - DATA360_RAG_ENABLED feature flag
FR57: Epic 9 - Interactive citation markers with tooltips
FR58: Epic 9 - Copy-with-citations and format export (IEEE/ABNT/APA)
FR59: Epic 9 - Source verification deep links to Data360

## Epic List

### Epic 1: World Bank Data Access via MCP Server
Users can search, retrieve, and explore World Bank Data360 climate and development indicators through MCP tools, testable in Claude Desktop from day 1.
**FRs covered:** FR2, FR3, FR4, FR5, FR6, FR31, FR32, FR33, FR34, FR35, FR36
**NFRs addressed:** NFR4 (caching prep), NFR7 (HTTPS), NFR9 (graceful API failure), NFR10 (rate limit backoff), NFR11 (cache TTL), NFR12 (transport-agnostic)

### Epic 2: Conversational Climate Data Interface
Users can ask climate and development questions in natural language via a chat interface and receive streaming, data-backed narrative responses with multi-turn conversation support.
**FRs covered:** FR1, FR7, FR13, FR14, FR15, FR16, FR17, FR27, FR28, FR29, FR30
**NFRs addressed:** NFR1 (first token latency), NFR2 (full response time), NFR3 (concurrent sessions), NFR5 (API key security), NFR6 (DB credentials)

### Epic 3: Trust, Citations & LLM Grounding
Every data response carries verifiable World Bank sources with pipeline-guaranteed citations (not LLM-generated). The citation registry is built deterministically from MCP tool responses. LLM grounding boundaries prevent hallucination, and data freshness is always transparent.
**FRs covered:** FR8, FR9, FR10, FR11, FR12, FR18, FR19, FR20, FR21, FR22
**NFRs addressed:** NFR8 (no PII)

### Epic 4: Fact-Check & Claim Verification
Users can paste a climate or data claim and receive a data-grounded verdict (supported/not supported/partially supported) with World Bank source citations.
**FRs covered:** FR23, FR24, FR25, FR26

### Epic 5: Offline Local Indicator Discovery
Users can instantly discover and search World Bank indicators without any API call, enabling faster workflows and resilience when the Data360 API is slow or unavailable.
**FRs covered:** FR37, FR38, FR39, FR40
**NFRs addressed:** NFR13 (offline search <50ms), NFR14 (startup load <500ms)

### Epic 6: Temporal Coverage Check
Users can check which years have data for a given indicator before requesting data, preventing failed API calls and enabling smarter data retrieval workflows.
**FRs covered:** FR41, FR42, FR43
**NFRs addressed:** NFR9 (graceful API failure), NFR12 (transport-agnostic)

### Epic 7: MCP Prompts & Resources
The MCP server provides guided workflow prompts and discoverable resources that help LLM clients execute common data analysis patterns with consistent quality and proper citations.
**FRs covered:** FR44, FR45, FR46, FR47, FR48
**NFRs addressed:** NFR12 (transport-agnostic)

### Epic 8: Document Upload & RAG Search
Users can upload documents (PDFs, reports from CEMADEM, CPTEC, NDCs) and search them via vector similarity, enabling cross-referencing of World Bank quantitative data with sub-national/qualitative document context. Feature-flagged via DATA360_RAG_ENABLED.
**FRs covered:** FR49, FR50, FR51, FR52, FR53, FR54, FR55, FR56
**NFRs addressed:** NFR8 (no PII), NFR9 (graceful failure)

### Epic 9: Citation UI & Journalist Export
Structured citation data from Epic 3's pipeline is rendered in the Chainlit UI with interactive references, copy-with-citation support, and export-ready formatting for newsroom workflows. Directly addresses Data360 Challenge pillars 04 (Digital Passport for Facts) and 02 (Instant Visual Stories).
**FRs covered:** FR9 (publication-ready, enhanced), FR57, FR58, FR59
**NFRs addressed:** NFR1 (responsive UI interactions)
**Implementation order:** After Epic 3
**Implementation order:** After Epic 2, before Epic 3 (so system prompt covers all data sources). Full order: 2 → 8 → 3 → 9 → 4 → 5 → 6 → 7

---

## Epic 1: World Bank Data Access via MCP Server

Users can search, retrieve, and explore World Bank Data360 climate and development indicators through MCP tools. The MCP server is standalone, testable in Claude Desktop via stdio, and production-ready via HTTP Streamable.

### Story 1.1: Project Setup and Configuration

As a developer,
I want to initialize the Context Climate project with all dependencies and configuration,
So that I have a working development environment to build the MCP server.

**Acceptance Criteria:**

**Given** a clean development environment
**When** running `uv init context-climate && cd context-climate && uv add fastmcp httpx`
**Then** the project is created with pyproject.toml containing all MCP server dependencies
**And** the project structure includes `mcp_server/__init__.py`, `mcp_server/server.py`, `mcp_server/data360_client.py`, `mcp_server/config.py`
**And** `mcp_server/config.py` contains base URL (`https://data360api.worldbank.org`), timeout settings, and pagination limits (1000 per page, 5000 cap)
**And** `.env.example` documents all required environment variables
**And** `.gitignore` excludes `.env`, `__pycache__`, `.venv`
**And** `tests/mcp_server/__init__.py` directory structure exists

### Story 1.2: Data360 API Client with Error Handling

As a developer,
I want an async HTTP client that wraps the World Bank Data360 API with retry logic and structured error handling,
So that all MCP tools have a reliable, consistent way to call the API.

**Acceptance Criteria:**

**Given** the `data360_client.py` module
**When** making a successful API call to any Data360 endpoint
**Then** the client maps Python snake_case parameters to API UPPERCASE parameters (e.g., `database_id` -> `DATABASE_ID`)
**And** the response preserves all API field names exactly (`DATA_SOURCE`, `COMMENT_TS`, `OBS_VALUE`, etc.)
**And** the client uses httpx.AsyncClient with configurable timeout

**Given** a Data360 API call that returns a 429 or 5xx error
**When** the client processes the response
**Then** it retries with exponential backoff (1s, 2s, 4s, max 3 attempts)
**And** if all retries fail, returns a structured error: `{"success": False, "error": "<message>", "error_type": "api_error"}`

**Given** a Data360 API call that returns a 4xx client error (not 429)
**When** the client processes the response
**Then** it does NOT retry and returns a structured error immediately

**Given** a request for data with more than 1000 records
**When** the client fetches data
**Then** it auto-paginates using the `skip` parameter in increments of 1000
**And** it stops at 5000 records total and sets `truncated: True` in the response

**Given** any API interaction
**When** logging is invoked
**Then** the client uses `logging.getLogger(__name__)` (no print statements)
**And** logs API request/response details at DEBUG level, failures at ERROR level

### Story 1.3: Search Indicators MCP Tool

As a user querying World Bank data,
I want to search for relevant indicators using natural language,
So that I can find the right data indicators for my climate or development questions.

**Acceptance Criteria:**

**Given** the MCP server is running
**When** a user calls `search_indicators(query="drought Brazil")`
**Then** the tool calls POST `/data360/searchv2` with `{"search": "drought Brazil", "top": 10, "skip": 0}`
**And** returns `{"success": True, "data": [...], "total_count": N, "returned_count": M, "truncated": False}`
**And** each result includes indicator ID, name, database_id, and description

**Given** a search with optional parameters
**When** calling `search_indicators(query="CO2 emissions", top=5, filter="...")`
**Then** the tool passes all parameters correctly to the API

**Given** a search that returns no results
**When** the tool processes the empty response
**Then** it returns `{"success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False}`

**Given** the Data360 API is unavailable
**When** the tool is called
**Then** it returns `{"success": False, "error": "<descriptive message>", "error_type": "api_error"}`

### Story 1.4: Get Data MCP Tool

As a user exploring climate data,
I want to retrieve actual data values for specific indicators by country and time period,
So that I can see the numbers behind climate and development trends.

**Acceptance Criteria:**

**Given** the MCP server is running
**When** a user calls `get_data(database_id="WB_WDI", indicator="WB_WDI_EN_ATM_CO2E_KT", ref_area="BRA")`
**Then** the tool calls GET `/data360/data` with the mapped UPPERCASE parameters
**And** returns data including `OBS_VALUE`, `DATA_SOURCE`, `COMMENT_TS`, `TIME_PERIOD`, `LATEST_DATA`, `INDICATOR`, `REF_AREA`
**And** all API field names are preserved exactly as returned

**Given** a query with time period filters
**When** calling `get_data(database_id="WB_WDI", indicator="...", time_period_from="2015", time_period_to="2023")`
**Then** the tool passes `timePeriodFrom` and `timePeriodTo` parameters correctly

**Given** a query that returns more than 1000 records
**When** the tool fetches data
**Then** it auto-paginates internally (via data360_client.py) up to 5000 records
**And** returns `total_count` from the API so the LLM knows if data was truncated

**Given** no data exists for the requested indicator/country combination
**When** the tool processes the response
**Then** it returns `{"success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False}`

### Story 1.5: Get Metadata, List Indicators, and Get Disaggregation MCP Tools

As a user exploring World Bank data,
I want to access indicator metadata, browse available indicators per dataset, and check disaggregation dimensions,
So that I can understand what data is available and how it's structured.

**Acceptance Criteria:**

**Given** the MCP server is running
**When** a user calls `get_metadata(query="&$filter=series_description/idno eq 'WB_WDI_SP_POP_TOTL'")`
**Then** the tool calls POST `/data360/metadata` with the OData query
**And** returns indicator metadata including description, topics, and data sources

**Given** the MCP server is running
**When** a user calls `list_indicators(dataset_id="WB_WDI")`
**Then** the tool calls GET `/data360/indicators?datasetId=WB_WDI`
**And** returns all available indicators for that dataset

**Given** the MCP server is running
**When** a user calls `get_disaggregation(dataset_id="WB_WDI", indicator_id="WB_WDI_SP_POP_TOTL")`
**Then** the tool calls GET `/data360/disaggregation` with the correct parameters
**And** returns available disaggregation dimensions (SEX, AGE, URBANISATION, etc.)

**Given** any of these three tools encounters an API error
**When** the error is processed
**Then** the tool returns a structured error response following the standard format
**And** never raises an exception

### Story 1.6: Dual Transport and Claude Desktop Testing

As a developer,
I want the MCP server to work via both stdio (Claude Desktop) and HTTP Streamable (production) transports,
So that I can test locally in Claude Desktop and deploy for web access without code changes.

**Acceptance Criteria:**

**Given** the MCP server with all 5 tools implemented
**When** running `fastmcp dev mcp_server/server.py`
**Then** the MCP Inspector opens and all 5 tools are visible and callable

**Given** the MCP server configured for stdio transport
**When** installed via `fastmcp install mcp_server/server.py`
**Then** Claude Desktop can use all 5 tools to query World Bank data end-to-end

**Given** the MCP server configured for HTTP Streamable transport
**When** started in HTTP mode
**Then** the server accepts MCP client connections over HTTP
**And** all 5 tools work identically to stdio mode

**Given** any transport mode
**When** tools are called
**Then** tool logic is identical, only the transport layer differs (handled by FastMCP)
**And** NFR12 (transport-agnostic) is satisfied

### Story 1.7: MCP Server Test Suite

As a developer,
I want automated tests for the MCP server and API client,
So that I can verify correctness and catch regressions.

**Acceptance Criteria:**

**Given** the test suite in `tests/mcp_server/`
**When** running `uv run pytest tests/mcp_server/`
**Then** all tests pass

**Given** `tests/mcp_server/fixtures/` with sample API responses
**When** `test_data360_client.py` runs
**Then** it tests parameter mapping (snake_case to UPPERCASE)
**And** tests auto-pagination logic
**And** tests retry behavior on 429/5xx errors
**And** tests no-retry on 4xx errors
**And** tests structured error response format

**Given** `test_server.py`
**When** MCP tool integration tests run
**Then** each of the 5 tools is tested with mocked API responses
**And** tests verify the consistent response format (success/error structure)
**And** tests verify API field names are preserved (DATA_SOURCE, COMMENT_TS, etc.)

---

## Epic 2: Conversational Climate Data Interface

Users can ask climate and development questions in natural language via a Chainlit chat interface and receive streaming, data-backed narrative responses with multi-turn conversation support and session persistence.

### Story 2.1: Chainlit + FastAPI Application Setup

As a developer,
I want to set up the web application with Chainlit mounted in FastAPI and PostgreSQL for persistence,
So that users have a chat interface to interact with the system.

**Acceptance Criteria:**

**Given** the existing project with MCP server
**When** adding web application dependencies (`uv add chainlit fastapi uvicorn asyncpg`)
**Then** `app/main.py` creates a FastAPI app with Chainlit mounted via `mount_chainlit`
**And** `app/config.py` loads environment variables for Claude API key, database connection, and MCP server URL
**And** `.chainlit/config.toml` is generated via `chainlit init`
**And** running `uvicorn app.main:app --reload` starts the full application

**Given** the application is running
**When** a user opens the browser
**Then** the Chainlit chat interface loads in under 2 seconds
**And** environment variables are used for all secrets (NFR5, NFR6)
**And** all external API communication uses HTTPS (NFR7)

### Story 2.2: Claude API Integration with Streaming

As a user,
I want to see the AI's response appear word-by-word in real time,
So that I don't have to wait for the full response before seeing results.

**Acceptance Criteria:**

**Given** a user sends a question
**When** Claude generates a response
**Then** tokens stream to the UI via Socket.IO (Chainlit's WebSocket)
**And** the first token appears within 3 seconds for uncached queries (NFR1)
**And** the full response completes within 15 seconds for uncached queries (NFR2)

**Given** Claude is making tool calls before responding
**When** tool call status changes
**Then** intermediate steps are displayed (e.g., "Searching indicators...", "Fetching data...")
**And** the user sees progress before the narrative response begins

### Story 2.3: MCP Client Integration with Claude Tool Use

As a user,
I want my natural language questions to be processed by Claude using the MCP server tools,
So that my questions are answered with real World Bank data.

**Acceptance Criteria:**

**Given** the Chainlit app is running with MCP client connected to the MCP server
**When** a user types "What are CO2 emissions in Brazil?"
**Then** Chainlit sends the message to Claude API with MCP tools available
**And** Claude selects appropriate tools (search_indicators, then get_data)
**And** tool calls are displayed as intermediate steps in the Chainlit UI
**And** the final response contains data from the World Bank Data360 API

**Given** the MCP server is connected via HTTP Streamable transport
**When** tool calls are made
**Then** the MCP client (Chainlit native handlers: `@cl.on_mcp_connect`, `@cl.on_mcp_disconnect`) manages the connection
**And** tool results flow back to Claude for response generation

**Given** the Data360 API is unavailable
**When** a tool call fails
**Then** the structured error response is passed to Claude
**And** Claude narrates the failure transparently to the user (NFR9)

### Story 2.4: Narrative Response Generation

As a journalist or researcher,
I want data presented as contextual narratives describing values, trends, and comparisons,
So that I can understand and use the data without interpreting raw numbers.

**Acceptance Criteria:**

**Given** a user asks "How has drought increased in Brazil in the last decade?"
**When** Claude receives data from MCP tools
**Then** the response describes data values in human-readable narrative form (FR13)
**And** includes trend descriptions (rising, falling, stable, accelerating) when time-series data is available (FR15)

**Given** a user asks "Compare CO2 emissions between Brazil and India"
**When** Claude processes multi-country data
**Then** the response compares data across the requested countries in a single narrative (FR14)

**Given** data has missing years or gaps
**When** Claude generates the response
**Then** it flags the gaps transparently (e.g., "Data not available for 2021-2022") (FR16)

**Given** no matching indicator exists for the query
**When** Claude processes the empty result
**Then** it responds clearly with "No relevant data found" and suggests alternative queries if appropriate (FR17)

### Story 2.5: Multi-Turn Conversation Support

As a user,
I want to ask follow-up questions that build on my previous questions,
So that I can explore data progressively without repeating context.

**Acceptance Criteria:**

**Given** a user asked "What are CO2 emissions in Brazil?" and received an answer
**When** the user follows up with "How does that compare to Argentina?"
**Then** Claude uses the conversation context to understand "that" refers to CO2 emissions (FR7)
**And** the response provides the comparison without the user needing to re-specify the indicator

**Given** a multi-turn conversation
**When** multiple tool calls are made across turns
**Then** each response maintains coherent context with previous answers

### Story 2.6: Conversation Persistence and History

As a user,
I want my conversations saved so I can return to them later,
So that I don't lose my research progress between sessions.

**Acceptance Criteria:**

**Given** the Chainlit datalayer configured with PostgreSQL
**When** a user has a conversation
**Then** the conversation history is persisted to the database (FR27)

**Given** a user returns to the application
**When** they open the interface
**Then** they can start a new conversation (FR28)
**And** they can access previous conversations from the sidebar (FR29)

**Given** PostgreSQL is the persistence backend
**When** the application starts
**Then** it connects using credentials from environment variables (NFR6)
**And** the shared connection pool is used by both FastAPI and Chainlit

---

## Epic 3: Trust, Citations & LLM Grounding

Every data response carries verifiable World Bank sources with pipeline-guaranteed citations. The LLM grounding boundary is enforced architecturally, preventing hallucination of data, causal explanations, predictions, or external knowledge. Citations are built deterministically from tool responses by the chat layer, not generated by the LLM, ensuring journalists can trust every source attribution.

**Design rationale:** LLMs are structurally unreliable at source attribution (ref: Nieman Lab, March 2026). Rather than relying on prompt instructions for citation formatting, the citation pipeline intercepts MCP tool responses and builds a structured citation registry server-side. The LLM's only citation responsibility is placing `[n]` markers in prose. This architectural decision directly addresses Data360 Challenge pillars 03 (Shielding the Pipeline) and 04 (Digital Passport for Facts).

### Story 3.1: System Prompt for LLM Grounding Boundary

As a product owner,
I want the LLM strictly constrained to narrate only data returned by the API,
So that users can trust every claim in the response is backed by official World Bank data.

**Acceptance Criteria:**

**Given** the system prompt in `app/prompts.py`
**When** Claude receives data from MCP tools
**Then** it narrates only the data values, trends, and comparisons present in the tool results (FR18)
**And** it never adds causal explanations not present in the API data (FR19)
**And** it never generates predictions or forecasts (FR20)
**And** it never adds external knowledge or editorial judgment (FR21)

**Given** a user asks "Why did CO2 emissions increase in Brazil?"
**When** Claude processes the question
**Then** it responds that it can report what the World Bank indicators show but cannot explain causation beyond what the data contains (FR22)

**Given** a user pushes for opinions or predictions
**When** Claude processes the follow-up
**Then** it maintains the grounding boundary and redirects to what the data shows

**Given** the system prompt citation instructions
**When** Claude formats a data-bearing response
**Then** it uses IEEE-style numbered markers `[1]`, `[2]`, etc. in prose next to data claims
**And** it does NOT generate the reference list itself (the server appends it)
**And** markers are assigned in order of first appearance
**And** the same source (database + indicator combination) reuses its original number

### Story 3.2: Citation Registry Pipeline

As a journalist,
I want every data point to include its World Bank source attribution built from the data pipeline (not LLM-generated),
So that I can cite it in my publications with absolute confidence in accuracy.

**Acceptance Criteria:**

**Given** Claude calls MCP tools that return data records with `CITATION_SOURCE` fields
**When** the agentic loop in `app/chat.py` completes
**Then** the chat layer builds a `references: list[dict]` from all tool responses containing `CITATION_SOURCE` (FR8)
**And** each reference entry contains: `id` (int), `source` (str), `indicator_code` (str), `indicator_name` (str), `database_id` (str), `years` (str, collapsed range), `type` ("api" or "document")
**And** document references additionally contain: `filename`, `upload_date`, `page`/`chunk` fields

**Given** the citation registry is built
**When** deduplication is applied
**Then** one reference per unique combination of database + indicator (FR12)
**And** different countries or years under the same indicator share one reference number
**And** different indicators from the same database get separate reference numbers

**Given** the structured citation registry
**When** the response is rendered
**Then** a fallback markdown reference list is appended to the response text
**And** the format follows IEEE-light style: `[1] World Bank, "CO2 emissions, total (kt)," World Development Indicators (EN.ATM.CO2E.KT), 2015-2022.`
**And** document citations follow: `[3] "Relatório de Riscos," CEMADEM (uploaded 2026-04-01), p. 12.`
**And** the reference list title adapts to conversation language ("References", "Referências", "Referencias", etc.) (FR9)

**Given** a response that contains no data points (clarification questions, "no data found")
**When** the citation registry is evaluated
**Then** no reference list is appended

**Implementation notes:**
- New module `app/citations.py` for citation registry logic (extraction, deduplication, formatting)
- Integration point: `_agentic_loop()` in `app/chat.py` intercepts tool results before final response
- The structured `references` list is attached to the Chainlit message metadata for Epic 9 UI consumption

### Story 3.3: Data Freshness Transparency

As a researcher,
I want to see the most recent data year for every data point and be warned about stale data,
So that I understand the recency of the information I'm using.

**Acceptance Criteria:**

**Given** Claude generates a response with data
**When** the response is displayed
**Then** every data point shows the most recent data year available (FR10)
**And** the year is extracted from `TIME_PERIOD` / `LATEST_DATA` fields in the API response

**Given** data where the most recent year is more than 2 years old
**When** the response is generated
**Then** Claude includes an explicit warning about data staleness (FR11)
**And** the warning distinguishes between "this is the latest available" vs "more recent data may exist"

**Given** a multi-country comparison where data years differ
**When** the response is generated
**Then** each country's data year is shown individually
**And** discrepancies in data recency are flagged transparently

**Given** the citation registry is built in Story 3.2
**When** year ranges are extracted from tool responses
**Then** the `years` field in each reference entry reflects the actual data range (collapsed format, e.g., "2015-2022")

---

## Epic 4: Fact-Check & Claim Verification

Users can paste a climate or data claim and receive a data-grounded verdict (supported, not supported, partially supported) with World Bank source citations, enabling rapid fact-checking workflows.

### Story 4.1: Claim Input and Indicator Identification

As a fact-checker,
I want to paste a climate claim and have the system identify the relevant data indicators,
So that verification starts automatically from my input.

**Acceptance Criteria:**

**Given** a user pastes "Brazil's deforestation dropped 50% since 2020"
**When** the system processes the input
**Then** Claude identifies this as a claim to verify (FR23)
**And** uses `search_indicators` to find relevant forest/deforestation indicators (FR24)
**And** uses `get_data` to retrieve Brazil's data for the relevant time period

**Given** a claim about a topic with no matching indicators
**When** the system searches for data
**Then** it responds transparently that no relevant data was found to verify the claim
**And** provides whatever partial data is available (e.g., country-level vs. the requested regional level)

### Story 4.2: Verdict Generation with Source Citations

As a fact-checker,
I want a clear verdict on whether a claim is supported by official data,
So that I can publish a fact-check with confidence in under 15 seconds.

**Acceptance Criteria:**

**Given** the system has retrieved relevant data for a claim
**When** generating the verdict
**Then** it calculates actual values and compares them against the claimed values (FR25)
**And** returns a clear verdict: "supported", "not supported", or "partially supported" (FR26)
**And** includes full CITATION_SOURCE citations for every data point used in the verdict

**Given** a claim like "Brazil's deforestation dropped 50% since 2020"
**When** the verdict is generated
**Then** the response shows the actual data values, the calculated percentage change, and how it compares to the claimed 50%
**And** includes the exact indicator code, data source, and years used

**Given** the claim is partially correct (e.g., direction is right but magnitude is wrong)
**When** the verdict is generated
**Then** the response provides a "partially supported" verdict explaining what is correct and what isn't
**And** all claims are grounded exclusively in API data (no external knowledge, per the grounding boundary)

**Given** the full fact-check flow
**When** measuring end-to-end time
**Then** the verdict with sources is delivered in under 15 seconds (per success criteria)

---

## Epic 5: Offline Local Indicator Discovery

Users can instantly discover and search World Bank indicators without any API call, enabling faster workflows and resilience when the Data360 API is slow or unavailable. A curated set of climate-focused popular indicators provides an opinionated starting point.

**FRs covered:** FR37, FR38, FR39, FR40
**NFRs addressed:** NFR13 (offline search <50ms), NFR14 (startup load <500ms)

### Story 5.1: Popular Indicators Data File

As a developer,
I want a curated JSON file of ~25-30 popular climate and development indicators,
So that the MCP server can offer instant indicator discovery without API calls.

**Acceptance Criteria:**

**Given** the file `mcp_server/popular_indicators.json`
**When** loaded by the MCP server
**Then** it contains ~25-30 indicators across 7 climate-weighted categories (Climate & Environment, Energy, Demographics, Economy, Health, Infrastructure, Agriculture & Land Use)
**And** each indicator has `category`, `code`, `name`, and `description` fields
**And** the category distribution is weighted toward climate/environment topics (at least 40% of indicators)
**And** indicator codes match the short codes used by the Data360 API (e.g. `EN_ATM_CO2E_KT`), which map to fully-qualified indicator IDs via the `{database}_{code}` convention (e.g. `WB_WDI_EN_ATM_CO2E_KT`)
**And** the JSON file loads in under 100ms

### Story 5.2: Metadata Indicators Data File

As a developer,
I want a comprehensive JSON file of ~1500 indicator metadata records,
So that users can search the full indicator catalog offline.

**Acceptance Criteria:**

**Given** the file `mcp_server/metadata_indicators.json`
**When** loaded by the MCP server
**Then** it contains ~1500 indicator metadata records extracted from the Data360 API
**And** each record has `code`, `name`, `description`, and `source` fields
**And** the file loads into memory in under 500ms (NFR14)
**And** a script or documented process exists to regenerate this file from the live API

### Story 5.3: list_popular_indicators MCP Tool

As a user exploring World Bank data,
I want to see a curated list of popular climate and development indicators,
So that I can quickly discover relevant indicators without knowing exact codes.

**Acceptance Criteria:**

**Given** the MCP server is running
**When** a user calls `list_popular_indicators()`
**Then** the tool returns the curated indicator list from `popular_indicators.json` (FR37)
**And** no API call is made to the Data360 API
**And** the response follows the standard format: `{"success": True, "data": [...], "total_count": N, "returned_count": N, "truncated": False}`
**And** indicators are grouped by category in the response
**And** the response is returned in under 50ms (NFR13)

**Given** the MCP server has not yet loaded the popular indicators file
**When** `list_popular_indicators()` is called for the first time
**Then** the file is loaded once and cached in memory via the singleton pattern (FR40)
**And** subsequent calls reuse the cached data without re-reading the file

### Story 5.4: search_local_indicators MCP Tool

As a user querying World Bank data,
I want to search indicator metadata offline with instant results,
So that I can quickly find relevant indicators before making API calls.

**Acceptance Criteria:**

**Given** the MCP server is running
**When** a user calls `search_local_indicators(query="CO2 emissions")`
**Then** the tool searches the local metadata cache using relevance scoring (FR38):
  - Exact code match: score 100
  - Code substring: score 90
  - Word in indicator name: score 80
  - Substring in indicator name: score 70
  - Substring in description: score 40
**And** returns results sorted by relevance score descending (FR39)
**And** the response includes: `{"success": True, "query": "CO2 emissions", "total_matches": N, "data": [...], "note": "Local search - instant results from cached metadata"}`
**And** each result includes `indicator`, `name`, `description` (truncated to 200 chars), `source` (truncated to 100 chars), and `relevance_score`
**And** the response is returned in under 50ms (NFR13)

**Given** `search_local_indicators(query="xyz", limit=5)`
**When** more than 5 results match
**Then** only the top 5 by relevance score are returned

**Given** a search with no matches
**When** the query doesn't match any indicator
**Then** the tool returns `{"success": True, "query": "xyz", "total_matches": 0, "data": [], "note": "No local matches found. Try search_indicators for API-based search."}`

**Given** the metadata file has not been loaded yet
**When** `search_local_indicators()` is called for the first time
**Then** the metadata file is loaded once and cached in memory (FR40)

### Story 5.5: Offline Indicator Search Test Suite

As a developer,
I want automated tests for the offline search tools and indicator cache,
So that I can verify correctness and catch regressions.

**Acceptance Criteria:**

**Given** the test suite in `tests/mcp_server/`
**When** running `uv run pytest tests/mcp_server/test_indicator_cache.py`
**Then** all tests pass

**Given** `test_indicator_cache.py`
**When** tests run
**Then** it tests relevance scoring (exact code match gets 100, code substring gets 90, etc.)
**And** tests result ordering (highest relevance first)
**And** tests limit parameter (returns at most `limit` results)
**And** tests empty query results
**And** tests singleton caching (file loaded only once across multiple calls)
**And** tests `list_popular_indicators` returns correct structure
**And** tests `search_local_indicators` returns correct response format

---

## Epic 6: Temporal Coverage Check

Users can check which years have data for a given indicator before requesting data, preventing failed API calls and enabling smarter data retrieval workflows.

**FRs covered:** FR41, FR42, FR43
**NFRs addressed:** NFR9 (graceful API failure), NFR12 (transport-agnostic)

### Story 6.1: get_temporal_coverage MCP Tool

As a user exploring climate data,
I want to check what years have data for an indicator before requesting data,
So that I can avoid failed API calls and know the data availability upfront.

**Acceptance Criteria:**

**Given** the MCP server is running
**When** a user calls `get_temporal_coverage(indicator="WB_WDI_SP_POP_TOTL", database="WB_WDI")`
**Then** the tool calls the existing `get_metadata` endpoint via `data360_client.py` with OData filter: `"&$filter=series_description/idno eq 'WB_WDI_SP_POP_TOTL'"` (FR42)
**And** extracts `time_periods` from the `series_description` in the metadata response
**And** returns: `{"success": True, "start_year": 1960, "end_year": 2023, "latest_year": 2023, "available_years": [1960, 1961, ..., 2023]}`

**Given** the indicator has no temporal coverage data in the metadata
**When** the tool processes the response
**Then** it returns `{"success": True, "start_year": null, "end_year": null, "latest_year": null, "available_years": [], "note": "No temporal coverage data found for this indicator"}`

**Given** the Data360 API is unavailable
**When** the tool is called
**Then** it returns the standard error format: `{"success": False, "error": "<descriptive message>", "error_type": "api_error"}`

**Given** the tool docstring
**When** Claude reads the tool description
**Then** the description recommends the 3-step workflow: `search_indicators → get_temporal_coverage → get_data` (FR43)

### Story 6.2: Temporal Coverage Test Suite

As a developer,
I want automated tests for the temporal coverage tool,
So that I can verify correct metadata extraction and error handling.

**Acceptance Criteria:**

**Given** the test suite in `tests/mcp_server/`
**When** running temporal coverage tests
**Then** all tests pass

**Given** `test_temporal_coverage.py`
**When** tests run
**Then** it tests successful year extraction from mocked metadata response
**And** tests empty coverage scenario (no time_periods in metadata)
**And** tests API error handling (returns structured error)
**And** tests that the tool uses `data360_client.py` (not direct HTTP calls)
**And** tests response format matches the standard structure

---

## Epic 7: MCP Prompts & Resources

The MCP server provides guided workflow prompts and discoverable resources that help LLM clients execute common data analysis patterns (country comparisons, profiles, trend analysis) with consistent quality and proper citations.

**FRs covered:** FR44, FR45, FR46, FR47, FR48
**NFRs addressed:** NFR12 (transport-agnostic)

### Story 7.1: MCP Prompt Definitions

As a user exploring climate data,
I want guided workflow prompts for common analysis patterns,
So that I get comprehensive, well-structured results with proper citations every time.

**Acceptance Criteria:**

**Given** the MCP server is running
**When** a client lists available prompts
**Then** three prompts are available: `compare_countries`, `country_profile`, `trend_analysis`

**Given** a user invokes `compare_countries(indicator="CO2 emissions", countries="Brazil, India, Germany")`
**When** the prompt is rendered
**Then** it returns a 4-step instruction guiding: search indicator → check coverage → retrieve data → present ranked markdown table (FR44)
**And** the instructions specify DATA_SOURCE citations for every data point

**Given** a user invokes `country_profile(country="Brazil")`
**When** the prompt is rendered
**Then** it returns instructions to retrieve 7 key climate and development indicators: population, GDP, GDP per capita, CO2 emissions, forest area, renewable energy, electricity access (FR45)
**And** instructions include checking temporal coverage for each indicator
**And** the output format is a structured summary with DATA_SOURCE citations

**Given** a user invokes `trend_analysis(indicator="deforestation", country="Brazil", start_year="2010", end_year="2023")`
**When** the prompt is rendered
**Then** it returns a 5-step instruction guiding: search → coverage → retrieve → filter years → analyze trend pattern (FR46)
**And** trend pattern analysis includes direction (rising/falling/stable), rate (accelerating/decelerating/linear), and inflection points
**And** the output format includes a markdown data table and narrative description

**Given** default parameters for `trend_analysis`
**When** `start_year` and `end_year` are not specified
**Then** they default to "2010" and "2023" respectively

### Story 7.2: MCP Resource Definitions

As a developer or LLM client,
I want discoverable resources that document available databases and recommended workflows,
So that I can use the MCP server effectively without reading external documentation.

**Acceptance Criteria:**

**Given** the MCP server is running
**When** a client lists available resources
**Then** three resources are available: `data360://popular-indicators`, `data360://databases`, `data360://workflow` (FR47, FR48)

**Given** a client reads `data360://popular-indicators`
**When** the resource is returned
**Then** it contains the curated popular indicators JSON from `popular_indicators.json`
**And** indicators are categorized and include code, name, and description

**Given** a client reads `data360://databases`
**When** the resource is returned
**Then** it lists 4 World Bank databases: WB_WDI, WB_HNP, WB_GDF, WB_IDS
**And** each database includes `id`, `name`, and `description`

**Given** a client reads `data360://workflow`
**When** the resource is returned
**Then** it contains markdown documentation of the recommended 3-step workflow: find indicators → check temporal coverage → retrieve data (FR48)
**And** includes tips for using popular indicators and offline search

### Story 7.3: MCP Prompts & Resources Test Suite

As a developer,
I want automated tests for all prompts and resources,
So that I can verify they render correctly and return expected content.

**Acceptance Criteria:**

**Given** the test suite in `tests/mcp_server/`
**When** running prompts and resources tests
**Then** all tests pass

**Given** `test_prompts.py`
**When** tests run
**Then** it tests each prompt renders with required parameters
**And** tests default parameter values for `trend_analysis`
**And** tests that rendered prompts contain key workflow steps
**And** tests that prompts mention DATA_SOURCE citations

**Given** `test_resources.py`
**When** tests run
**Then** it tests `data360://popular-indicators` returns valid JSON with indicator list
**And** tests `data360://databases` returns all 4 databases
**And** tests `data360://workflow` returns markdown with 3-step workflow

---

## Epic 8: Document Upload & RAG Search

Users can upload documents (PDFs, reports from CEMADEM, CPTEC, NDCs) and search them via vector similarity, enabling cross-referencing of World Bank quantitative data with sub-national/qualitative document context. Feature-flagged via DATA360_RAG_ENABLED.

**FRs covered:** FR49, FR50, FR51, FR52, FR53, FR54, FR55, FR56
**NFRs addressed:** NFR8 (no PII), NFR9 (graceful failure)
**Implementation order:** After Epic 2, before Epic 3

### Story 8.1: pgvector Schema and Database Migration

As a developer,
I want the PostgreSQL database extended with pgvector for vector storage,
So that document embeddings can be stored and queried efficiently.

**Acceptance Criteria:**

**Given** the existing docker-compose.yml with PostgreSQL
**When** updating the database setup for RAG support
**Then** docker-compose.yml uses `pgvector/pgvector:pg16` image (superset of postgres, no breaking change)
**And** `db/init.sql` is renamed to `db/001_chainlit_schema.sql` (existing Chainlit schema)
**And** `db/002_rag_schema.sql` creates a `documents` table (id UUID PK, filename TEXT, mime_type TEXT, upload_date TIMESTAMPTZ, page_count INT, metadata JSONB)
**And** `db/002_rag_schema.sql` creates a `document_chunks` table (id UUID PK, document_id UUID FK, content TEXT, page_number INT, chunk_index INT, embedding vector(384), metadata JSONB)
**And** a vector similarity index (HNSW or IVFFlat) is created on the embedding column
**And** `CREATE EXTENSION IF NOT EXISTS vector;` is included at the top of 002_rag_schema.sql
**And** existing Chainlit schema (users, threads, steps, elements, feedbacks) is unaffected
**And** tests verify schema creation and basic vector operations work

### Story 8.2: Document Processing Pipeline

As a developer,
I want a pipeline that extracts text from uploaded files, chunks it, generates embeddings, and stores them in pgvector,
So that uploaded documents become searchable.

**Acceptance Criteria:**

**Given** the `mcp_server/rag/` module
**When** processing an uploaded document
**Then** `chunker.py` extracts text from PDF (pymupdf4llm), TXT, MD, and CSV formats
**And** text is split into fixed-size chunks (512 tokens, 64 token overlap), configurable via `DATA360_RAG_CHUNK_SIZE` and `DATA360_RAG_CHUNK_OVERLAP` env vars
**And** `embeddings.py` generates 384-dimension embeddings using sentence-transformers/all-MiniLM-L6-v2
**And** the embedding model is loaded once at startup and cached for the server lifetime (singleton pattern)
**And** `store.py` stores chunks with embeddings in pgvector and retrieves by cosine similarity
**And** `processor.py` orchestrates the full pipeline: extract → chunk → embed → store
**And** each chunk preserves source metadata: filename, page number, chunk index
**And** pipeline handles errors gracefully (corrupt PDF returns structured error, empty file returns structured error)
**And** all config via `DATA360_RAG_*` env vars in `config.py`, no hardcoded values
**And** tests with fixture documents (small PDF, TXT, MD) verify the pipeline

### Story 8.3: search_documents and list_documents MCP Tools

As a user,
I want to search my uploaded documents and see what's available,
So that I can find relevant context from local sources alongside World Bank data.

**Acceptance Criteria:**

**Given** the MCP server is running with `DATA360_RAG_ENABLED=true`
**When** a user calls `search_documents(query="drought northeast Brazil", limit=5, min_score=0.3)`
**Then** the tool generates an embedding for the query and searches pgvector using the `<=>` cosine distance operator
**And** converts distance to similarity score (`similarity = 1 - distance`, higher is better)
**And** returns chunks ranked by descending similarity score, filtered by `min_score` (`similarity >= min_score`)
**And** response format: `{"success": True, "data": [...], "total_count": N, "returned_count": N, "truncated": False}`
**And** each result includes: `content`, `source` (filename), `page_number` (or null for non-paginated formats), `similarity_score`, `CITATION_SOURCE`
**And** `CITATION_SOURCE` follows format-specific patterns: PDFs use `"{filename} (uploaded {date}), p. {page}"`, TXT/MD use `"..., chunk {chunk_index}"`, CSV uses `"..., rows {start}-{end}"`

**Given** the MCP server is running with `DATA360_RAG_ENABLED=true`
**When** a user calls `list_documents(limit=20)`
**Then** the tool returns all uploaded documents with metadata (filename, upload_date, page_count, chunk_count, mime_type)
**And** response follows the standard format

**Given** the MCP server is running with `DATA360_RAG_ENABLED=false`
**When** listing available tools
**Then** `search_documents` and `list_documents` are NOT registered
**And** existing tools (search_indicators, get_data, etc.) work unchanged

**Given** a search or list operation fails
**When** the error is processed
**Then** the tool returns the standard error format: `{"success": False, "error": "<message>", "error_type": "api_error"}`

### Story 8.4: Chainlit Upload Integration

As a user,
I want to attach documents in the chat and have them processed automatically,
So that I can add context to my conversations without extra steps.

**Acceptance Criteria:**

**Given** the Chainlit app is running with `DATA360_RAG_ENABLED=true`
**When** a user attaches a file to their message
**Then** `app/chat.py` processes `message.elements` for file attachments
**And** only PDF, TXT, MD, and CSV MIME types are accepted
**And** unsupported formats receive a clear error message

**Given** a valid file is uploaded
**When** the upload is processed
**Then** the user sees processing status ("Processing document...", "Document ready for search")
**And** the document is available via `search_documents` immediately after processing completes
**And** oversized files (configurable limit) are rejected with a clear error

**Given** `DATA360_RAG_ENABLED=false`
**When** a user attaches a file
**Then** the file is not processed for RAG (standard Chainlit element handling only)

**Given** the upload flow
**When** tests run
**Then** tests verify upload processing with mock Chainlit elements
**And** tests verify MIME type filtering
**And** tests verify error handling for corrupt/empty files

### Story 8.5: System Prompt Update for Cross-Referencing

As a product owner,
I want Claude to know how to use both API tools and document search tools together,
So that responses can cross-reference quantitative World Bank data with qualitative document context.

**Acceptance Criteria:**

**Given** the system prompt in `app/prompts.py`
**When** `DATA360_RAG_ENABLED=true`
**Then** the system prompt includes a DOCUMENT SEARCH section instructing Claude to:
  - Use `search_documents` when the user mentions uploaded reports, sub-national data, or local sources
  - Cross-reference Data360 API data (quantitative) with document context (qualitative) when both are relevant
  - Format document citations using CITATION_SOURCE: `"{filename} (uploaded {date}), p. {page}"`
  - Treat document content as user-provided context, not LLM knowledge (grounding boundary extension)
  - Clearly distinguish between API-sourced data and document-sourced context in responses

**Given** `DATA360_RAG_ENABLED=false`
**When** the system prompt is generated
**Then** the DOCUMENT SEARCH section is not included
**And** existing prompt behavior is unchanged

### Story 8.6: RAG Test Suite

As a developer,
I want comprehensive tests for the entire RAG pipeline,
So that I can verify correctness and catch regressions end-to-end.

**Acceptance Criteria:**

**Given** the test directory `tests/mcp_server/test_rag/`
**When** running `uv run pytest tests/mcp_server/test_rag/`
**Then** all tests pass

**Given** `test_chunker.py`
**When** tests run
**Then** it tests text extraction from PDF, TXT, MD, CSV formats
**And** tests chunk sizing (512 tokens default) and overlap (64 tokens default)
**And** tests metadata preservation (filename, page number, chunk index)
**And** tests error handling for corrupt/empty files

**Given** `test_embeddings.py`
**When** tests run
**Then** it tests embedding generation produces 384-dimension vectors
**And** tests singleton model caching (model loaded once)

**Given** `test_store.py`
**When** tests run
**Then** it tests pgvector storage and retrieval
**And** tests cosine similarity search returns results ranked by score
**And** tests min_score filtering
**And** tests CITATION_SOURCE generation for document chunks

**Given** `test_processor.py`
**When** tests run
**Then** it tests end-to-end pipeline with fixture documents
**And** tests error propagation from each pipeline stage

**Given** `test_rag_tools.py`
**When** tests run
**Then** it tests `search_documents` tool with mocked store
**And** tests `list_documents` tool response format
**And** tests feature flag: tools not registered when `DATA360_RAG_ENABLED=false`

**Given** fixture documents in `tests/mcp_server/fixtures/documents/`
**When** used in tests
**Then** fixtures include a small PDF, TXT, and MD file with known content for assertion

---

## Epic 9: Data Provenance & Journalist Export — DONE (2026-05-07)

**Status:** Closed via course correction on 2026-05-07. Story 9.1 (server-side Data Sources block) is the complete deliverable and shipped. Stories 9.2 and 9.3 are cancelled — the dossier pivot (Epics 10–13) supersedes both: 9.2 is replaced by the dossier as the primary export artifact (Epic 11); 9.3's verification-link need moves to Epic 12 (dossier Methodology section). The citation pipeline built in 9.1 is reused by Epic 12. See `sprint-change-proposal-2026-05-07.md`.

The server deterministically appends a "Data Sources" block to every data-bearing response, built entirely from MCP tool response metadata. The LLM writes narrative only, with zero involvement in citation or source attribution. This replaces the original marker-based approach that failed due to LLM unreliability (see `epic-9-retrospective-pre-redesign.md`). Addresses Data360 Challenge pillars 04 (Digital Passport for Facts) and 05 (Permanent Source Seals).

**FRs covered:** FR8, FR9, FR58, FR59
**NFRs addressed:** None (server-side only, no UI interaction complexity)
**Implementation order:** After Epic 3
**Dependency:** Epic 3 Story 3.2 (Citation Registry Pipeline) provides the extraction and deduplication pipeline (`extract_references`, `deduplicate_references`) used by this epic.
**Supersedes:** Original Epic 9 (Citation UI & Journalist Export), reverted in PR #44. FR57 (interactive `[n]` markers) is dropped, replaced by deterministic server-side provenance.

### Story 9.1: Server-side Data Sources Block

As a user,
I want to see exactly where the data in each response came from,
So that I can trust the information and trace it back to its source.

**Acceptance Criteria:**

**Given** a chat response where tool calls returned data with `CITATION_SOURCE` fields
**When** the response is rendered in the Chainlit UI
**Then** a "Data Sources" section is appended after the narrative as a bullet-point list
**And** API sources show: source name, indicator name (if available), indicator code, year range
**And** document sources show: filename, upload date, page/chunk
**And** the section title adapts to the conversation language (en: "Data Sources", pt: "Fontes de Dados", es: "Fuentes de Datos", fr: "Sources de Donn\u00e9es", de: "Datenquellen")

**Given** a response with no tool calls or where all tool calls returned empty data
**When** the response is rendered
**Then** no Data Sources section appears

**Given** multiple tool calls returning data from the same indicator and database
**When** the Data Sources block is built
**Then** duplicate sources are merged (deduplicated by database_id + indicator_code)
**And** year ranges are collapsed into compact format (e.g., "2015-2022")

**Given** the system prompt
**When** the LLM generates a response
**Then** the prompt does NOT instruct the LLM to place `[n]` markers or generate any reference list
**And** the prompt states that a Data Sources section is appended automatically

**Implementation scope:**
- Remove `[n]` marker instructions from `app/prompts.py` (CITATION MARKERS section)
- Reformat `format_reference_list` in `app/citations.py`: bullet-point format, no `[n]` numbering
- Rename titles from "References" to "Data Sources" across all 5 languages
- Update `app/chat.py` comments (no logic changes, pipeline already works)
- Update `tests/app/test_citations.py` format assertions

### Story 9.2: Copy with Data Sources — CANCELLED (2026-05-07)

**Status:** Cancelled. The dossier document (Epic 11) is now the primary export artifact, replacing per-message chat copying. See `sprint-change-proposal-2026-05-07.md`.

As a journalist,
I want to copy a response with its data sources preserved,
So that I can paste it into articles with proper attribution.

**Acceptance Criteria:**

**Given** a chat response with a Data Sources block
**When** the user clicks a "Copy" button
**Then** the clipboard contains the full narrative text plus the Data Sources section
**And** the text pastes cleanly as plain text into Google Docs, Word, or any text editor (FR58)

**Given** a response with no Data Sources
**When** the user clicks Copy
**Then** only the narrative text is copied

### Story 9.3: Source Verification Links — CANCELLED (2026-05-07)

**Status:** Cancelled in Epic 9. Verification-link need is reassigned to Epic 12 (inline links in the dossier Methodology section), a better surface than per-message chat UI. See `sprint-change-proposal-2026-05-07.md`.

As a journalist or editor,
I want each data source to include a link to the original data,
So that I can verify any data claim in one click.

**Acceptance Criteria:**

**Given** an API-type source in the Data Sources block
**When** rendered in the UI
**Then** it includes a verification link to the Data360 indicator page (FR59)
**And** the URL format follows: `https://data360.worldbank.org/en/indicator/{indicator_code}?database_id={database_id}`

**Given** a document-type source in the Data Sources block
**When** rendered in the UI
**Then** no external link is shown (uploaded documents are local, not publicly accessible)
**And** the entry shows filename and upload date for internal reference

**Given** the verification link
**When** clicked by the user
**Then** it opens the Data360 indicator page in a new browser tab
**And** the user can independently confirm the data values referenced in the AI response
