---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 1
research_type: 'technical'
research_topic: 'Technology stack for Context Climate - FastAPI + PostgreSQL + React vs alternatives'
research_goals: 'Compare proposed stack against alternatives and deep-dive into architecture, optimizing for both speed-to-prototype and production readiness'
user_name: 'Felipe'
date: '2026-03-23'
web_research_enabled: true
source_verification: true
---

# Context Climate: Technology Stack Technical Research

**Date:** 2026-03-23
**Author:** Felipe
**Research Type:** Technical Stack Analysis

---

## Executive Summary

This research evaluated the technology stack for Context Climate, a conversational AI tool that enables journalists, researchers, and citizens to query World Bank climate data using natural language. The initial proposal (FastAPI + PostgreSQL + React) was validated and refined, with **Chainlit replacing React** as the frontend framework, a decision that dramatically reduces development time while providing native MCP integration.

**The recommended stack is: Chainlit + FastAPI + PostgreSQL + FastMCP 3.0 + Claude API (Haiku 4.5).**

This combination optimizes for both speed-to-prototype (challenge deadline) and production readiness, leveraging Chainlit's built-in conversation persistence, MCP client support, and streaming chat UI to eliminate weeks of frontend development. The architecture follows an LLM-centric orchestration pattern with a monolithic ASGI deployment, appropriate for a 2-person team with a tight timeline.

**Key Findings:**
- Chainlit provides native MCP support and mounts directly into FastAPI as a sub-application (single deployment)
- Chainlit-datalayer offers built-in PostgreSQL conversation persistence (Prisma ORM + asyncpg)
- FastMCP 3.0 powers 70% of MCP servers and uses a decorator-based API for minimal boilerplate
- Claude Haiku 4.5 keeps per-query costs at $0.005-0.02 with prompt caching saving 90% on repeated content
- PostgreSQL + pgvector provides a unified database for conversations, caching, and future RAG

**Top Recommendations:**
1. Build MCP server first with FastMCP (stdio), test in Claude Desktop before building the web app
2. Use Chainlit mounted in FastAPI for a single-container monolithic deployment
3. Start with Haiku 4.5, reserve Sonnet for complex multi-country queries
4. Cache World Bank API responses aggressively in PostgreSQL
5. Deploy to Railway or Render for simple Docker + managed Postgres hosting

## Table of Contents

1. [Technical Research Scope Confirmation](#technical-research-scope-confirmation)
2. [Technology Stack Analysis](#technology-stack-analysis)
3. [Integration Patterns Analysis](#integration-patterns-analysis)
4. [Architectural Patterns and Design](#architectural-patterns-and-design)
5. [Implementation Approaches and Technology Adoption](#implementation-approaches-and-technology-adoption)
6. [Technical Research Recommendations](#technical-research-recommendations)
7. [Research Methodology and Sources](#research-methodology-and-sources)

## Research Overview

This technical research was conducted on 2026-03-23 to evaluate the optimal technology stack for Context Climate, comparing the initially proposed FastAPI + PostgreSQL + React stack against alternatives. The research covered five areas: technology stack analysis, integration patterns, architectural patterns, and implementation approaches. All technical claims were verified against current web sources (2025-2026 data), with multi-source validation for critical decisions. The key pivot from the original proposal was replacing React with Chainlit after discovering its native MCP integration and built-in PostgreSQL data layer, which aligns perfectly with the project's constraints (2-person team, challenge deadline, chat-first interface).

---

## Technical Research Scope Confirmation

**Research Topic:** Technology stack for Context Climate - FastAPI + PostgreSQL + React vs alternatives
**Research Goals:** Compare proposed stack against alternatives and deep-dive into architecture, optimizing for both speed-to-prototype and production readiness

**Technical Research Scope:**

- Architecture Analysis - design patterns, frameworks, system architecture
- Implementation Approaches - development methodologies, coding patterns
- Technology Stack - languages, frameworks, tools, platforms
- Integration Patterns - APIs, protocols, interoperability
- Performance Considerations - scalability, optimization, patterns

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-03-23

## Technology Stack Analysis

### Programming Languages

**Python** is the clear primary language for this project. In 2026, Python dominates AI/ML application development, with native support for Claude's Anthropic SDK, MCP Python SDK, and the entire LLM tooling ecosystem. FastAPI leverages Python's async capabilities (asyncio) for high-concurrency AI workloads.

**TypeScript** serves the frontend layer. React/Next.js ecosystem is TypeScript-first in 2026, providing type safety for chat UI components, API client code, and data visualization logic.

_Recommendation: Python backend + TypeScript frontend aligns perfectly with Felipe's existing skills._
_Source: [FastAPI vs Django 2025](https://capsquery.com/blog/fastapi-vs-django-in-2025-which-is-best-for-ai-driven-web-apps/), [Django vs FastAPI 2026](https://www.capitalnumbers.com/blog/django-vs-fastapi/)_

### Development Frameworks and Libraries

#### Backend Frameworks Comparison

| Framework | Strengths | Weaknesses for Context Climate |
|-----------|-----------|------------------------------|
| **FastAPI** | Async-native, auto OpenAPI docs, Pydantic validation, lightweight, ideal for AI workloads | No built-in admin, requires manual session management |
| **Django** | Batteries-included, ORM, admin panel | Synchronous by default, heavier for API-first apps, overkill for this scope |
| **Next.js API Routes** | Single deployment, SSR for sharing pages | Python LLM ecosystem harder to integrate, MCP SDK is Python-native |

**Verdict: FastAPI** is the optimal choice. In 2026, it's the go-to framework for AI-driven API services, with native async support critical for streaming LLM responses and concurrent World Bank API calls.

#### Frontend Frameworks Comparison

| Framework | Strengths | Weaknesses for Context Climate |
|-----------|-----------|------------------------------|
| **React (custom)** | Full control over UI/UX, rich chart libraries (Recharts, Chart.js), shareable conversation views | More development time, must build chat UI from scratch |
| **Chainlit** | Purpose-built for LLM chat, native MCP support, built-in streaming/markdown/code rendering, session management, Apache 2.0 license | Less UI customization, Python-only (no separate frontend), harder to build custom dashboards |
| **Streamlit** | Fastest prototyping, pure Python | Not designed for multi-turn chat, poor session management, limited UI customization |
| **Next.js** | SSR for shareable links, useChat hook for streaming | Adds complexity vs plain React for this scope |

**Key Discovery: Chainlit has native MCP integration** with SSE and stdio transport, plus dedicated handlers (`@cl.on_mcp_connect`, `@cl.on_mcp_disconnect`). This could dramatically reduce development time.

**Two viable paths:**
1. **Speed path (Chainlit)**: Ship faster, native MCP + chat UI, but less control over custom visualizations and sharing features
2. **Flexibility path (React)**: More work upfront, but full control for interactive charts, shareable conversation links, and custom dashboard (post-MVP features)

_Source: [Chainlit MCP Docs](https://docs.chainlit.io/advanced-features/mcp), [Best Python AI UI Frameworks](https://getstream.io/blog/ai-chat-ui-tools/), [Streamlit vs Chainlit](https://markaicode.com/streamlit-vs-gradio-vs-chainlit-llm-ui-framework/)_

### Database and Storage Technologies

**PostgreSQL** is the recommended database, validated by current industry trends:

- **OpenAI runs PostgreSQL** for 800M+ ChatGPT users (disclosed January 2026), processing millions of queries/second across ~50 read replicas
- **pgvector** has matured to production-ready status in 2026, enabling vector search alongside relational data, reducing infrastructure costs by 60-75% vs purpose-built vector databases
- **Conversation storage**: PostgreSQL handles conversation history, user sessions, and cached API responses in a single database
- **Future RAG**: pgvector enables document embedding storage for post-MVP document upload feature without adding a separate vector database

_Alternatives considered:_
- **SQLite**: Simpler but no pgvector, no concurrent writes for production
- **MongoDB**: Flexible documents but unnecessary, PostgreSQL JSONB covers semi-structured data needs
- **Dedicated vector DB (Pinecone, Weaviate)**: Overkill when pgvector handles the scale needed

_Source: [pgvector 2026 Guide](https://www.instaclustr.com/education/vector-database/pgvector-key-features-tutorial-and-pros-and-cons-2026-guide/), [PostgreSQL for AI 2026](https://www.adwaitx.com/postgresql-ai-applications-vector-database/), [pgvector Complete Guide](https://calmops.com/database/postgresql-vector-search-pgvector-2026/)_

### LLM Integration: Claude API

**Direct Claude API via Anthropic Python SDK** is recommended over LangChain:

- Anthropic Python SDK supports sync/async clients, streaming via SSE, and native tool use
- `client.messages.stream()` enables real-time token streaming to the chat UI
- Tool use allows Claude to call World Bank API functions as structured tools
- No abstraction overhead from LangChain (15+ transitive dependencies avoided)
- SDK supports Claude 4 models with advanced features

_Source: [Anthropic Python SDK](https://platform.claude.com/docs/en/api/sdks/python), [Claude API Integration 2026](https://jishulabs.com/blog/claude-api-integration-guide-2026)_

### MCP Server Development

**MCP Python SDK v1.25.0** (January 2026) is the current stable release:

- Supports stdio, SSE, and Streamable HTTP transports
- Structured data output (spec revision 2025-06-18) for returning JSON dictionaries
- 2026 roadmap priorities: Streamable HTTP for remote deployments, Tasks primitive, enterprise readiness
- MCP is now production-grade, used at companies large and small

_Development strategy: Build MCP server with stdio transport first (testable in Claude Desktop app), then add SSE/HTTP transport for web deployment._

_Source: [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [MCP 2026 Roadmap](http://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/), [MCP PyPI](https://pypi.org/project/mcp/1.7.1/)_

### Technology Adoption Trends

_Migration Patterns:_ The industry is consolidating around PostgreSQL + pgvector for AI applications, moving away from specialized vector databases for most use cases.

_Emerging Pattern:_ FastAPI + React remains the dominant full-stack pattern for AI applications in 2026. Chainlit is gaining rapid adoption as a faster alternative for chat-first interfaces.

_MCP Ecosystem:_ MCP has moved from experimental to production-grade in 2026, with growing client support across Claude, VS Code, and third-party tools like Chainlit.

_Source: [MCP Clients Comparison 2026](https://fast.io/resources/best-mcp-clients-developers/), [Top MCP Servers 2026](https://www.datacamp.com/blog/top-mcp-servers-and-clients)_

## Integration Patterns Analysis

### System Integration Overview

Context Climate has four critical integration points:

```
User <-> Chainlit (Chat UI + MCP Client)
            |
            v
      FastAPI Backend (mounted parent app)
            |
      +-----+-----+
      |           |
Claude API    World Bank
(Tool Use)    Data360 API
      |           |
      +-----+-----+
            |
        PostgreSQL
     (conversations,
      cache, pgvector)
```

### Integration Pattern 1: Chainlit + FastAPI (Mount Pattern)

Chainlit can be **mounted as a FastAPI sub-application** using the `mount_chainlit` utility. This is the recommended integration pattern:

- Chainlit handles the chat UI, WebSocket connections (via Socket.IO), and session management
- FastAPI serves as the parent application, handling additional REST endpoints (e.g., shared conversation links, health checks)
- Authentication is delegated to the parent FastAPI app via header-based auth
- Both servers run as a single ASGI application

**Architecture benefit:** One deployment, one process, shared database connections.

_Source: [Chainlit FastAPI Integration](https://docs.chainlit.io/integrations/fastapi), [Chainlit Backend Architecture](https://deepwiki.com/Chainlit/chainlit/2.1-backend-architecture)_

### Integration Pattern 2: Claude API Tool Use

Claude's tool use is the core integration for converting natural language queries into World Bank API calls. The pattern:

1. User asks a question in natural language via Chainlit
2. Backend sends the query to Claude API with tool definitions (search indicators, fetch data, get metadata)
3. Claude decides which tools to call and with what parameters
4. Backend executes the World Bank API calls
5. Results are sent back to Claude for natural language synthesis
6. Claude generates a response with citations (DATA_SOURCE fields)

**Key features available (2025-2026):**
- **Structured outputs with `strict: true`**: Guarantees Claude's tool call inputs match your schema exactly, eliminating type mismatches
- **Streaming responses**: `client.messages.stream()` for real-time token delivery to Chainlit UI
- **Programmatic tool calling** (beta): Claude writes code to call tools in an execution container, reducing latency for multi-tool workflows and token consumption

**Tool definitions for Context Climate:**
- `search_indicators(query: str)` - Vector search on Data360 `/searchv2` endpoint
- `get_data(indicator_id: str, country: str, year_range: str)` - Fetch values from `/data` endpoint
- `get_metadata(indicator_id: str)` - Get indicator details from `/metadata` endpoint

_Source: [Claude Tool Use Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview), [Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Programmatic Tool Calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)_

### Integration Pattern 3: MCP Server (Dual Transport)

The MCP server wraps the World Bank Data360 API, exposing it as tools that any MCP client can use.

**Development strategy (two phases):**

| Phase | Transport | Purpose |
|-------|-----------|---------|
| **Phase 1: Local dev** | stdio | Test MCP server directly in Claude Desktop app. Client launches server as subprocess, communicates via stdin/stdout. Zero network overhead. |
| **Phase 2: Web deploy** | HTTP Streamable | Production transport for Chainlit integration. Supersedes SSE as of MCP spec 2025-03-26. Recommended standard in 2026. |

**Chainlit native MCP support:**
- Chainlit acts as an MCP client with built-in handlers: `@cl.on_mcp_connect` and `@cl.on_mcp_disconnect`
- Supports both stdio and Streamable HTTP connections
- Built-in UI controls for server management
- Tool calls rendered natively in the chat interface

**Bridge option:** If needed, `mcp-proxy` can convert between SSE and stdio transports.

_Source: [MCP Transports](https://dev.to/zrcic/understanding-mcp-server-transports-stdio-sse-and-http-streamable-5b1p), [Chainlit MCP](https://docs.chainlit.io/advanced-features/mcp), [FastMCP + Claude Code](https://gofastmcp.com/integrations/claude-code)_

### Integration Pattern 4: World Bank Data360 API

Public REST API, no authentication required. Three endpoints power the application:

| Endpoint | Purpose | Integration Notes |
|----------|---------|-------------------|
| `/searchv2` | Vector search for indicators from natural language | Maps user intent to indicator IDs. Returns ranked results. |
| `/data` | Fetch actual values by indicator, country, year | Returns DATA_SOURCE (citations) and COMMENT_TS (human-readable descriptions). Country-level granularity only. |
| `/metadata` | Indicator details and topic information | Used to enrich Claude's context about what an indicator measures. |

**Base URL:** `data360api.worldbank.org`
**Data scope:** 300M+ data points, 200+ economies, 10,000+ indicators (Topic 19 = Climate Change, ~50+ indicators)
**Note:** API is currently in Beta.

_Source: [Data360 API](https://data360.worldbank.org/en/api), [Data360 About](https://data360.worldbank.org/en/about)_

### Integration Pattern 5: PostgreSQL Data Layer

PostgreSQL serves three integration roles:

1. **Conversation persistence**: Store chat threads, messages, tool call history for conversation continuity and sharing
2. **API response caching**: Cache World Bank API responses to reduce latency and API load (indicators don't change frequently)
3. **Future pgvector RAG**: Store document embeddings for post-MVP document upload feature (NDCs, national reports)

**Connection pattern:** AsyncPG or SQLAlchemy async with FastAPI's lifespan for connection pool management.

### Communication Protocols Summary

| Integration | Protocol | Format | Auth |
|-------------|----------|--------|------|
| User <-> Chainlit | WebSocket (Socket.IO) | JSON | Session-based |
| Backend <-> Claude API | HTTPS | JSON (streaming SSE) | API key |
| Backend <-> World Bank API | HTTPS | JSON | None (public) |
| Backend <-> PostgreSQL | TCP | Binary (asyncpg) | Connection string |
| MCP (local) | stdio | JSON-RPC | None |
| MCP (web) | HTTP Streamable | JSON-RPC | Configurable |

## Architectural Patterns and Design

### System Architecture Pattern: LLM-Centric with Orchestration

Context Climate follows the **LLM-centric with orchestration** pattern, where Claude handles understanding and generation while an orchestration layer (FastAPI backend) decides when to call tools, retrieve data, and format responses.

This is the dominant pattern for conversational AI applications in 2026, as opposed to:
- **Pure agentic** (too autonomous for a data query tool, hard to guarantee citation accuracy)
- **Static flow** (too rigid, can't handle natural language variation)
- **Multi-agent** (overkill for the scope, adds complexity)

**Why this pattern fits:**
- User intent is clear (query climate data), but expression varies (natural language)
- Tool use is bounded (3 World Bank API endpoints), not open-ended
- Citations must be deterministic (DATA_SOURCE fields from API), not hallucinated
- Streaming responses are expected for good UX

_Source: [LLM Applications Paradigms](https://arxiv.org/html/2503.04596v2), [AI Agent Design Patterns (Microsoft)](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)_

### Application Architecture: Monolithic ASGI

```
┌─────────────────────────────────────────┐
│           Single ASGI Application        │
│                                          │
│  ┌──────────────┐  ┌─────────────────┐  │
│  │   FastAPI     │  │    Chainlit     │  │
│  │   (parent)    │  │  (mounted sub)  │  │
│  │              │  │                 │  │
│  │ - Health     │  │ - Chat UI       │  │
│  │ - Share URLs │  │ - WebSocket     │  │
│  │ - Custom API │  │ - MCP Client    │  │
│  │              │  │ - Sessions      │  │
│  └──────┬───────┘  └───────┬─────────┘  │
│         │                  │             │
│  ┌──────┴──────────────────┴─────────┐  │
│  │      Shared Service Layer          │  │
│  │                                    │  │
│  │  - Claude API Client (async)       │  │
│  │  - World Bank API Client (async)   │  │
│  │  - Database Pool (asyncpg)         │  │
│  └────────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**Why monolithic over microservices:**
- 2-person team, tight deadline (prototype by May 31)
- Single deployment unit simplifies ops
- Shared database connections and API clients reduce resource usage
- Can extract services later if needed (unlikely at this scale)

_Source: [FastAPI Scalable Architecture](https://medium.com/@moradikor296/architecting-scalable-fastapi-systems-for-large-language-model-llm-applications-and-external-cf72f76ad849)_

### Data Architecture: Chainlit-Datalayer + Custom Tables

**Discovery: Chainlit has a built-in PostgreSQL data layer** (`chainlit-datalayer` v2.0+):

| What Chainlit handles | What you add |
|----------------------|--------------|
| Conversation threads | API response cache table |
| Chat steps/messages | Indicator metadata cache |
| File attachments (S3/Azure/GCS) | pgvector embeddings (post-MVP) |
| User management | Custom sharing/permalink logic |
| Feedback collection | - |

**Database architecture:**
- Chainlit-datalayer uses **Prisma ORM** with asyncpg for async operations
- You extend the same PostgreSQL instance with custom tables for caching
- Single database, single connection pool, no data fragmentation

**Caching strategy for World Bank API:**
- Cache indicator search results (change infrequently)
- Cache data responses with TTL (daily refresh is sufficient)
- Cache metadata indefinitely (static)
- Reduces API latency from ~500ms to ~5ms for repeated queries

_Source: [Chainlit Data Persistence](https://docs.chainlit.io/data-persistence/overview), [Chainlit Datalayer Architecture](https://deepwiki.com/Chainlit/chainlit-datalayer)_

### Streaming Architecture

```
User types query
    │
    v
Chainlit WebSocket (Socket.IO)
    │
    v
Backend receives message
    │
    v
Claude API call with tools
    │
    ├── Tool use response? ──> Execute World Bank API call
    │                              │
    │                              v
    │                         Return tool result to Claude
    │                              │
    v                              v
Claude streams final response (SSE)
    │
    v
Chainlit renders tokens in real-time
```

**FastAPI streaming performance (2026 benchmarks):**
- Up to 15,000 req/s with p95 latency < 20ms
- AsyncIO event loop handles thousands of concurrent connections
- Async generators (`async def` + `yield`) for incremental data delivery
- Gunicorn + Uvicorn in production can improve throughput by ~30%

_Source: [FastAPI Async Streaming Guide](https://dasroot.net/posts/2026/03/async-streaming-responses-fastapi-comprehensive-guide/), [FastAPI LLM Scalability](https://www.capitalnumbers.com/blog/django-vs-fastapi/)_

### Security Architecture

For the challenge/prototype phase, security is lightweight:

| Concern | Approach |
|---------|----------|
| Claude API key | Environment variable, never in code |
| World Bank API | Public, no auth needed |
| User auth | Optional for MVP (Chainlit supports header-based auth via FastAPI parent) |
| Data privacy | No PII collected, all data is public World Bank data |
| Rate limiting | FastAPI async middleware + Redis (add if needed) |
| CORS | Configure for specific frontend origin |

**Post-MVP security additions:**
- User authentication (OAuth via FastAPI)
- Rate limiting per user
- API key rotation strategy

_Source: [FastAPI Rate Limiting](https://dasroot.net/posts/2026/02/rate-limiting-ai-apis-async-middleware-fastapi-redis/)_

### MCP Server Architecture (Dual-Use)

The MCP server is designed as a **standalone, reusable component**:

```
Phase 1: Local Development
┌─────────────┐    stdio     ┌──────────────┐
│ Claude       │◄────────────►│  MCP Server  │
│ Desktop App  │              │  (Python)    │
└─────────────┘              └──────┬───────┘
                                    │
                              World Bank
                              Data360 API

Phase 2: Web Application
┌─────────────┐  HTTP Stream  ┌──────────────┐
│  Chainlit    │◄─────────────►│  MCP Server  │
│  (MCP Client)│              │  (Python)    │
└─────────────┘              └──────┬───────┘
                                    │
                              World Bank
                              Data360 API
```

**Design principle:** The MCP server is transport-agnostic. Same tool logic, different transport layer. Build once, use in Claude Desktop AND in the web app.

### Deployment Architecture (Simplified)

For the challenge, keep deployment minimal:

```
┌─────────────────────┐     ┌─────────────────┐
│  Single Container    │     │  PostgreSQL      │
│                      │     │  (managed)       │
│  FastAPI + Chainlit  │────►│                  │
│  + MCP Server        │     │  + pgvector ext  │
│                      │     └─────────────────┘
│  Uvicorn (ASGI)      │
└─────────────────────┘
         │
    External APIs
    ├── Claude API
    └── World Bank Data360
```

**Single container** with Uvicorn running the ASGI app. PostgreSQL as a managed service. No Kubernetes, no multi-container orchestration needed at this scale.

## Implementation Approaches and Technology Adoption

### Development Workflow and Tooling

**Recommended development stack:**

| Tool | Purpose |
|------|---------|
| **uv** | Python package manager (required for FastMCP CLI tools, recommended for FastMCP deployment) |
| **FastMCP 3.0** | MCP server framework (released Jan 2026, powers 70% of MCP servers across all languages) |
| **MCP Inspector** | Interactive debugging tool for testing MCP servers before connecting to Claude Desktop |
| **Python 3.11+** | Better async performance over 3.10 |
| **Docker** | Containerized deployment |

**FastMCP development pattern:**
```python
from fastmcp import FastMCP

mcp = FastMCP("context-climate")

@mcp.tool()
async def search_indicators(query: str) -> dict:
    """Search World Bank climate indicators by natural language description."""
    # Call Data360 /searchv2 endpoint
    ...

mcp.run(transport="stdio")  # Phase 1: Claude Desktop
```

FastMCP uses Python type hints and docstrings to auto-generate MCP schemas, eliminating boilerplate. The decorator-based API is Pythonic and minimal.

**FastMCP 3.0 features relevant to Context Climate:**
- Component versioning
- OpenTelemetry instrumentation (observability)
- Multiple provider types (OpenAPI provider could wrap World Bank API directly)

_Source: [FastMCP Tutorial](https://www.firecrawl.dev/blog/fastmcp-tutorial-building-mcp-servers-python), [FastMCP PyPI](https://pypi.org/project/fastmcp/), [FastMCP GitHub](https://github.com/jlowin/fastmcp)_

### Testing Strategy

**MCP Server testing:**
1. **MCP Inspector** - Interactive tool for verifying tool schemas, testing tool calls, debugging responses
2. **Unit tests** - Use `ClientSession` over stdio with `StdioServerParameters` and `stdio_client()` to programmatically test tools
3. **Claude Desktop** - End-to-end testing with real LLM interaction via stdio transport

**Application testing:**
- **pytest + httpx** for FastAPI endpoint testing
- **Chainlit's built-in test utilities** for chat flow testing
- **World Bank API mocking** with `respx` or `aioresponses` for deterministic test data

_Source: [Build MCP Server](https://modelcontextprotocol.io/docs/develop/build-server), [Python MCP Server (Real Python)](https://realpython.com/python-mcp/)_

### Deployment Considerations

**Chainlit-specific deployment requirements:**
- WebSocket support is mandatory (Chainlit is built on Socket.IO)
- Sticky sessions required for auto-scaling (session affinity)
- Docker CMD: `chainlit run app.py -h --host 0.0.0.0 --port 8080`
- Or via Uvicorn when using FastAPI mount: `uvicorn app:app --host 0.0.0.0 --port 8080`

**Platform options for the challenge:**
- **Railway / Render**: Simple Docker deploys, WebSocket support, managed Postgres
- **Google Cloud Run**: Supports WebSocket, auto-scaling with session affinity
- **AWS ECS**: More complex but production-grade

_Source: [Chainlit Deploy Overview](https://docs.chainlit.io/deploy/overview), [Chainlit Docker Deployment](https://deepwiki.com/Chainlit/cookbook/10-deployment-and-infrastructure)_

### Cost Optimization and Resource Management

**Claude API pricing (current 2026):**

| Model | Input | Output | Best for |
|-------|-------|--------|----------|
| **Haiku 4.5** | $1/MTok | $5/MTok | Production queries (cost-effective, fast) |
| **Sonnet 4.6** | $3/MTok | $15/MTok | Complex multi-step queries |
| **Opus 4.6** | $5/MTok | $25/MTok | Development/testing only |

**Cost optimization strategies:**

1. **Prompt caching**: Cache system prompt + tool definitions. Cache hits cost 10% of standard input price. Saves 90% on repeated content. 5-minute cache duration (1.25x write cost) pays off after just one cache read.

2. **Model selection**: Use **Haiku 4.5** for production (fast, cheap). It handles tool use well for bounded tool sets like Context Climate's 3 tools. Reserve Sonnet for complex multi-country comparisons.

3. **Batch API** (post-MVP): 50% discount on tokens for async processing. Useful for pre-generating climate summaries or bulk data analysis.

4. **API response caching**: Cache World Bank API responses in PostgreSQL. Climate data doesn't change daily, so aggressive caching reduces both latency and Claude's context size (smaller tool results = fewer tokens).

**Estimated cost per query:**
- System prompt + tools: ~1,500 tokens input (cached after first call)
- User query + conversation context: ~500-2,000 tokens input
- Tool calls + results: ~1,000-3,000 tokens
- Response: ~500-1,500 tokens output
- **Per query with Haiku 4.5: ~$0.005-0.02** (half a cent to two cents)
- **Monthly estimate (1,000 queries/day): ~$150-600**

_Source: [Claude API Pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Claude Cost Calculator](https://costgoat.com/pricing/claude-api)_

### Risk Assessment and Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| World Bank API changes (beta) | Medium | High | Cache responses aggressively, abstract API client for easy updates |
| Chainlit breaking changes | Low | Medium | Pin version, monitor releases |
| Claude API rate limits | Low | Low | Implement exponential backoff, consider Batch API for heavy use |
| MCP spec evolution | Low | Low | FastMCP abstracts protocol details, transport-agnostic design |
| WebSocket scaling issues | Low | Medium | Sticky sessions, single-instance sufficient for challenge scale |

### Team Organization (2-Person Team)

| Person | Focus Area |
|--------|------------|
| **Felipe** (Fullstack Engineer) | MCP server, FastAPI backend, Claude API integration, Chainlit setup, PostgreSQL, deployment |
| **Gustavo** (Product/Journalist) | EOI writing, user testing, content/prompting, demo scenarios, presentation |

**Phased implementation:**

| Phase | Timeline | Deliverable |
|-------|----------|-------------|
| **Phase 1: MCP Server** | Week 1 | World Bank Data360 MCP server (stdio), testable in Claude Desktop |
| **Phase 2: Web App** | Week 2-3 | Chainlit + FastAPI app with Claude API tool use, PostgreSQL persistence |
| **Phase 3: Polish** | Week 4 | Caching, error handling, demo scenarios, deployment |

## Technical Research Recommendations

### Recommended Technology Stack

| Layer | Technology | Confidence |
|-------|-----------|------------|
| **Frontend/Chat UI** | Chainlit (mounted in FastAPI) | High |
| **Backend** | FastAPI (ASGI, async) | High |
| **LLM** | Claude API (Haiku 4.5 for prod, Sonnet for complex queries) | High |
| **MCP Framework** | FastMCP 3.0 | High |
| **Database** | PostgreSQL + pgvector + chainlit-datalayer | High |
| **Package Manager** | uv | High |
| **Deployment** | Docker + Railway/Render | Medium |

### Implementation Roadmap

```
Week 1 (Mar 25-31): MCP Server + EOI
├── Build MCP server with FastMCP (3 tools: search, data, metadata)
├── Test in Claude Desktop via stdio
├── Gustavo submits EOI
└── Validate data quality and citations

Week 2-3 (Apr 1-14): Web Application
├── FastAPI + Chainlit setup with mount pattern
├── Claude API integration with tool use + streaming
├── PostgreSQL setup (chainlit-datalayer + cache tables)
├── MCP server HTTP Streamable transport for Chainlit
└── Basic conversation persistence

Week 4 (Apr 15-30): Polish + Demo
├── API response caching
├── Error handling and edge cases
├── Demo scenarios for 3 personas (Ana, Kofi, Clara)
├── Deployment to Railway/Render
└── Finalist announcement (Apr 30)

Week 5-8 (May 1-31): Prototype Refinement (if selected)
├── Prompt caching optimization
├── Basic visualization support
├── Conversation sharing/permalinks
└── Working prototype deadline (May 31)
```

### Success Metrics

- **Query accuracy**: Claude correctly identifies and calls the right World Bank indicators >90% of the time
- **Citation accuracy**: Every data point includes DATA_SOURCE field from API response
- **Response time**: < 5 seconds for cached queries, < 15 seconds for uncached
- **Cost**: < $0.02 per query average with Haiku 4.5
- **Uptime**: > 99% during demo/evaluation period

## Research Methodology and Sources

### Research Approach

- **16+ web searches** across technology comparisons, framework documentation, pricing, and architecture patterns
- **Multi-source validation** for all critical technical claims (framework choices, pricing, MCP status)
- **Confidence level: High** for all recommendations, based on official documentation and recent (2025-2026) sources

### Key Sources

- [Chainlit Documentation](https://docs.chainlit.io/) - FastAPI integration, MCP support, data persistence, deployment
- [FastMCP GitHub](https://github.com/jlowin/fastmcp) - MCP server framework documentation
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) - Official MCP protocol SDK
- [MCP 2026 Roadmap](http://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) - Protocol evolution and priorities
- [Claude API Docs](https://platform.claude.com/docs/en/) - Tool use, structured outputs, pricing, streaming
- [World Bank Data360 API](https://data360.worldbank.org/en/api) - API documentation and endpoints
- [pgvector 2026 Guide](https://www.instaclustr.com/education/vector-database/pgvector-key-features-tutorial-and-pros-and-cons-2026-guide/) - Vector search capabilities
- [PostgreSQL for AI 2026](https://www.adwaitx.com/postgresql-ai-applications-vector-database/) - Industry consolidation trends
- [FastAPI vs Django 2026](https://www.capitalnumbers.com/blog/django-vs-fastapi/) - Framework comparison and benchmarks
- [LLM Application Paradigms](https://arxiv.org/html/2503.04596v2) - Architecture pattern classification
- [AI Agent Design Patterns (Microsoft)](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) - Orchestration patterns

---

**Technical Research Completed:** 2026-03-23
**Source Verification:** All facts cited with current (2025-2026) sources
**Confidence Level:** High, based on multiple authoritative sources
