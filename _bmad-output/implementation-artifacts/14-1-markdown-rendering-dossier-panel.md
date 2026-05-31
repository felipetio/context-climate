# Story 14.1: Markdown Rendering in the Dossier Panel

Status: review

## Story

As a journalist,
I want the dossier panel to display formatted content instead of raw Markdown syntax,
So that I can read the dossier naturally without seeing `##` and `**` characters.

---

## Acceptance Criteria

**AC1:** Given the dossier panel is in `"dossier"` phase, when the Document component renders, then `props.html_content` (pre-rendered HTML from Python) is displayed using `dangerouslySetInnerHTML`, and headings, bold, italics, lists, and blockquotes appear formatted with Tailwind `prose prose-sm max-w-none` classes.

**AC2:** Given `props.html_content` is absent or empty, when the component renders, then it falls back to displaying `props.content` via `<pre className="whitespace-pre-wrap font-sans text-sm">`.

**AC3:** Given the Python `update_dossier_content(content)` helper is called, when it updates the Document element, then it converts `content` to HTML using the `markdown` Python package (with `tables` and `fenced_code` extensions), stores the result in `doc.props["html_content"]`, and keeps `doc.props["content"]` as the raw Markdown string (source of truth for edits and downloads).

---

## Tasks / Subtasks

### Task 1: Add `markdown` dependency (AC: #3)

- [x] Run `uv add markdown` (verify it is not already in `pyproject.toml`) — added `markdown==3.10.2`

### Task 2: Update `update_dossier_content()` in `app/chat.py` (AC: #3)

- [x] Import `markdown` at the top of `app/chat.py`
- [x] In `update_dossier_content(content: str)`, compute `html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])`
- [x] Set `doc.props["html_content"] = html_content` in addition to `doc.props["content"] = content`
- [x] **CRITICAL — set `html_content` on `doc.props` BEFORE the existing `doc.content = json.dumps(doc.props)` line** (chat.py:155). Verified: order is set props → set html_content → `doc.content = json.dumps(doc.props)` → `await doc.update()` → `await _refresh_dossier_canvas()`.

### Task 3: Update `Document.jsx` view mode (AC: #1, #2)

- [x] In the view-mode branch (when `!isEditing`), replace the `<pre>` with the `html_content ? <div dangerouslySetInnerHTML.../> : <pre.../>` fallback
- [x] Destructure `html_content` from `props` at the top of the component

### Task 4: Manual verification (AC: all)

- [x] Restart the app with `just restart chainlit` — boots cleanly, `markdown` import OK, MCP connected (9 tools), no errors in `.logs/app.log`
- [x] Unit test added (`test_update_dossier_content_computes_html_from_markdown`) asserting `<h1>`/`<strong>` rendering and raw `##` absence; content preserved as raw Markdown
- [ ] Consolidated visual verification (headings/bold/lists render; no raw `##`/`**`; `<pre>` fallback) — deferred to epic-end UI verification per review-at-epic-end plan

---

## Dev Notes

### Files to change

- `app/chat.py` — update `update_dossier_content()` to compute and pass `html_content`
- `public/elements/Document.jsx` — swap `<pre>` for `dangerouslySetInnerHTML` div in view mode
- `pyproject.toml` — `uv add markdown`

### Files NOT to touch

- `app/prompts.py`
- `app/citations.py`
- Any MCP server files

### Current code state (verified against worktree)

- `Document.jsx` view-mode line to replace (currently): `<pre className="prose prose-sm max-w-none whitespace-pre-wrap font-sans text-sm">{content ?? ""}</pre>`. It already carries the `prose prose-sm max-w-none` classes — move those onto the new `dangerouslySetInnerHTML` div, and keep the plain `whitespace-pre-wrap font-sans text-sm` `<pre>` for the fallback branch.
- `Document.jsx` already destructures `phase` (`const { content, version, phase } = props;`) and early-returns when `phase === "investigating"`, so everything in the main return body is inherently dossier-phase only.
- `update_dossier_content()` (chat.py:149-157) already does `doc.props["content"] = content` → `doc.props["version"] += 1` → `doc.content = json.dumps(doc.props)` → `await doc.update()` → `await _refresh_dossier_canvas()`.

### Key constraint

`props.content` (raw Markdown) must remain unchanged — it is the source of truth for the edit textarea (Story 10.1 AC4) and for downloads (Stories 14.3 and 14.4). `html_content` is a derived read-only display prop.

### Anti-patterns

- **DON'T** replace `props.content` with `html_content` — the textarea edit sync and download features depend on the raw string
- **DON'T** attempt to load `react-markdown` — confirmed unavailable in Chainlit's JSX bundle (Story 10.1 Task 2)
- **DON'T** use `innerHTML` via DOM manipulation — use React's `dangerouslySetInnerHTML`

### XSS note

The HTML is generated server-side from the dossier Markdown, which is produced by the system's own LLM — not from user-supplied external input. `dangerouslySetInnerHTML` is acceptable here.

---

## Dev Agent Record

### Completion Notes

- Added `markdown==3.10.2` via `uv add markdown`.
- `app/chat.py`: imported `markdown` (third-party import group); `update_dossier_content()` now sets `doc.props["html_content"] = markdown.markdown(content, extensions=["tables", "fenced_code"])` BEFORE the `doc.content = json.dumps(doc.props)` re-sync line, so the prop reaches `Document.jsx`. Raw Markdown preserved in `doc.props["content"]` as source of truth.
- `public/elements/Document.jsx`: destructured `html_content`; view-mode branch renders `<div dangerouslySetInnerHTML={{ __html: html_content }} className="prose prose-sm max-w-none" />` when `html_content` is present, falling back to `<pre className="whitespace-pre-wrap font-sans text-sm">` otherwise.
- Tests: added `test_update_dossier_content_computes_html_from_markdown`; full `tests/app/test_chat.py` suite green (155 passing). `ruff check`/`ruff format` clean.
- App restarts cleanly; no errors. Visual confirmation of rendered output is folded into the consolidated epic-end UI verification.

### File List

- `pyproject.toml` (+ `uv.lock`) — added `markdown` dependency
- `app/chat.py` — import `markdown`; compute & set `html_content` in `update_dossier_content()`
- `public/elements/Document.jsx` — render `html_content` via `dangerouslySetInnerHTML`, `<pre>` fallback
- `tests/app/test_chat.py` — added html_content rendering test

### Change Log

- 2026-05-31: Implemented Story 14.1 — Markdown→HTML rendering in dossier panel (status → review)
