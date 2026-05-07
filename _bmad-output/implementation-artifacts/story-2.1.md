# Story 2.1: Web Application Setup — Chainlit + FastAPI Scaffolding

Status: done

## Story

As a developer,
I want to set up the Chainlit + FastAPI web application layer with all dependencies and configuration,
so that I have a working app skeleton that can be extended with Claude tool-use and MCP integration in subsequent stories.

## Acceptance Criteria

1. Given a fresh project checkout, when running `chainlit run app/chat.py`, then the Chainlit UI loads in the browser at `http://localhost:8000` (or the configured port) without errors
2. `pyproject.toml` includes all Epic 2 dependencies: `chainlit>=2.10.0`, `anthropic>=0.55.0`, `asyncpg>=0.30.0`, `pydantic-settings>=2.0.0`
3. `app/config.py` loads required env vars (`ANTHROPIC_API_KEY`, `DATABASE_URL`, `MCP_SERVER_URL`) from `.env` and raises a clear error if any required variable is missing at startup
4. `.env.example` is updated with all new variables documented with descriptions
5. `app/main.py` exists with a FastAPI app stub and Chainlit mounted at root (`/`)
6. `app/chat.py` exists with stub `@cl.on_chat_start` and `@cl.on_message` handlers that echo the user's message back (placeholder behavior)
7. `.chainlit/config.toml` is committed and configures the app name (`Context Climate`) and disables telemetry
8. `tests/app/__init__.py` directory structure exists and a smoke test verifies the FastAPI app starts without errors

## Tasks / Subtasks

- [ ] Task 1: Add Epic 2 dependencies to pyproject.toml (AC: #2)
  - [ ] `uv add chainlit anthropic asyncpg pydantic-settings`
  - [ ] Verify `uv lock` succeeds with no conflicts
  - [ ] Commit: `chore: add epic 2 dependencies (chainlit, anthropic, asyncpg)`

- [ ] Task 2: Create `app/` module structure with stub files (AC: #5, #6)
  - [ ] Create `app/__init__.py`
  - [ ] Create `app/config.py` — pydantic-settings `Settings` class loading env vars (see Dev Notes)
  - [ ] Create `app/main.py` — FastAPI app with Chainlit mount
  - [ ] Create `app/chat.py` — stub Chainlit handlers (echo bot)
  - [ ] Commit: `feat(app): scaffold app/ module with FastAPI + Chainlit stubs`

- [ ] Task 3: Initialize Chainlit config (AC: #7)
  - [ ] Run `chainlit init` to generate `.chainlit/config.toml`
  - [ ] Edit config: set `project.name = "Context Climate"`, `telemetry = false`
  - [ ] Commit: `chore: add chainlit config (context-climate, no telemetry)`

- [ ] Task 4: Update `.env.example` with new variables (AC: #4)
  - [ ] Add `ANTHROPIC_API_KEY`, `DATABASE_URL`, `MCP_SERVER_URL` with descriptions
  - [ ] Commit: `chore: update .env.example with epic 2 env vars`

- [ ] Task 5: Create tests/app/ structure and smoke test (AC: #8)
  - [ ] Create `tests/app/__init__.py`
  - [ ] Create `tests/app/test_main.py` with FastAPI startup smoke test
  - [ ] Run `uv run pytest tests/app/` — all tests pass
  - [ ] Commit: `test(app): add smoke test for FastAPI app startup`

- [ ] Task 6: Manual verification — Chainlit UI loads (AC: #1)
  - [ ] Run `chainlit run app/chat.py`
  - [ ] Confirm UI loads in browser and echo bot responds to a test message
  - [ ] Commit: `docs: verify chainlit smoke test in story 2.1 dev log`

## Dev Notes

### app/config.py Pattern

Use `pydantic-settings` for environment variable loading. Required fields have no defaults — missing vars raise a startup error immediately:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str
    database_url: str
    mcp_server_url: str = "http://localhost:8001"  # default for local dev

settings = Settings()
```

### app/main.py Pattern

```python
from fastapi import FastAPI
from chainlit.utils import mount_chainlit

app = FastAPI(title="Context Climate")
mount_chainlit(app=app, target="app/chat.py", path="/")
```

### app/chat.py Stub Pattern

```python
import chainlit as cl

@cl.on_chat_start
async def on_chat_start():
    await cl.Message(content="Welcome to Context Climate! Ask me about climate data.").send()

@cl.on_message
async def on_message(message: cl.Message):
    # Stub: echo back — replaced in Story 2.2
    await cl.Message(content=f"[echo] {message.content}").send()
```

### Chainlit Mount Note

`mount_chainlit` requires the `target` path to be relative to the project root. Run with:
```bash
uvicorn app.main:app --reload
# or directly:
chainlit run app/chat.py
```

### Dependencies

Epic 1 completed: MCP server is functional with HTTP Streamable transport at a configurable URL. This story adds the web app layer that will later connect to it. The `MCP_SERVER_URL` config value is wired up here but not yet used (Story 2.3 integrates it).

### Key Architectural References

- Architecture doc: `app/` structure, Chainlit mount pattern, FastAPI integration
- Architecture doc: `app/config.py` — single config per component, env vars only
- Architecture doc: Boundary 4 (Web App ↔ PostgreSQL) — custom tables live in `app/`, Chainlit-datalayer tables not touched
- PRD FR27, FR28, FR29, FR30 — conversation management (Chainlit datalayer + PostgreSQL) targeted in Stories 2.4+
- PRD NFR5, NFR6 — secrets in env vars, never in source code

## Test Cases

| # | Scenario | Steps | Expected Result |
|---|----------|-------|----------------|
| TC1 | Dependencies install cleanly | `uv sync` on clean checkout | No dependency conflicts, all packages installed |
| TC2 | Config fails fast on missing env | Run app without `.env` file | Clear error naming the missing variable(s) at startup |
| TC3 | Config loads successfully with valid env | Run with `.env` containing all required vars | `settings` object populated, no errors |
| TC4 | FastAPI app starts | `uvicorn app.main:app` | Server starts, `GET /` returns Chainlit HTML |
| TC5 | Chainlit UI loads | Open `http://localhost:8000` in browser | Chat UI renders without errors |
| TC6 | Echo bot responds | Send "hello" in chat UI | Response: "[echo] hello" appears |
| TC7 | Smoke test passes | `uv run pytest tests/app/` | All tests green |
| TC8 | `.chainlit/config.toml` committed | `git show HEAD:.chainlit/config.toml` | File present, `name = "Context Climate"`, `telemetry = false` |

## Dev Agent Record

### Agent Model Used

anthropic/claude-sonnet-4-6 (via OpenClaw subagent)

### Debug Log References

- No significant debug issues. Import-time `settings = Settings()` required `importlib.reload()` in tests to force re-evaluation with monkeypatched env vars.
- `chainlit init` found an existing config (no-op); config was edited manually.
- `chainlit run app/chat.py` confirmed UI starts at `http://localhost:8000` (verified in Task 6 shell output).

### Completion Notes List

- All 5 tasks completed and committed in order.
- Added `chainlit.md` (welcome screen) as an extra commit — generated by Chainlit at first run, customised with project-specific content.
- Task 6 (manual browser verification) was done via `chainlit run --headless` in CI-style; confirmed server starts and logs `Your app is available at http://localhost:8000`.
- 115/115 tests pass (no regressions to existing MCP server tests).
- Ruff lint and format checks clean.

### File List

- `pyproject.toml` — added Epic 2 dependencies
- `uv.lock` — updated lock file
- `app/__init__.py` — new, empty module marker
- `app/config.py` — new, pydantic-settings Settings class
- `app/main.py` — new, FastAPI app with Chainlit mount
- `app/chat.py` — new, stub Chainlit handlers (echo bot)
- `.chainlit/config.toml` — new, Chainlit config (name + telemetry=false)
- `.chainlit/translations/*.json` — new, generated by Chainlit init (23 locale files)
- `chainlit.md` — new, Chainlit welcome screen
- `.env.example` — updated with ANTHROPIC_API_KEY, DATABASE_URL, MCP_SERVER_URL
- `tests/app/__init__.py` — new, empty test package marker
- `tests/app/test_main.py` — new, 4 smoke tests for FastAPI app and config

### Change Log

- 2026-03-26: Implemented all tasks, opened PR #10 against main.
- 2026-03-26: PR reviewed by Copilot (6 comments). Fixed: added `fastapi` as explicit dep, hardened tests with `_env_file=None`. Two comments dismissed by owner (allow_origins, cot). One clarified (mcp_server_url is intentionally optional).
- 2026-03-26: Tested locally — `chainlit run app/chat.py --port 8000` confirmed UI loads. Approved and merged to main.
