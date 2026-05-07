---
research_type: domain
research_topic: 'World Bank Data360 API'
research_goals: 'Understand the Data360 API capabilities for building the Context Climate MCP server'
stepsCompleted: [1, 2, 3, 4]
---

# Domain Research Report: World Bank Data360 API

**Date:** 2026-03-23
**Research Focus:** API architecture, endpoints, and capabilities for Context Climate product
**Base URL:** `https://data360api.worldbank.org`

## API Overview

The World Bank Data360 API (OpenAPI 3.0.1) provides access to development indicators, climate data, and statistical datasets. It is a **public API requiring no authentication**.

**Important:** This is NOT the legacy World Bank Indicators API (`api.worldbank.org/v2`). The Data360 API is the current platform with superior capabilities including vector search.

## Endpoints

### 1. GET `/data360/data`

**Purpose:** Retrieve actual data values for indicators by country and time period.

**Key Parameters:**
- `indicator` (required) - Indicator ID (e.g., `WB_WDI_EN_ATM_CO2E_KT`)
- `areaCode` - Country/region ISO code (e.g., `BRA`, `WLD` for world)
- `year` - Specific year or range
- `skip` - Pagination offset (max 1000 records per call)

**Response includes:**
- `COMMENT_TS` - Human-readable description of the data point (valuable for AI responses)
- `DATA_SOURCE` - Source attribution for citations
- `LATEST_DATA` - Boolean indicating if this is the most recent value

### 2. POST `/data360/searchv2`

**Purpose:** Semantic/vector search for indicators using natural language.

**This is the key endpoint for Context Climate.** Users can describe what they're looking for in plain language, and the API uses vector search to find matching indicators.

**Request Body:**
```json
{
  "searchText": "drought in Brazil",
  "pageSize": 10,
  "pageNumber": 1
}
```

**Why this matters:** Dramatically reduces the AI-to-indicator mapping challenge. Instead of maintaining a static mapping of user queries to indicator IDs, we can let the API's own vector search find the right indicators.

### 3. POST `/data360/metadata`

**Purpose:** Get detailed metadata about indicators, datasets, and topics.

**Supports OData-style filtering:**
- `$filter` - Filter expression (e.g., `series_description/topics/any(t: t/name eq 'Climate Change')`)
- `$select` - Choose specific fields to return

**Climate Change Topic:** Topic 19 with ~50+ indicators covering emissions, energy, temperature, deforestation, etc.

### 4. GET `/data360/indicators`

**Purpose:** List available indicators with basic metadata.

**Useful for:** Building indicator catalogs, understanding available data coverage.

### 5. GET `/data360/disaggregation`

**Purpose:** Get disaggregation dimensions for indicators.

**Available Dimensions:**
- `SEX` - Gender breakdown
- `AGE` - Age group breakdown
- `URBANISATION` - Urban/rural breakdown
- `COMP_BREAKDOWN_1`, `COMP_BREAKDOWN_2`, `COMP_BREAKDOWN_3` - Component breakdowns

## Indicator ID Format

Format: `{DATABASE}_{DATASET}_{INDICATOR_CODE}`

Example: `WB_WDI_EN_ATM_CO2E_KT`
- `WB` = World Bank database
- `WDI` = World Development Indicators dataset
- `EN_ATM_CO2E_KT` = CO2 emissions in kilotons

## Key Climate Indicators (Topic 19)

Examples of available climate-related indicators:
- CO2 emissions (total, per capita, by sector)
- Renewable energy consumption
- Forest area and deforestation rates
- Access to electricity
- Agricultural land use
- Disaster risk indicators
- Temperature anomalies
- Sea level data

## API Constraints and Pagination

- **Max 1000 records per request** - Use `skip` parameter for pagination
- **No authentication required** - Public API
- **Country-level granularity** - Data is at national level (no sub-national)
- **`WLD` area code** - Use for global/world averages and comparisons

## Architectural Implications for MCP Server

### Recommended Query Flow

```
User Question (natural language)
    |
    v
/searchv2 (vector search to find relevant indicators)
    |
    v
/metadata (get indicator details and context)
    |
    v
/data (fetch actual values for matched indicators)
    |
    v
AI formats response with COMMENT_TS context + DATA_SOURCE citations
```

### Key Design Decisions

1. **Vector search first:** Use `/searchv2` as the primary indicator discovery mechanism rather than maintaining hardcoded mappings
2. **Citation by default:** Always include `DATA_SOURCE` in responses for journalist credibility
3. **Context from COMMENT_TS:** Use the human-readable descriptions to enrich AI responses
4. **Pagination handling:** Implement automatic pagination for large result sets (>1000 records)
5. **World reference:** Use `WLD` area code for global comparisons (e.g., "Is Brazil above world average?")

### MCP Server Tools to Implement

| Tool | Maps to Endpoint | Purpose |
|------|-----------------|---------|
| `search_indicators` | POST `/searchv2` | Find indicators from natural language |
| `get_data` | GET `/data` | Fetch data values |
| `get_metadata` | POST `/metadata` | Get indicator/topic details |
| `list_indicators` | GET `/indicators` | Browse available indicators |
| `get_disaggregation` | GET `/disaggregation` | Check available breakdowns |

## Comparison with Legacy API

| Feature | Data360 API | Legacy API (v2) |
|---------|------------|-----------------|
| Vector search | Yes (`/searchv2`) | No |
| Disaggregation | Yes (SEX, AGE, etc.) | No |
| OData filtering | Yes (`$filter`, `$select`) | No |
| Rich metadata | Yes (`COMMENT_TS`, `DATA_SOURCE`) | Limited |
| Authentication | None required | None required |
| Base URL | `data360api.worldbank.org` | `api.worldbank.org/v2` |

**The Data360 API is strictly superior for the Context Climate use case**, especially due to vector search reducing the NLP-to-indicator mapping complexity.
