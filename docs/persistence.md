# Conversation Persistence Setup Guide

Context Climate uses the [Chainlit SQLAlchemy community data layer](https://docs.chainlit.io/data-layers/sqlalchemy)
to persist conversations to PostgreSQL. Once configured, users can:

- Return to previous conversations from the sidebar
- Start new conversations with the "New Chat" button
- Resume context where they left off

---

## Prerequisites

- Docker and Docker Compose installed
- PostgreSQL service from `docker-compose.yml`

---

## Setup Steps

### Step 1: Start a fresh database with the schema

The schema DDL is in `db/init.sql` and is applied automatically by PostgreSQL on a **fresh volume**.
If you already have a `pgdata` volume from a previous run, you must destroy it first:

```bash
docker compose down -v && docker compose up -d
```

> **Important:** PostgreSQL only runs init scripts when the data directory is empty.
> If `pgdata` already exists, `db/init.sql` will be silently skipped.
> Always use `docker compose down -v` (note the `-v` flag) when resetting the schema.

### Step 2: Set `DATABASE_URL` in `.env`

Copy `.env.example` to `.env` (if you haven't already) and set the database URL:

```bash
cp .env.example .env
```

Edit `.env` and uncomment/set:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/contextclimate
```

Match the credentials to what's in `docker-compose.yml` (defaults: `user` / `password` / `contextclimate`).

> **Note:** The `+asyncpg` protocol conversion (`postgresql://` → `postgresql+asyncpg://`) is handled
> automatically by `app/data.py`. You do not need to add `+asyncpg` to your `.env` file.

### Step 3: Set `CHAINLIT_AUTH_SECRET` in your shell

Chainlit requires a JWT secret to be present in the environment when authentication is enabled.
This must be set as a **shell environment variable** (Chainlit does not read it from `.env`):

```bash
export CHAINLIT_AUTH_SECRET=your-secret-here
```

For production, generate a strong secret:

```bash
export CHAINLIT_AUTH_SECRET=$(openssl rand -hex 32)
```

Default login credentials are `demo` / `demo`. Override via:

```bash
export CHAINLIT_DEMO_USERNAME=yourname
export CHAINLIT_DEMO_PASSWORD=yourpassword
```

### Step 4: Restart the app

```bash
uv run chainlit run app/chat.py
```

Or with the FastAPI mount:

```bash
uv run uvicorn app.main:app --reload
```

The app requires a valid `DATABASE_URL` to start. With a working database connection, the Chainlit sidebar will
show previous conversations, and users can click "New Chat" to start a fresh thread.

---

## How It Works

The data layer is registered in `app/data.py` using the `@cl.data_layer` decorator:

```python
@cl.data_layer
def get_data_layer():
    conninfo = settings.database_url
    if conninfo and "postgresql://" in conninfo and "+asyncpg" not in conninfo:
        conninfo = conninfo.replace("postgresql://", "postgresql+asyncpg://")
    return SQLAlchemyDataLayer(conninfo=conninfo)
```

This registration happens when `app/data.py` is imported — either via `app/main.py` when running with the FastAPI mount, or via `app/chat.py` when running `chainlit` directly (since `app/chat.py` imports `app.data`).

Chainlit automatically:
1. Creates a `threads` row for each new conversation
2. Creates `steps` rows for each user/assistant message
3. Displays previous threads in the sidebar (UI handled by Chainlit)
4. Calls `@cl.on_chat_resume` when a user resumes a thread

The `on_chat_resume` handler in `app/chat.py` restores conversation history from the thread's
steps and reconnects to the MCP server, so Claude has full context for follow-up questions.

---

## Schema Tables

| Table | Purpose |
|-------|---------|
| `users` | User identity records |
| `threads` | One row per conversation |
| `steps` | One row per message/tool step |
| `elements` | File/image attachments |
| `feedbacks` | User thumbs up/down feedback |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Schema tables don't exist | Run `docker compose down -v && docker compose up -d` (fresh volume) |
| `+asyncpg` driver errors | Ensure `asyncpg` and `greenlet` are in dependencies (handled by `uv sync`) |
| Old conversations missing | Persistence only applies from the first run with `DATABASE_URL` set |
| Connection refused | Check that `docker compose up -d` is running and `DATABASE_URL` matches credentials |
