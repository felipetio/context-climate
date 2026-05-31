# Story 14.3: Download Dossier as Markdown File

Status: ready-for-dev

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
- [ ] Add a `<Button size="sm" variant="outline" onClick={handleDownloadMd}>⬇ MD</Button>` to the toolbar
- [ ] Button is only visible when `phase !== "investigating"`

### Task 2: Manual verification (AC: all)

- [ ] Start app, open dossier panel with real or seeded content
- [ ] Click "⬇ MD" — confirm browser download dialog appears with filename `dossier.md`
- [ ] Open the downloaded file — confirm it contains the raw Markdown (not HTML)
- [ ] Confirm no chat bubble appears in the conversation
- [ ] Trigger a Python content update, click "⬇ MD" again — confirm updated content in the new download

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
