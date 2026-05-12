# Story 10.2: ElementSidebar Canvas Integration

Status: in-progress

## Story

As a developer,
I want the dossier canvas to open automatically in the right panel when a session starts,
So that the split-panel layout is wired up and ready for content from the first message.

---

## Acceptance Criteria

**AC1:** Given a new chat session starts, when `@cl.on_chat_start` fires, then `cl.user_session["dossier"]` is initialized as `{"phase": "investigating", "content": "", "version": 0}`.

**AC2:** Given `on_chat_start`, when initializing, then `open_dossier_canvas()` is called, which creates a `cl.CustomElement(name="Document", props={...}, display="inline")`, sets `cl.ElementSidebar` title to `"Dossier"`, and calls `cl.ElementSidebar.set_elements([doc], key="dossier-canvas")`.

**AC3:** Given the canvas is open, when `open_dossier_canvas()` returns, then the `CustomElement` reference is stored in `cl.user_session["doc"]`.

**AC4:** Given the dossier session is active, when `update_dossier_content(new_content)` is called, then `doc.props["content"]` is mutated in place, `doc.props["version"]` is incremented by 1, and `await doc.update()` is called.

**AC5:** Given the user edits the canvas textarea (JSX calls `updateElement`), when the next user message arrives, then `cl.user_session.get("doc").props["content"]` reflects the user's edited content (no polling needed — Chainlit syncs props on `updateElement`).

**AC6:** Given `chainlit` version in `pyproject.toml`, when this story is implemented, then the version constraint is `>=2.4.301` (minimum required for `cl.ElementSidebar`).

---

## Tasks / Subtasks

### Task 1: Add `open_dossier_canvas()` helper to `app/chat.py` (AC: #2, #3)

- [x] Add `async def open_dossier_canvas() -> None:` near the top of `app/chat.py` (after imports, before handlers)
  - Create `cl.CustomElement(name="Document", props={"content": "", "version": 0, "phase": "investigating"}, display="inline")`
  - Call `await cl.ElementSidebar.set_title("Dossier")`
  - Call `await cl.ElementSidebar.set_elements([doc], key="dossier-canvas")`
  - Store: `cl.user_session.set("doc", doc)`

### Task 2: Add `update_dossier_content()` helper to `app/chat.py` (AC: #4)

- [ ] Add `async def update_dossier_content(content: str) -> None:` below `open_dossier_canvas()`
  - `doc = cl.user_session.get("doc")`
  - `doc.props["content"] = content`
  - `doc.props["version"] += 1`
  - `await doc.update()`

### Task 3: Update `@cl.on_chat_start` to initialize dossier state (AC: #1, #2)

- [ ] In `@cl.on_chat_start`, add before existing initialization:
  - `cl.user_session.set("dossier", {"phase": "investigating", "content": "", "version": 0})`
  - `await open_dossier_canvas()`
- [ ] Keep all existing session initialization (`history`, etc.) unchanged

### Task 4: Bump chainlit version constraint (AC: #6)

- [ ] In `pyproject.toml`, update chainlit dependency to `chainlit>=2.4.301`
- [ ] Run `uv lock` to update the lock file

### Task 5: Manual verification (AC: all)

- [ ] Run `chainlit run app/chat.py -w`
- [ ] Confirm the right panel opens immediately with title "Dossier"
- [ ] Confirm Document.jsx renders the investigating placeholder (phase="investigating")
- [ ] Confirm `cl.user_session["dossier"]` is initialized (add a `logger.debug` temporarily to verify)
- [ ] Confirm `cl.user_session["doc"]` is set (log the type)

---

## Dev Notes

### Key API Pattern (from Chainlit cookbook map-canvas)

```python
import chainlit as cl

async def open_dossier_canvas() -> None:
    doc = cl.CustomElement(
        name="Document",
        props={"content": "", "version": 0, "phase": "investigating"},
        display="inline",
    )
    await cl.ElementSidebar.set_title("Dossier")
    await cl.ElementSidebar.set_elements([doc], key="dossier-canvas")
    cl.user_session.set("doc", doc)

async def update_dossier_content(content: str) -> None:
    doc = cl.user_session.get("doc")
    doc.props["content"] = content
    doc.props["version"] += 1
    await doc.update()
```

### Props Sync-Back from JSX

When the user edits the canvas textarea and the JSX calls `updateElement({...props, content: newContent, version: props.version + 1})`, Chainlit automatically updates `doc.props` on the Python side. The next time `_agentic_loop` runs, it should read the latest content with:
```python
doc = cl.user_session.get("doc")
current_content = doc.props.get("content", "")
```

No polling, no extra webhooks. This is the Chainlit-native sync pattern.

### What NOT to Change

- `app/citations.py` — no changes
- `app/prompts.py` — no changes in this story (Story 10.4 handles prompts)
- `mcp_server/` — no changes
- Existing `@cl.on_message` agentic loop logic — no changes to tool dispatch

### pyproject.toml Change

```toml
# Before:
chainlit = ">=2.0.0"

# After:
chainlit = ">=2.4.301"
```

Verify the installed version supports `cl.ElementSidebar` before running.

### Anti-Patterns

- **DON'T** call `await cl.ElementSidebar.set_elements([])` on chat start — this closes the canvas
- **DON'T** recreate the `CustomElement` on every message turn — create once, update props in place
- **DON'T** use `display="side"` or `display="page"` — `display="inline"` is required for ElementSidebar
- **DON'T** store the element by name only — store the object reference: `cl.user_session.set("doc", doc)`, not the `name` string

### References

- [Chainlit cookbook map-canvas `app.py`](https://github.com/Chainlit/cookbook/tree/main/map-canvas) — exact `open_map()` pattern to replicate
- `_bmad-output/planning-artifacts/epics.md#Story 10.2`
- Story 10.1 — Document.jsx must exist for the canvas to render anything

---

## Dev Agent Record

### Agent Model Used

_To be filled on implementation_

### Completion Notes

_To be filled on implementation_

### File List

_To be filled on implementation_
