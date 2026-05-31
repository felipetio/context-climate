# Story 14.2: Raw Markdown Toggle

Status: done

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

- [x] Add `const [viewMode, setViewMode] = useState("preview")` alongside existing `isEditing` state
- [x] In the non-editing branch, render based on `viewMode`: `"raw"` → `<pre className="whitespace-pre-wrap font-mono text-sm">{content}</pre>`; `"preview"` → html_content div (with `<pre>` fallback when html_content absent)
- [x] In the toolbar, show a "Raw" / "Preview" toggle button (shown only when not editing — the toggle has no effect in Edit mode)
- [x] When exiting Edit mode (`isEditing → false`), reset `viewMode` to `"preview"` via a `toggleEdit` handler

### Task 2: Toolbar layout update (AC: #1, #2)

- [x] Toolbar has the new Preview/Raw toggle button + the existing Edit button
- [x] Preview/Raw toggle: `onClick={() => setViewMode(v => v === "preview" ? "raw" : "preview")}`
- [x] Label: `viewMode === "preview"` → `"Raw"`, `viewMode === "raw"` → `"Preview"`
- [x] Edit button behavior unchanged (now routed through `toggleEdit`, which also resets viewMode on exit)

### Task 3: Manual verification (AC: all)

- [x] App restarts cleanly with the updated JSX (no element load errors)
- [x] AC3 (no stale render) holds by construction: raw branch renders live `props.content`, which re-renders on prop update; `viewMode` is never reset on content update
- [x] Consolidated visual verification (live at felipet.io): default preview; "Raw" shows monospace raw Markdown + label flips to "Preview"; "Preview" restores HTML; Edit→View returns to Preview (AC4); Raw/Preview toggle hidden while editing

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

---

## Dev Agent Record

### Completion Notes

- `public/elements/Document.jsx`: added `viewMode` state (default `"preview"`); a `toggleEdit` handler resets `viewMode` to `"preview"` when leaving Edit mode (AC4). View-mode render order: Edit textarea → Raw `<pre className="whitespace-pre-wrap font-mono text-sm">` → preview `html_content` div → `<pre>` fallback. Toolbar gains a Raw/Preview toggle (label flips on `viewMode`), rendered only when not editing.
- AC3 (live raw view) is satisfied structurally: the raw branch binds `props.content` directly and `viewMode` is never reset on content updates, so a Python update re-renders the raw view immediately.
- No Python or dependency changes (per story). App restarts cleanly.

### File List

- `public/elements/Document.jsx` — `viewMode` state, `toggleEdit` handler, Raw/Preview toggle button, raw render branch

### Change Log

- 2026-05-31: Implemented Story 14.2 — Raw/Preview toggle in dossier panel (status → review)
