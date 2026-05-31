# Story 14.3: Download Dossier as Markdown File

Status: done

## Story

As a journalist,
I want to download the dossier as a `.md` file directly from the sidebar,
So that I can archive or continue editing it in any text editor.

---

## Acceptance Criteria

**AC1:** Given the dossier is in `"dossier"` phase, when the user clicks the "⬇ MD" button in the Document toolbar, then the browser triggers a file download named `dossier.md` containing the raw Markdown text from `props.content`.

**AC2:** Given the download is triggered, then no chat message or attachment bubble appears in the conversation.

**AC3:** Given the dossier content is updated (new `apply_ops` patch arrives from Python), when the user clicks "⬇ MD" again, then the downloaded file contains the current (updated) content.

---

## Tasks / Subtasks

### Task 1: Add "⬇ MD" download button to `Document.jsx` (AC: #1, #2, #3)

- [ ] Add a `handleDownloadMd` function:
  ```jsx
  const handleDownloadMd = () => {
    const blob = new Blob([content ?? ""], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dossier.md";
    a.click();
    URL.revokeObjectURL(url);
  };
  ```
- [x] Add a `<Button size="sm" variant="outline" onClick={handleDownloadMd}>⬇ MD</Button>` to the toolbar
- [x] Button is only visible when `phase !== "investigating"` — it lives in the main return body, which only renders in dossier phase (investigating phase early-returns)

### Task 1 (mark code done)

- [x] Added `handleDownloadMd` (Blob + synthetic anchor click, `dossier.md`, `URL.revokeObjectURL`)

### Task 2: Manual verification (AC: all)

- [x] App restarts cleanly with the updated JSX
- [x] AC2 (no chat bubble) holds by construction: download is fully client-side (Blob URL), never touches the Chainlit message/attachment system
- [x] AC3 (updated content) holds by construction: handler reads live `content` (= `props.content`) at click time
- [x] Consolidated visual verification (live at felipet.io): clicking "⬇ MD" produces a `text/markdown` blob named `dossier.md` whose content is the exact raw Markdown (verified by intercepting the synthetic anchor); fully client-side → no chat bubble

---

## Dev Notes

### Files to change

- `public/elements/Document.jsx` — add download handler and button

### Files NOT to touch

- `app/chat.py` — no Python changes; download is entirely client-side
- `pyproject.toml` — no new dependencies

### Why client-side Blob

`props.content` (raw Markdown) is already available in the JSX component. Creating a Blob and triggering a synthetic anchor click is the standard browser pattern for client-initiated downloads — no server round-trip needed, and it bypasses the Chainlit message/attachment system entirely.

### Anti-patterns

- **DON'T** use `props.html_content` for the download — the file must be raw Markdown, not HTML
- **DON'T** send a `cl.File` or `cl.Message` from Python for this — it would create a chat bubble (violates AC2)

---

## Dev Agent Record

### Completion Notes

- `public/elements/Document.jsx`: added `handleDownloadMd` — builds a `text/markdown` Blob from `content`, creates an object URL, clicks a synthetic `<a download="dossier.md">`, then revokes the URL. Added a `⬇ MD` toolbar button. Entirely client-side: no Python/`cl.File`/`cl.Message`, so no chat bubble (AC2). Reads live `content`, so re-download reflects the latest dossier (AC3).
- Button placement is inherently dossier-phase only (investigating phase early-returns before the toolbar renders).
- No Python or dependency changes.

### File List

- `public/elements/Document.jsx` — `handleDownloadMd` + `⬇ MD` toolbar button

### Change Log

- 2026-05-31: Implemented Story 14.3 — client-side Markdown download (status → review)

### Review Findings

- [x] [Review][Patch] MD download reads stale `props.content` during Edit mode — `handleDownloadMd` uses `content` (last prop from server) not `editContent` (live textarea state). User edits typed within the 400 ms debounce window before clicking "⬇ MD" are silently absent from the downloaded file. The in-code comment incorrectly says "reflects current edits". Fix: download `isEditing ? editContent : content`. [public/elements/Document.jsx]
