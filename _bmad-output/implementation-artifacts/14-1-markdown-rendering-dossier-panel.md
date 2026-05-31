# Story 14.1: Markdown Rendering in the Dossier Panel

Status: draft

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

- [ ] Run `uv add markdown` (verify it is not already in `pyproject.toml`)

### Task 2: Update `update_dossier_content()` in `app/chat.py` (AC: #3)

- [ ] Import `markdown` at the top of `app/chat.py`
- [ ] In `update_dossier_content(content: str)`, compute `html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])`
- [ ] Set `doc.props["html_content"] = html_content` in addition to `doc.props["content"] = content`
- [ ] Call `await doc.update()` as before

### Task 3: Update `Document.jsx` view mode (AC: #1, #2)

- [ ] In the view-mode branch (when `!isEditing`), replace the `<pre>` with:
  ```jsx
  props.html_content
    ? <div dangerouslySetInnerHTML={{ __html: props.html_content }} className="prose prose-sm max-w-none" />
    : <pre className="whitespace-pre-wrap font-sans text-sm">{content ?? ""}</pre>
  ```
- [ ] Destructure `html_content` from `props` at the top of the component

### Task 4: Manual verification (AC: all)

- [ ] Restart the app with `just restart chainlit`
- [ ] Trigger a dossier update (run an investigation or temporarily call `update_dossier_content()` in `on_chat_start`)
- [ ] Confirm headings render as `<h1>`/`<h2>`, bold as `<strong>`, lists as `<ul>/<li>`
- [ ] Confirm raw `##` and `**` characters are NOT visible in view mode
- [ ] Confirm the `<pre>` fallback renders when `html_content` is absent

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

### Key constraint

`props.content` (raw Markdown) must remain unchanged — it is the source of truth for the edit textarea (Story 10.1 AC4) and for downloads (Stories 14.3 and 14.4). `html_content` is a derived read-only display prop.

### Anti-patterns

- **DON'T** replace `props.content` with `html_content` — the textarea edit sync and download features depend on the raw string
- **DON'T** attempt to load `react-markdown` — confirmed unavailable in Chainlit's JSX bundle (Story 10.1 Task 2)
- **DON'T** use `innerHTML` via DOM manipulation — use React's `dangerouslySetInnerHTML`

### XSS note

The HTML is generated server-side from the dossier Markdown, which is produced by the system's own LLM — not from user-supplied external input. `dangerouslySetInnerHTML` is acceptable here.
