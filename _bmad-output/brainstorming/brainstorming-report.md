---
stepsCompleted: [1, 2, 3, 4]
session_topic: 'Context Climate - Conversational AI for World Bank Climate Data'
session_goals: 'Define product concept, personas, MVP features, and EOI submission narrative for Data 360 Global Challenge'
selected_approach: 'ai-recommended'
techniques_used: ['Persona Storm', 'Feature Safari', 'Word Picture']
ideas_generated: ['Context Climate product concept', 'Three user personas', 'MVP feature set', 'Product name', 'EOI word picture']
---

# Brainstorming Session Report: Context Climate

**Date:** 2026-03-23
**Participants:** Felipe (fullstack engineer), Gustavo (product/journalist)
**Challenge:** Data 360 Global Challenge (Media Party + World Bank)
**Category:** Data Dialogue

## Product Concept

**Name:** Context Climate
**One-liner:** A conversational AI tool that lets journalists and citizens query World Bank climate data using natural language.

## Session Overview

**Topic:** Building a product for the Data 360 Global Challenge that makes World Bank climate data accessible through conversation.
**Goals:** Define the product concept, user personas, MVP feature set, and submission narrative for the Expression of Interest (EOI) due March 31, 2026.

## Technique 1: Persona Storm

### Persona 1: Ana (Brazilian Climate Journalist)

- **Profile:** Mid-career journalist covering environment for a major Brazilian outlet
- **Need:** Quick, reliable climate data to support stories on deadline
- **Sample Query:** "How has drought increased in Brazil in the last 10 years?"
- **Follow-up Need:** "Has Brazil's drought grown above the world average?"
- **Pain Point:** Data is spread across many sources showing different numbers
- **Output:** Clear text answers with source citations she can quote directly
- **Tone:** Professional, data-driven, with context for non-specialist readers
- **Core Action:** Ask a question in natural language, get a sourced answer

### Persona 2: Kofi (Policy Analyst at African Think Tank)

- **Profile:** Researcher preparing comparative analysis across countries
- **Need:** Visual data comparisons across multiple countries
- **Sample Query:** "Show me CO2 emissions per capita for all African countries"
- **Key Insight:** The tool should ask clarifying questions before building visualizations
- **Output:** Interactive HTML graphs that can be modified through conversation
- **Tone:** Analytical, precise, with methodology transparency
- **Core Action:** Request a visualization, refine it through dialogue

### Persona 3: Clara (Climate Activist and University Student)

- **Profile:** Young activist preparing for COP presentations
- **Need:** Emotionally resonant but data-backed narratives
- **Pain Point:** Deeply impacted by climate crisis, needs the tool to be empathic yet data-driven
- **Output:** Links to full conversation transcripts for sharing
- **Tone:** Empathic and supportive while maintaining data integrity
- **Core Action:** Explore data through a guided, conversational experience

## Technique 2: Feature Safari - MVP Definition

### MVP Features (Must Have)

| Feature | Description |
|---------|-------------|
| Natural language query | User asks climate questions in plain language |
| Data360 API integration | Direct queries to World Bank Data360 API via MCP server |
| Country-level data responses | Climate indicators at country granularity |
| Source citations | Every data point includes `DATA_SOURCE` attribution |
| Text-based answers | Clear, readable responses with context (`COMMENT_TS`) |
| Basic visualization | Simple charts/graphs from query results |

### Key Design Principles

- **Data granularity:** API responds at country level only
- **Fact-checking capability:** Valuable for verifying country-level climate claims, especially relevant near election periods
- **RAG support:** Users can upload documents (e.g., NDCs) to customize the tool's knowledge base
- **Simplicity:** Must be a simple, deliverable product for the challenge timeline

### Post-MVP Roadmap

1. **Interactive HTML visualizations** with conversational refinement (Kofi's need)
2. **Conversation history and sharing** with permanent links
3. **Climate dashboard homepage** where users can browse trending topics and start conversations
4. **Document upload (RAG)** for custom context (NDCs, national reports)
5. **Multi-language support** for broader accessibility

## Technique 3: Word Picture - EOI Submission Narrative

**Context Climate** is a conversational AI tool that transforms how journalists, researchers, and citizens interact with World Bank climate data. Instead of navigating complex databases and APIs, users simply ask questions in natural language: "How has drought changed in Brazil over the last decade?" or "Compare CO2 emissions across African countries."

The tool connects directly to the World Bank Data360 API, leveraging its vector search capabilities to find the right indicators and return accurate, sourced responses. Every answer includes proper citations so journalists can quote with confidence and researchers can verify methodology.

Built for the Data Dialogue category, Context Climate bridges the gap between rich climate datasets and the people who need them most: the storytellers, analysts, and advocates working to communicate climate reality. By making World Bank data conversational, we make it accessible, and accessible data drives better stories, better policy, and better outcomes.

**Team:** Felipe (fullstack engineer) + Gustavo (product/journalist)

## Timeline

| Date | Milestone |
|------|-----------|
| Wed Mar 25 | Felipe: AI conversing with WB API using MCP + BMAD methodology; Gustavo: drafts EOI application |
| Tue Mar 31 | **EOI submission deadline** |
| Wed Apr 30 | Finalist announcement |
| Sat May 31 | Working prototype deadline (if selected) |

## Product Name Selection

**Chosen Name:** Context Climate

**Rationale:** Directly connects to the World Bank Data360 platform while emphasizing the conversational, voice-driven interaction model. Clear, memorable, and immediately communicates what the product does.
