# Story 8.1: pgvector Schema and Database Migration

**Status:** review
**Epic:** 8 — Document Upload & RAG Search
**Story Key:** 8-1-pgvector-schema-and-database-migration
**Created:** 2026-03-31

---

## Story

As a developer,
I want the PostgreSQL database extended with pgvector for vector storage,
so that document embeddings can be stored and queried efficiently.

---

## Acceptance Criteria

**AC1:** Given the existing `docker-compose.yml` with `postgres:16-alpine`, when updating the database image, then `docker-compose.yml` uses `pgvector/pgvector:pg16` (a superset of postgres:16 — no schema breaking change, just adds vector extension support).

**AC2:** Given the existing `db/init.sql` containing the Chainlit SQLAlchemy schema, when performing the migration, then `db/init.sql` is **renamed** to `db/001_chainlit_schema.sql` (exact same content, just renamed for ordered execution).

**AC3:** Given the new `db/002_rag_schema.sql`, when PostgreSQL initializes with a fresh volume, then it creates:
- `CREATE EXTENSION IF NOT EXISTS vector;` at the very top
- `documents` table: `id UUID PK`, `filename TEXT NOT NULL`, `mime_type TEXT NOT NULL`, `upload_date TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `page_count INT`, `metadata JSONB DEFAULT '{}'::jsonb`
- `document_chunks` table: `id UUID PK`, `document_id UUID FK → documents(id) ON DELETE CASCADE`, `content TEXT NOT NULL`, `page_number INT` (nullable, for non-paginated formats), `chunk_index INT NOT NULL`, `embedding vector(384)`, `metadata JSONB DEFAULT '{}'::jsonb`

**AC4:** Given `db/002_rag_schema.sql`, when the extension and tables are created, then an HNSW index is created on `document_chunks.embedding` using `vector_cosine_ops` (enables `<=>` cosine distance operator used in `search_documents`).

**AC5:** Given the renamed `db/001_chainlit_schema.sql`, when PostgreSQL runs init scripts in alphanumeric order, then the Chainlit tables (users, threads, steps, elements, feedbacks) are unaffected — same DDL, same constraints.

**AC6:** Given tests in `tests/db/`, when running `uv run pytest tests/db/`, then tests verify:
- Both SQL files exist at the correct paths
- `001_chainlit_schema.sql` contains all 5 Chainlit table definitions
- `002_rag_schema.sql` contains `CREATE EXTENSION IF NOT EXISTS vector`
- `002_rag_schema.sql` defines `embedding vector(384)`
- `002_rag_schema.sql` defines `document_chunks` and `documents` tables with all required columns
- HNSW index definition exists in `002_rag_schema.sql`

---

## ⚠️ Critical Context: Docker Volume and Init Script Ordering

**Read this before touching a single file.**

### How PostgreSQL Init Scripts Work

PostgreSQL only runs scripts in `/docker-entrypoint-initdb.d/` on a **fresh (empty) volume**. If `pgdata` already exists:

- Scripts will **NOT** re-run
- You must `docker compose down -v` to destroy the volume, then `docker compose up -d`
- This destroys all existing conversation data — expected behavior for dev environment

### File Naming Convention → Execution Order

PostgreSQL runs init scripts in **alphanumeric order**. The naming `001_` / `002_` guarantees:
1. `001_chainlit_schema.sql` runs first (creates users, threads, steps, elements, feedbacks)
2. `002_rag_schema.sql` runs second (creates vector extension + documents + document_chunks)

This ordering matters because `002` depends on the `pgvector` extension, not on the Chainlit tables.

### pgvector/pgvector:pg16 vs postgres:16-alpine

- `pgvector/pgvector:pg16` is the **official pgvector image**, based on `postgres:16`
- It ships with the `vector` extension pre-compiled — just needs `CREATE EXTENSION IF NOT EXISTS vector;`
- `postgres:16-alpine` does **not** include `vector` — the extension would be missing
- Behavior: same PostgreSQL 16, same entrypoint, same env vars, same volume mount patterns
- No changes to PostgreSQL environment variables (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`)

---

## Tasks / Subtasks

### Task 1: Update `docker-compose.yml` to use pgvector image (AC: #1)

- [x] Change image from `postgres:16-alpine` → `pgvector/pgvector:pg16`
- [x] Verify no other changes needed — all env vars and volume mounts stay identical
- [x] Exact change:

```yaml
# BEFORE
image: postgres:16-alpine

# AFTER
image: pgvector/pgvector:pg16
```

- [x] Commit: `feat(db): use pgvector/pgvector:pg16 docker image`

### Task 2: Rename `db/init.sql` → `db/001_chainlit_schema.sql` (AC: #2, #5)

- [x] `git mv db/init.sql db/001_chainlit_schema.sql` (use git mv to preserve history)
- [x] **DO NOT change a single character** of the SQL content — exact same DDL
- [x] Verify `db/` directory now has `001_chainlit_schema.sql` only (no `init.sql`)
- [x] Commit: `refactor(db): rename init.sql → 001_chainlit_schema.sql for ordered init`

### Task 3: Create `db/002_rag_schema.sql` (AC: #3, #4)

- [x] Create `db/002_rag_schema.sql` with the following exact content:

```sql
-- 002_rag_schema.sql: pgvector extension and RAG document storage
-- Requires: pgvector/pgvector:pg16 Docker image (set in docker-compose.yml)
-- Execution order: runs after 001_chainlit_schema.sql (alphanumeric init order)
-- Feature flag: DATA360_RAG_ENABLED=true required at app runtime (schema always created)

-- Enable pgvector extension (pre-compiled in pgvector/pgvector:pg16 image)
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table: tracks uploaded files with metadata
CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename    TEXT NOT NULL,
    mime_type   TEXT NOT NULL,
    upload_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    page_count  INT,                              -- NULL for non-paginated formats (TXT, MD, CSV)
    metadata    JSONB DEFAULT '{}'::jsonb
);

-- Document chunks: text segments with 384-dim vector embeddings for similarity search
-- Embedding model: sentence-transformers/all-MiniLM-L6-v2 (produces 384-dim vectors)
-- Cosine distance operator: <=> (requires vector_cosine_ops index)
-- Similarity = 1 - cosine_distance (higher score = more similar)
CREATE TABLE IF NOT EXISTS document_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    page_number INT,           -- NULL for non-paginated formats (TXT, MD, CSV)
    chunk_index INT NOT NULL,  -- 0-based position within parent document
    embedding   vector(384),   -- all-MiniLM-L6-v2: exactly 384 dimensions
    metadata    JSONB DEFAULT '{}'::jsonb
);

-- HNSW index for approximate nearest-neighbor cosine similarity search
-- HNSW chosen over IVFFlat: no minimum row requirement, better recall at query time
-- vector_cosine_ops → enables <=> operator used in search_documents tool
-- Future stories (8.2, 8.3) query: ORDER BY embedding <=> $1 LIMIT $2
CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw_idx
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
```

- [x] Verify file creates cleanly with no syntax errors (can use `psql --command "\i db/002_rag_schema.sql"` against a pgvector instance)
- [x] Commit: `feat(db): add 002_rag_schema.sql with pgvector extension and RAG tables`

### Task 4: Add schema tests (AC: #6)

- [x] Create `tests/db/__init__.py` (empty)
- [x] Create `tests/db/test_rag_schema.py` with the following test structure:

```python
"""Static analysis tests for RAG database schema files.

These tests validate SQL file content without requiring a running database.
This approach works in CI without a PostgreSQL service.
"""

from pathlib import Path

SCHEMA_DIR = Path(__file__).parent.parent.parent / "db"


class TestChainlitSchemaFile:
    """Verify 001_chainlit_schema.sql contains all required Chainlit tables."""

    def test_chainlit_schema_file_exists(self):
        assert (SCHEMA_DIR / "001_chainlit_schema.sql").exists(), \
            "db/001_chainlit_schema.sql not found — did you rename db/init.sql?"

    def test_init_sql_removed(self):
        assert not (SCHEMA_DIR / "init.sql").exists(), \
            "db/init.sql still exists — remove after renaming to 001_chainlit_schema.sql"

    def test_chainlit_tables_present(self):
        content = (SCHEMA_DIR / "001_chainlit_schema.sql").read_text()
        for table in ["users", "threads", "steps", "elements", "feedbacks"]:
            assert f'CREATE TABLE IF NOT EXISTS "{table}"' in content or \
                   f"CREATE TABLE IF NOT EXISTS {table}" in content, \
                   f"Chainlit table '{table}' missing from 001_chainlit_schema.sql"


class TestRagSchemaFile:
    """Verify 002_rag_schema.sql defines all required RAG structures."""

    def test_rag_schema_file_exists(self):
        assert (SCHEMA_DIR / "002_rag_schema.sql").exists(), \
            "db/002_rag_schema.sql not found"

    def test_vector_extension_enabled(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "CREATE EXTENSION IF NOT EXISTS vector" in content, \
            "pgvector extension declaration missing from 002_rag_schema.sql"

    def test_documents_table_defined(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS documents" in content

    def test_document_chunks_table_defined(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS document_chunks" in content

    def test_embedding_column_correct_dimensions(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "vector(384)" in content, \
            "embedding column must be vector(384) — all-MiniLM-L6-v2 produces 384 dimensions"

    def test_hnsw_index_defined(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "USING hnsw" in content, \
            "HNSW index missing — required for cosine similarity search"

    def test_cosine_ops_index(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "vector_cosine_ops" in content, \
            "vector_cosine_ops required for <=> cosine distance operator"

    def test_fk_document_id_cascade(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "ON DELETE CASCADE" in content, \
            "document_chunks.document_id FK must cascade delete"

    def test_documents_required_columns(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        for col in ["filename", "mime_type", "upload_date", "page_count", "metadata"]:
            assert col in content, f"documents table missing column: {col}"

    def test_document_chunks_required_columns(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        for col in ["document_id", "content", "page_number", "chunk_index", "embedding", "metadata"]:
            assert col in content, f"document_chunks table missing column: {col}"


class TestDbSchemaOrdering:
    """Verify file naming ensures correct init script execution order."""

    def test_schema_files_have_numeric_prefix(self):
        sql_files = sorted(SCHEMA_DIR.glob("*.sql"))
        assert len(sql_files) == 2, f"Expected 2 SQL files in db/, found: {[f.name for f in sql_files]}"

    def test_chainlit_schema_runs_first(self):
        sql_files = sorted(SCHEMA_DIR.glob("*.sql"))
        assert sql_files[0].name == "001_chainlit_schema.sql"
        assert sql_files[1].name == "002_rag_schema.sql"
```

- [x] Run `uv run pytest tests/db/ -v` — all tests should pass
- [x] All existing tests still pass (no regressions): `uv run pytest` — 191 tests (15 new + 176 existing)
- [x] Commit: `test(8-1): schema file static analysis tests`

### Task 5: Reset dev database (local only — NOT committed)

- [x] Run: `docker compose down -v && docker compose up -d`
- [x] Wait ~3 seconds for PostgreSQL to initialize
- [x] Verify both scripts ran: `docker compose logs postgres | grep -E "001_|002_"`
- [x] Verify pgvector is available: `docker compose exec postgres psql -U user -d contextclimate -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"` — returned `vector`
- [x] Verify tables exist: all 7 tables confirmed (users, threads, steps, elements, feedbacks, documents, document_chunks)
- [x] Verify HNSW index: present
- [x] This step is local verification only — no commit needed

### Task 6: Final validation

- [x] Run full test suite: `uv run pytest` — 191 passed, 1 warning
- [x] Run linter: `uv run ruff check . && uv run ruff format .` — all checks passed
- [x] Update `.env.example` with `DATA360_RAG_ENABLED=false` entry if not already present
- [x] Commit: `chore(8-1): add DATA360_RAG_ENABLED to .env.example`

---

## Dev Notes

### Files to Create/Modify

| File | Action | Notes |
|------|--------|-------|
| `docker-compose.yml` | **Modify** | Image: `postgres:16-alpine` → `pgvector/pgvector:pg16` |
| `db/init.sql` | **Delete/Rename** | `git mv db/init.sql db/001_chainlit_schema.sql` |
| `db/001_chainlit_schema.sql` | **New (renamed)** | Exact content from `init.sql`, no changes |
| `db/002_rag_schema.sql` | **New** | pgvector extension + documents + document_chunks + HNSW |
| `tests/db/__init__.py` | **New** | Empty file |
| `tests/db/test_rag_schema.py` | **New** | Static SQL content analysis tests |

**DO NOT modify:** `app/`, `mcp_server/`, `pyproject.toml`, `app/config.py`, any existing test files.

### Vector Index Choice: HNSW vs IVFFlat

Use HNSW. Rationale:
- IVFFlat requires a minimum number of rows before `VACUUM` can build the index effectively; HNSW works on empty tables
- HNSW has better recall quality at query time
- IVFFlat needs `WITH (lists = 100)` tuning (optimal value = `sqrt(row_count)`, unknown at schema creation time)
- HNSW is the pgvector recommendation for most use cases since v0.5.0

### Embedding Dimensions: Why 384

`sentence-transformers/all-MiniLM-L6-v2` always produces **384-dimension** vectors. This is fixed by the model architecture — not configurable. Future stories 8.2 (chunker) and 8.3 (search_documents) depend on this being `vector(384)`.

### Data Flow for Future Stories (context only — do NOT implement in 8.1)

```
Story 8.2: mcp_server/rag/embeddings.py generates vector(384) via all-MiniLM-L6-v2
Story 8.2: mcp_server/rag/store.py inserts into document_chunks with embedding
Story 8.3: search_documents tool queries: ORDER BY embedding <=> $query_embedding LIMIT $limit
Story 8.3: similarity = 1 - (embedding <=> $query_embedding)  [cosine distance → similarity]
```

Do NOT create `mcp_server/rag/` or `app/prompts.py` changes — those belong to 8.2–8.5.

### Feature Flag Scope for 8.1

`DATA360_RAG_ENABLED` env var gates **app-level features** (MCP tool registration, upload handling, system prompt). The **database schema is always created** regardless of the flag. This simplifies deployment — pgvector tables exist but are unused when the flag is off.

### Docker Volume: Critical Operations

```bash
# Start fresh (destroys all conversation and document data — expected in dev)
docker compose down -v && docker compose up -d

# Check init scripts ran
docker compose logs postgres | grep "running\|001_\|002_"

# Verify tables
docker compose exec postgres psql -U user -d contextclimate -c "\dt"

# Verify HNSW index
docker compose exec postgres psql -U user -d contextclimate -c "\di"
```

### Anti-Patterns

- **DON'T** modify the content of `db/init.sql` before renaming — rename first, verify, then proceed
- **DON'T** add `sentence-transformers` or `pymupdf4llm` to `pyproject.toml` — those belong to Story 8.2
- **DON'T** create `mcp_server/rag/` directory or any Python files — that's 8.2's scope
- **DON'T** use `IVFFlat` — HNSW is the right choice (see Vector Index section above)
- **DON'T** use `vector_l2_ops` or `vector_ip_ops` — must be `vector_cosine_ops` to enable `<=>` operator
- **DON'T** add `DATA360_RAG_ENABLED` checks to existing code — this story is infrastructure only
- **DON'T** forget `IF NOT EXISTS` on all CREATE statements — ensures idempotent migrations
- **DON'T** hardcode `384` anywhere outside the SQL schema — `vector(384)` in the SQL is the single source of truth
- **DON'T** use `Optional[X]` in any Python code — use `X | None` per project style
- **DON'T** use `print()` — use `logging.getLogger(__name__)` (no Python files in this story anyway)

### Existing `db/init.sql` Content (for reference)

The file has 5 Chainlit tables with `camelCase` column names (that's correct — it's Chainlit's schema format):
`users`, `threads`, `steps`, `elements`, `feedbacks`

Exact content preserved in `001_chainlit_schema.sql`. Verify with:
```bash
diff <(git show HEAD:db/init.sql) db/001_chainlit_schema.sql
# Should produce no output (identical files)
```

### Testing Standards (from project patterns)

- Use `pytest` with `asyncio_mode = "auto"` (already configured in `pyproject.toml`)
- No real database in unit/integration tests — static file analysis is appropriate for schema tests
- Tests live in `tests/db/` following the `tests/<component>/` pattern
- Run `uv run ruff check . && uv run ruff format .` before committing
- Pre-commit hook runs ruff automatically
- Branch naming: `story/8-1-pgvector-schema-and-database-migration`
- Commit format: `feat(db): ...` / `refactor(db): ...` / `test(8-1): ...`

### `.env.example` Update

Ensure `.env.example` includes the RAG feature flag:
```bash
# Feature Flags
DATA360_RAG_ENABLED=false  # Set to true to enable document upload and RAG search
```

---

## Epic 8 Cross-Story Context (DO NOT implement — context only)

| Story | Scope | Dependency on 8.1 |
|-------|-------|-------------------|
| 8.2 | `mcp_server/rag/` pipeline (chunker, embeddings, store, processor) | Needs `document_chunks` + `documents` tables from 8.1 |
| 8.3 | `search_documents` + `list_documents` MCP tools | Needs `<=>` cosine search from 8.1's HNSW index |
| 8.4 | Chainlit file upload integration in `app/chat.py` | Needs 8.2's pipeline, indirectly 8.1 schema |
| 8.5 | System prompt update in `app/prompts.py` | No direct dependency on 8.1 |
| 8.6 | Full RAG test suite | Tests schema implicitly via fixtures |

---

## Learnings from Epic 2 (Applied to This Story)

1. **⚠️ Critical Context sections** are mandatory — this story has them (Docker volume, file naming, index choice)
2. **docker compose down -v** is required for schema changes (same as 2.6's Task 1 — fresh volume requirement)
3. **Explicit anti-patterns** prevent disasters — e.g., "DON'T create mcp_server/rag/" guards scope creep
4. **git mv preserves history** — use it for the rename, not `cp` + `rm`
5. **Task by task commits** make PRs reviewable — 4-6 commits expected for this story
6. **Justfile dev scripts** are available (added in epic-2 retro): use `just dev-reset` if it covers `docker compose down -v`

---

## References

- [Source: epics.md#Story 8.1] — Acceptance criteria, table schemas, HNSW/IVFFlat note
- [Source: epics.md#Epic 8] — FR49-FR56, feature flag behavior, cross-story context
- [Source: architecture.md#Project Structure] — `db/001_chainlit_schema.sql`, `db/002_rag_schema.sql` paths
- [Source: architecture.md#Data Architecture] — `search_documents` uses `<=>` cosine distance, `similarity = 1 - distance`
- [Source: architecture.md#Cross-Cutting Concerns] — RAG data flow, feature flag isolation rules
- [Source: 2-6-conversation-persistence-and-history.md] — `db/init.sql` content, docker-compose volume mount pattern
- [Source: epic-2-retro-2026-03-31.md] — Action Item #5 (pgvector in init.sql before Epic 8), dev scripts action item
- [Source: docker-compose.yml] — Existing `postgres:16-alpine` image, volume mount `./db:/docker-entrypoint-initdb.d`
- [Source: pyproject.toml] — No pgvector/sentence-transformers deps yet (don't add in this story)

---

## Dev Agent Record

### Agent Model Used

anthropic/claude-sonnet-4-6

### Debug Log References

None — implementation completed without debug issues. Docker image pull required for first-time pgvector/pgvector:pg16 image download.

### Completion Notes List

- All 6 tasks completed successfully
- 15 new schema tests created and passing
- 191 total tests pass (no regressions)
- DB verified: vector extension active, all 7 tables present, HNSW index created
- `uv run pytest` requires `uv run python -m pytest` on this environment (pytest not in PATH)

### File List

| File | Action |
|------|--------|
| `docker-compose.yml` | Modified — `postgres:16-alpine` → `pgvector/pgvector:pg16` |
| `db/init.sql` | Deleted (renamed via git mv) |
| `db/001_chainlit_schema.sql` | New (renamed from init.sql, content unchanged) |
| `db/002_rag_schema.sql` | New — pgvector extension + documents + document_chunks + HNSW index |
| `tests/db/__init__.py` | New — empty |
| `tests/db/test_rag_schema.py` | New — 15 static SQL analysis tests |
| `.env.example` | Modified — added DATA360_RAG_ENABLED=false |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | Modified — 8-1 status updated |
