# Story 14.4: Download Dossier as PDF

Status: draft

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

- [ ] Run `uv add weasyprint`
- [ ] Verify import works: `python -c "from weasyprint import HTML; print('ok')"`
- [ ] If system libs are missing (Docker/VPS), add to `Dockerfile`:
  ```dockerfile
  RUN apt-get install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0
  ```

### Task 2: Update `update_dossier_content()` in `app/chat.py` (AC: #3, #4, #5)

- [ ] At module level, attempt `from weasyprint import HTML as WeasyHTML` inside a try/except; set `WEASYPRINT_AVAILABLE = True/False`
- [ ] In `update_dossier_content(content: str)`:
  - Reuse `html_content` already computed in Story 14.1
  - If `WEASYPRINT_AVAILABLE`:
    - Wrap html in a minimal styled page:
      ```python
      full_html = f"<html><body style='font-family:sans-serif;max-width:800px;margin:2cm auto'>{html_content}</body></html>"
      pdf_bytes = WeasyHTML(string=full_html).write_pdf()
      import base64
      pdf_data_url = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode()
      ```
    - Set `doc.props["pdf_data_url"] = pdf_data_url`
  - If not available: `doc.props["pdf_data_url"] = None`; log a warning

### Task 3: Update `Document.jsx` (AC: #1, #2, #5)

- [ ] Destructure `pdf_data_url` from `props`
- [ ] In the toolbar (visible only when `phase !== "investigating"`), add:
  ```jsx
  {pdf_data_url && (
    <a href={pdf_data_url} download="dossier.pdf">
      <Button size="sm" variant="outline">⬇ PDF</Button>
    </a>
  )}
  ```
- [ ] When `pdf_data_url` is falsy, the button is simply absent — no disabled state, no error message

### Task 4: Manual verification (AC: all)

- [ ] Confirm `weasyprint` import succeeds in the VPS environment
- [ ] Start app, open dossier panel with real or seeded content
- [ ] Click "⬇ PDF" — confirm browser download dialog appears with filename `dossier.pdf`
- [ ] Open the PDF — confirm headings, bold, lists are formatted (not raw Markdown)
- [ ] Confirm no chat bubble appears in the conversation
- [ ] Trigger a Python content update, click "⬇ PDF" again — confirm updated content in the new PDF
- [ ] Test graceful degradation: temporarily make import fail, confirm button disappears and no crash occurs

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
