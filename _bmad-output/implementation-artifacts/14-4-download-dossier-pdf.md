# Story 14.4: Download Dossier as PDF

Status: review

## Story

As a journalist,
I want to download the dossier as a PDF directly from the sidebar,
So that I can share it with editors or sources with formatting preserved.

---

## Acceptance Criteria

**AC1:** Given the dossier is in `"dossier"` phase and `props.pdf_data_url` is set, when the user clicks the "⬇ PDF" button, then the browser triggers a file download named `dossier.pdf` with formatted headings, bold, lists, and blockquotes rendered correctly.

**AC2:** Given the download is triggered, then no chat message or attachment bubble appears in the conversation.

**AC3:** Given Python calls `update_dossier_content(content)`, when the update is processed, then `weasyprint` generates PDF bytes from the HTML (reusing `html_content` from Story 14.1), the bytes are base64-encoded as `data:application/pdf;base64,...`, and stored in `doc.props["pdf_data_url"]`.

**AC4:** Given the dossier content changes (new `apply_ops` patch applied), when `update_dossier_content()` is called again, then `pdf_data_url` is regenerated with the latest content.

**AC5:** Given PDF generation fails (e.g., `weasyprint` not installed or import error), when the error is caught, then `pdf_data_url` is set to `None`, the "⬇ PDF" button is hidden in the JSX, and a warning is logged — no crash or unhandled exception.

---

## Tasks / Subtasks

### Task 1: Add `weasyprint` dependency (AC: #3)

- [x] Run `uv add weasyprint` — added `weasyprint==68.1`
- [x] Verify import works — `from weasyprint import HTML; HTML(string=...).write_pdf()` succeeds on the VPS (system libs already present, no Dockerfile change needed)
- [x] Dockerfile note: VPS already has pango/cairo/gdk-pixbuf; no change required for this environment (documented in Dev Notes for future container builds)

### Task 2: Update `update_dossier_content()` in `app/chat.py` (AC: #3, #4, #5)

- [x] Module-level `try: from weasyprint import HTML as WeasyHTML` → `WEASYPRINT_AVAILABLE`; logs a warning if unavailable
- [x] `_render_pdf_data_url(html_content)` builds the styled page, renders via `await asyncio.to_thread(WeasyHTML(...).write_pdf)` (never blocks the event loop), base64-encodes to a `data:application/pdf;base64,...` URL; returns None on unavailable/error
- [x] Derivation centralized in `_apply_derived_props(doc, content, render_pdf=...)`, called by `update_dossier_content` (AC3), `_handle_apply_ops` (final op → AC4), and `_sync_dossier_references_section`, all BEFORE the `doc.content = json.dumps(doc.props)` re-sync line
- [x] On unavailable/failure → `pdf_data_url = None`, warning logged, no crash (AC5)

### Task 3: Update `Document.jsx` (AC: #1, #2, #5)

- [x] Destructure `pdf_data_url` from `props`
- [x] Conditional `{pdf_data_url && (<a download="dossier.pdf">…⬇ PDF…</a>)}` in the dossier-phase toolbar
- [x] Falsy `pdf_data_url` → button absent (no disabled state)

### Task 4: Manual verification (AC: all) — verified live at https://felipet.io/demos/context-climate/

- [x] `weasyprint` import succeeds in the VPS environment
- [x] `⬇ PDF` button visible; its anchor is `download="dossier.pdf"` with href `data:application/pdf;base64,JVBERi0xLjcK…` (base64 decodes to `%PDF-1.7` — valid PDF, 15KB, formatted content)
- [x] No chat bubble — download is a client-side anchor to a data URL (no Python message)
- [x] AC4: per-op apply_ops refreshes html_content live and regenerates the PDF on the final op (covered by the streaming/derived-props tests; refresh count unchanged)
- [x] AC5 graceful degradation: unit tests cover WEASYPRINT_AVAILABLE=False (→ None) and a render exception (→ None), no crash

---

## Dev Notes

### Files to change

- `app/chat.py` — update `update_dossier_content()` to generate and pass `pdf_data_url`
- `public/elements/Document.jsx` — add conditional PDF download button
- `pyproject.toml` — `uv add weasyprint`
- `Dockerfile` (if containerized) — add system lib dependencies

### Files NOT to touch

- `app/prompts.py`
- `app/citations.py`
- MCP server files

### Why base64 data URL instead of a Starlette route

A `data:application/pdf;base64,...` URL embedded in the JSX props avoids adding a new HTTP endpoint, session routing, and authentication concerns. The trade-off is that large dossiers produce large props payloads — acceptable for typical dossier sizes (< 50KB Markdown → < 150KB base64 PDF).

If dossier sizes grow beyond ~200KB Markdown in the future, consider a session-keyed Starlette endpoint instead.

### weasyprint system dependencies

On Debian/Ubuntu (including the VPS):
```
libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev
```

Verify on VPS with: `python -c "from weasyprint import HTML; HTML(string='<p>test</p>').write_pdf()"`

### Anti-patterns

- **DON'T** use `props.content` (raw Markdown) for PDF generation — use `html_content` (already computed in Story 14.1) to avoid running markdown parsing twice
- **DON'T** crash if weasyprint is unavailable — degrade gracefully (AC5)
- **DON'T** show a disabled button — just hide it entirely when PDF is unavailable

---

## Dev Agent Record

### Completion Notes

- Added `weasyprint==68.1`. The VPS already has the required system libs (pango/cairo/gdk-pixbuf), so no Dockerfile change was needed here; the apt packages are noted in Dev Notes for future container builds.
- `app/chat.py`:
  - Module-level optional import sets `WEASYPRINT_AVAILABLE`; a warning is logged if unavailable (AC5).
  - `_render_pdf_data_url(html_content)` wraps the HTML in a minimal styled page and renders via `await asyncio.to_thread(WeasyHTML(...).write_pdf)` — keeping the ~0.5s synchronous render off the event loop — then base64-encodes to a `data:application/pdf;base64,...` URL. Returns None when weasyprint is unavailable or rendering raises (AC5).
  - `_apply_derived_props(doc, content, render_pdf=True)` centralizes html_content + pdf_data_url derivation so EVERY content-mutation path stays consistent. **Integration fix:** `_handle_apply_ops` and `_sync_dossier_references_section` previously mutated `doc.props["content"]` directly, which (after 14.1/14.4) would have left the rendered preview and PDF stale after a patch. They now call `_apply_derived_props`. During apply_ops streaming, html_content refreshes every op (cheap) while the PDF renders only on the final op (`render_pdf=(idx == last)`), avoiding N expensive renders; intermediate frames set `pdf_data_url=None` to keep the payload small. Rollback restores snapshotted derived props.
- `public/elements/Document.jsx`: destructured `pdf_data_url`; added a conditional `<a download="dossier.pdf">⬇ PDF</a>` button that is simply absent when `pdf_data_url` is falsy (AC5 — no disabled state).
- Tests: added 14.4 tests (pdf set when available; None when unavailable; render-error → None). Existing apply_ops streaming/rollback and references tests still pass unchanged (derived-props integration kept refresh counts intact).
- Verified live in the browser: formatted preview, Raw/Preview toggle, MD download (raw Markdown), and PDF download (valid `%PDF-1.7` data URL). Full app suite green except one pre-existing, unrelated failure in `tests/app/test_prompts.py::...asks_one_question_at_a_time` (Epic 12 prompt/test drift from commit 14d4d38 — the asserted phrase is absent from the committed prompt; not touched by Epic 14).

### File List

- `pyproject.toml` (+ `uv.lock`) — added `weasyprint` dependency
- `app/chat.py` — optional weasyprint import, `_render_pdf_data_url`, `_apply_derived_props`; wired into update_dossier_content, _handle_apply_ops, _sync_dossier_references_section; `import base64`
- `public/elements/Document.jsx` — `pdf_data_url` prop + conditional `⬇ PDF` button
- `tests/app/test_chat.py` — PDF data-url + graceful-degradation tests

### Change Log

- 2026-05-31: Implemented Story 14.4 — server-side PDF export via weasyprint with graceful degradation; derived-props kept consistent across all dossier content paths (status → review)
