---
title: "Product Brief Distillate: Context Climate"
type: llm-distillate
source: "product-brief-bmad.md"
created: "2026-03-23"
purpose: "Token-efficient context for downstream PRD creation"
---

# Product Brief Distillate: Context Climate

## Rejected Ideas (with rationale)

- **Competitor comparison section** — user decided not to include. Tools like Climate TRACE, ClimateWatch, or ChatGPT with browsing partially overlap but were deemed irrelevant to the brief's scope
- **Post-challenge sustainability/revenue model** — user chose not to define at this stage. Not a priority for EOI or challenge submission
- **Classroom/education distribution channel** — identified as opportunity but user declined for current scope
- **NGO reporting workflows (Oxfam, WWF)** — identified as potential post-challenge revenue but skipped
- **Sub-national data for MVP** — CEMADEM/CPTEC integration explicitly deferred to post-MVP vision
- **Multi-agent architecture** — technical research rejected this in favor of LLM-centric with orchestration pattern
- **LangChain** — rejected in favor of direct Anthropic Python SDK (avoids 15+ transitive dependencies)
- **React frontend** — replaced by Chainlit for speed-to-prototype, native MCP support, and built-in conversation persistence

## Requirements Hints

- Every response MUST include DATA_SOURCE attribution from the API (non-negotiable design principle)
- Data freshness: always show most recent data year, warn when data >2 years old
- "No data found" must be transparent, never fabricate or guess
- Fact-check mode: user pastes a climate claim, system returns verdict grounded in WB data (moved to MVP)
- Shareable answer cards: nice-to-have for post-MVP (primary viral/growth mechanism per opportunity review)
- System should ask clarifying questions before building visualizations (from Kofi persona)
- Tone should be empathic and supportive for citizen users while maintaining data integrity (from Clara persona)
- Professional, data-driven tone with context for non-specialist readers (from Ana persona)
- Analytical, precise tone with methodology transparency for researchers (from Kofi persona)

## Technical Context

- **API Base URL:** `https://data360api.worldbank.org` (public, no auth required, currently in Beta)
- **Key endpoints:** `/searchv2` (vector search), `/data` (values), `/metadata` (indicator details)
- **Indicator format:** `{DATABASE}_{DATASET}_{INDICATOR_CODE}` (e.g., `WB_WDI_EN_ATM_CO2E_KT`)
- **Data granularity:** Country-level only (no sub-national). Use `WLD` area code for global comparisons
- **Pagination:** Max 1000 records per request, use `skip` parameter
- **Response fields:** `COMMENT_TS` (human-readable description), `DATA_SOURCE` (citation), `LATEST_DATA` (boolean)
- **Climate topic:** Topic 19, ~50+ indicators (CO2, renewable energy, forest area, drought, temperature anomalies, sea level)
- **Stack decision:** Chainlit + FastAPI + PostgreSQL + FastMCP 3.0 + Claude Haiku 4.5
- **Chainlit mount pattern:** Chainlit mounts as FastAPI sub-application, single ASGI deployment
- **Chainlit-datalayer:** Built-in PostgreSQL persistence for conversations (Prisma ORM + asyncpg)
- **MCP dual transport:** stdio for local dev (Claude Desktop testing), HTTP Streamable for production (Chainlit MCP client)
- **Cost estimate:** ~$0.005-0.02 per query with Haiku 4.5; ~$150-600/month at 1,000 queries/day
- **Prompt caching:** Cache system prompt + tools, 90% savings on repeated content, 5-minute duration
- **Deploy targets:** Railway or Render (Docker + managed Postgres, WebSocket support)

## Detailed User Scenarios

- **Ana (journalist):** Asks "How has drought increased in Brazil in the last 10 years?" then follows up with "Has Brazil's drought grown above the world average?" Needs clear text answers with source citations she can quote directly in articles
- **Kofi (policy analyst):** Asks "Show me CO2 emissions per capita for all African countries." Tool should ask clarifying questions before building visualizations. Wants interactive HTML graphs modifiable through conversation
- **Clara (student activist):** Preparing for COP presentations, needs emotionally resonant but data-backed narratives. Wants links to full conversation transcripts for sharing
- **Fact-checker:** During elections, pastes "Brazil's deforestation dropped 50% since 2020" and gets verdict with official WB data

## Competitive Intelligence

- **Data360 API vs Legacy WB API (v2):** Data360 is strictly superior — has vector search, disaggregation (SEX, AGE, URBANISATION), OData filtering, richer metadata (COMMENT_TS, DATA_SOURCE). Legacy at `api.worldbank.org/v2`
- **Chainlit vs React:** Chainlit chosen for speed. React would give full UI control but adds weeks of dev time. Chainlit has native MCP support, built-in streaming/markdown, session management
- **FastMCP 3.0:** Powers 70% of MCP servers across all languages. Decorator-based API, auto-generates schemas from type hints

## Open Questions

- **Data lag:** WB indicator data is often 1-3 years behind. How prominently should the system warn about this beyond showing the data year?
- **Indicator disambiguation:** A query like "drought" can map to multiple valid indicators (dry days, PDSI, SPI). Should the system ask the user to choose, or pick the most relevant one?
- **Hallucination boundary:** The LLM is constrained to narrate API data, but where exactly is the line between "interpreting" data and "adding context"? Needs explicit prompt engineering guidelines
- **API stability:** Data360 API is in Beta. Aggressive caching + abstracted client mitigates this, but breaking changes are a risk

## Scope Signals

- **In MVP:** NL queries, Data360 API via MCP, country-level data with citations, narrative responses, fact-check mode, simple time-series charts, conversation persistence, transparent no-data responses
- **Out MVP / Nice to have:** Shareable answer cards (identified as primary growth mechanism), conversation links
- **Out MVP / Vision:** Sub-national data (CEMADEM/CPTEC), document upload/RAG, multi-language, custom dashboards, advanced visualizations
- **Post-challenge:** Open-source MCP server, partnerships with fact-checking networks (IFCN, Africa Check, Chequeado), API for newsroom CMS integration

## Challenge Context

- **Challenge:** Data 360 Global Challenge (Media Party + World Bank)
- **Category:** Data Dialogue
- **Mission:** Restore trust in information, combat disinformation
- **EOI deadline:** March 31, 2026
- **Finalist announcement:** April 30, 2026
- **Prototype deadline:** May 31, 2026
- **Team:** Felipe (fullstack engineer) + Gustavo (product/journalist)
- **User goals:** Reach the final AND have a viable product that continues after the challenge

## Review Findings (Integrated)

- **Skeptic:** Personas are assumed not validated; Data360 API accuracy unverified; no competitor analysis; post-challenge sustainability undefined; WB data lag risk
- **Opportunity:** Fact-check mode is a killer feature (moved to MVP); classroom distribution underexplored; NGO workflows could fund sustainability; shareable answer cards are primary viral mechanism; Gustavo's journalist background is underutilized credibility signal; challenge is a launch platform not just a deadline
- **Challenge-fit:** Brief needed stronger trust-restoration framing over accessibility framing (applied)
