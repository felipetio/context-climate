# Story 1.1: Project Setup and Configuration

Status: review

## Story

As a developer,
I want to initialize the Context Climate project with all dependencies and configuration,
so that I have a working development environment to build the MCP server.

## Acceptance Criteria

1. Given a clean development environment, When running project initialization, Then the project is created with pyproject.toml containing all MCP server dependencies (fastmcp, httpx)
2. The project structure includes `mcp_server/__init__.py`, `mcp_server/server.py`, `mcp_server/data360_client.py`, `mcp_server/config.py`
3. `mcp_server/config.py` contains base URL (`https://data360api.worldbank.org`), timeout settings, and pagination limits (1000 per page, 5000 cap)
4. `.env.example` documents all required environment variables
5. `.gitignore` excludes `.env`, `__pycache__`, `.venv`
6. `tests/mcp_server/__init__.py` directory structure exists

## Tasks / Subtasks

- [x] Task 1: Initialize project with uv and add MCP server dependencies (AC: #1)
  - [x] Run uv init to create pyproject.toml
  - [x] Add fastmcp and httpx dependencies
- [x] Task 2: Create mcp_server/ module structure with stub files (AC: #2)
  - [x] Create mcp_server/__init__.py
  - [x] Create mcp_server/server.py with FastMCP stub
  - [x] Create mcp_server/data360_client.py with class stub
  - [x] Create mcp_server/config.py with settings
- [x] Task 3: Implement mcp_server/config.py with all settings (AC: #3)
  - [x] Base URL, timeout, pagination limits
  - [x] Environment variable loading pattern
- [x] Task 4: Create .env.example with all required environment variables (AC: #4)
- [x] Task 5: Create .gitignore with proper exclusions (AC: #5)
- [x] Task 6: Create tests/ directory structure (AC: #6)
  - [x] Create tests/__init__.py
  - [x] Create tests/mcp_server/__init__.py
  - [x] Create tests/mcp_server/fixtures/ directory
- [x] Task 7: Verify project structure and run basic tests (AC: #1-6)

## Dev Notes

- Architecture specifies manual project setup (no starter template)
- Python 3.11+, type hints throughout
- uv for dependency management
- Organize by component (mcp_server/, app/), not by type
- No hardcoded URLs, API keys, or magic numbers
- Use Python stdlib logging, logger per module, no print statements
- Configuration via environment variables (loaded by pydantic-settings or python-dotenv)
- Week 1 scope: MCP server only (app/ is Week 2+)

### Project Structure Notes

Target structure from Architecture:
```
context-climate/
├── pyproject.toml
├── .env.example
├── .gitignore
├── mcp_server/
│   ├── __init__.py
│   ├── server.py
│   ├── data360_client.py
│   └── config.py
└── tests/
    ├── __init__.py
    └── mcp_server/
        ├── __init__.py
        ├── test_server.py (placeholder)
        ├── test_data360_client.py (placeholder)
        └── fixtures/
```

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Starter Template Evaluation]
- [Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules]
- [Source: _bmad-output/planning-artifacts/prd.md#Functional Requirements - Data Integration]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No issues encountered during implementation.

### Completion Notes List

- Initialized project with `uv init --name context-climate`, creating pyproject.toml with Python >=3.12
- Added fastmcp>=3.1.1 and httpx>=0.28.1 as dependencies, pytest>=9.0.2 as dev dependency
- Created mcp_server/ module with config.py (env-based settings), server.py (FastMCP stub), data360_client.py (async client stub with Data360Client class)
- Config uses os.getenv with sensible defaults: base URL, 30s timeout, 3 retries, 1.0s backoff base, 1000 page size, 5000 max records
- Created .env.example documenting DATA360_BASE_URL, ANTHROPIC_API_KEY, DATABASE_URL
- Updated .gitignore with comprehensive exclusions (.env, __pycache__, .venv, IDE files, OS files, pytest cache)
- Created full tests/ directory structure with fixtures/ directory
- All 10 verification tests pass covering all 6 acceptance criteria
- Removed uv-generated default main.py

### File List

- pyproject.toml (new)
- .env.example (new)
- .gitignore (modified)
- mcp_server/__init__.py (new)
- mcp_server/config.py (new)
- mcp_server/server.py (new)
- mcp_server/data360_client.py (new)
- tests/__init__.py (new)
- tests/mcp_server/__init__.py (new)
- tests/mcp_server/test_project_setup.py (new)

### Change Log

- 2026-03-24: Story 1.1 implemented - project initialization with uv, mcp_server module structure, config, env example, gitignore, tests directory. All 10 tests passing.
