# Story 14.2: Raw Markdown Toggle

Status: ready-for-dev

## Story

As a journalist,
I want to switch between the rendered preview and the raw Markdown source,
So that I can inspect or copy the exact Markdown syntax when needed.

---

## Acceptance Criteria

**AC1:** Given the dossier is in `"dossier"` phase and in Preview mode (default), when the user clicks the "Raw" button, then the panel displays `props.content` in a read-only `<pre>` with `font-mono text-sm whitespace-pre-wrap` classes, and the button label changes to "Preview".

**AC2:** Given the panel is in Raw mode, when the user clicks the "Preview" button, then the panel returns to the HTML-rendered view from Story 14.1, and the button label changes back to "Raw".

**AC3:** Given the panel is in Raw mode, when `props.content` updates from Python (new dossier content arrives), then the raw view immediately reflects the updated content (no stale render).

**AC4:** Given the user is in Edit mode (existing functionality), when they click "View" to exit edit mode, then the panel returns to Preview mode (not Raw mode).

---

## Tasks / Subtasks

### Task 1: Add `viewMode` state to `Document.jsx` (AC: #1, #2, #4)

- [ ] Add `const [viewMode, setViewMode] = useState("preview")` alongside existing `isEditing` state
- [ ] In the non-editing branch, render based on `viewMode`:
  - `"preview"`: `<div dangerouslySetInnerHTML={{ __html: props.html_content ?? "" }} className="prose prose-sm max-w-none" />` (or `<pre>` fallback if `html_content` absent)
  - `"raw"`: `<pre className="font-mono text-sm whitespace-pre-wrap">{content ?? ""}</pre>`
- [ ] In the toolbar, show a "Raw" / "Preview" toggle button (separate from the existing Edit button)
- [ ] When exiting Edit mode (`isEditing → false`), reset `viewMode` to `"preview"`

### Task 2: Toolbar layout update (AC: #1, #2)

- [ ] Toolbar now has two controls: the new Preview/Raw toggle button + the existing Edit button
- [ ] Preview/Raw toggle: `onClick={() => setViewMode(v => v === "preview" ? "raw" : "preview")}`
- [ ] Label: when `viewMode === "preview"` show `"Raw"`, when `viewMode === "raw"` show `"Preview"`
- [ ] Edit button behavior unchanged

### Task 3: Manual verification (AC: all)

- [ ] Start app, open dossier panel with real or seeded content
- [ ] Confirm default view shows rendered HTML (AC1 baseline)
- [ ] Click "Raw" — confirm raw Markdown syntax is visible, button label becomes "Preview"
- [ ] Click "Preview" — confirm HTML rendering returns, button label becomes "Raw"
- [ ] Enter Edit mode, make a change, click View — confirm return to Preview mode, not Raw
- [ ] Trigger a Python content update — confirm Raw mode reflects new content immediately

---

## Dev Notes

### Files to change

- `public/elements/Document.jsx` — add `viewMode` state, update toolbar, update render branch

### Files NOT to touch

- `app/chat.py` — no Python changes in this story
- `pyproject.toml` — no dependency changes

### State machine

```
                  click "Raw"
  Preview ──────────────────► Raw
     ▲                          │
     │       click "Preview"    │
     └──────────────────────────┘

  Any state → Edit → (click View) → Preview
```

### Anti-patterns

- **DON'T** make Raw mode editable — it is read-only; Edit mode (existing) handles editing
- **DON'T** reset `viewMode` when `props.content` updates — only reset on Edit→View transition
