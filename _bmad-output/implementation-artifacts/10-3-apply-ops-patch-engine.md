# Story 10.3: apply_ops Patch Engine

Status: done

## Story

As a developer,
I want the LLM to edit the dossier via surgical anchor-based patch operations,
So that document edits are incremental, verifiable, and never produce full-doc rewrites.

---

## Acceptance Criteria

**AC1:** Given the LLM calls `apply_ops` with a list of ops and a summary string, when processing begins, then ops are applied sequentially to the current document content.

**AC2:** Given each op is applied, when the op succeeds, then `doc.props["content"]` is updated, `doc.props["version"]` is incremented, `await doc.update()` is called, and `asyncio.sleep(0.03)` runs before the next op (streaming effect).

**AC3:** Given a `replace` or `delete` op, when the `find` text is not found in the document, then the tool returns `{"error": "Text not found: '<find>'"}` and no ops are applied from that point forward.

**AC4:** Given a `replace` or `delete` op, when the `find` text appears more than once in the document, then the tool returns `{"error": "Ambiguous match for '<find>' — found N times, be more specific"}` and no ops are applied from that point forward.

**AC5:** Given an `insert_after` or `insert_before` op, when the `anchor` text matches exactly once, then content is inserted immediately after or before that anchor string.

**AC6:** Given an `append` op, when processed, then `content` is appended to the end of the document. No `find` or `anchor` required.

**AC7:** Given a `prepend` op, when processed, then `content` is prepended to the beginning of the document. No `find` or `anchor` required.

**AC8:** Given all ops complete without error, when the tool finishes, then a short `cl.Message(content=summary)` is sent to the chat stream. The full document is never echoed inline.

**AC9:** Given the `apply_ops` tool schema, when registered, then it matches the schema defined in the Dev Notes exactly (name, description, input_schema with ops array and summary).

---

## Tasks / Subtasks

### Task 1: Implement `apply_single_op(content, op)` in `app/chat.py` (AC: #2, #3, #4, #5, #6, #7)

- [x] Add `def apply_single_op(content: str, op: dict) -> tuple[str, str | None]:` (returns `(new_content, error_msg | None)`)
- [x] Implement each op type:
  - `replace`: find exact match (count occurrences); if 0 → error; if >1 → error; else `content.replace(find, op["content"], 1)`
  - `delete`: same match logic as replace; if exact 1 → `content.replace(find, "", 1)`
  - `insert_after`: find anchor, count occurrences; if exact 1 → insert `op["content"]` after first occurrence
  - `insert_before`: same but insert before
  - `append`: `content + "\n\n" + op["content"]`
  - `prepend`: `op["content"] + "\n\n" + content`
- [x] Return `(new_content, None)` on success, `(content, error_msg)` on failure (content unchanged on error)

### Task 2: Implement `_handle_apply_ops(tool_input)` in `app/chat.py` (AC: #1, #2, #8)

- [x] Add `async def _handle_apply_ops(tool_input: dict) -> str:` to handle the full ops list
- [x] Get `doc = cl.user_session.get("doc")` and `current_content = doc.props["content"]`
- [x] Loop over `tool_input["ops"]`:
  - Call `apply_single_op(current_content, op)`
  - On error: return the error string immediately (stop processing remaining ops)
  - On success: update `current_content`, update `doc.props["content"]`, `doc.props["version"] += 1`, `await doc.update()`, `await asyncio.sleep(0.03)`
- [x] On success: `await cl.Message(content=tool_input["summary"]).send()`; return `"ok"`
- [x] Also sync back to `cl.user_session["dossier"]["content"]` after all ops

### Task 3: Register `apply_ops` tool in the dossier tool list (AC: #9)

- [x] Add `APPLY_OPS_TOOL` dict constant in `app/chat.py` (or `app/prompts.py`) with the schema from Dev Notes
- [x] Add it to the tools list used by the agentic loop when phase is `"dossier"` (Story 10.4 handles phase-gating, but register the tool definition here)

### Task 4: Wire `apply_ops` into the agentic loop tool dispatch (AC: #1, #8)

- [x] In `_agentic_loop()`, in the tool dispatch block, add:
  ```python
  if tool_use.name == "apply_ops":
      tool_result = await _handle_apply_ops(tool_use.input)
  ```
- [x] Tool result is returned to the model as a `tool_result` message block (same pattern as existing MCP tools)

### Task 5: Tests (AC: #3, #4, #5, #6, #7)

- [x] Create `tests/app/test_apply_ops.py`
- [x] Test `apply_single_op` for each op type:
  - `replace` success: exact match replaced
  - `replace` not found: returns error tuple
  - `replace` ambiguous: returns error tuple with count
  - `delete` success
  - `insert_after` success
  - `insert_before` success
  - `append` on empty doc
  - `append` on non-empty doc
  - `prepend`
- [x] No mocking of Chainlit session — test `apply_single_op` as a pure function

### Task 6: Run full test suite and linter (AC: all)

- [x] `uv run pytest -v` — zero failures (322 passed)
- [x] `uv run ruff check . && uv run ruff format .` — clean

### Review Findings (2026-05-13)

Adversarial code review with Blind Hunter + Edge Case Hunter + Acceptance Auditor across stories 10-2/10-3/10-4.

- [x] [Review][Patch] **`append`/`prepend` with empty or missing `content` silently no-ops but still increments `doc.props["version"]` and calls `doc.update()`** [app/chat.py:207-212] — **Fixed (2026-05-13):** added empty-content guard returning an error string; 4 new tests in `TestApplySingleOpEmptyContent`. 352/352 pass. — `op.get("content", "")` returns `""` if the LLM omits the key; the function returns `(content.strip(), None)` (success), version is bumped, frontend gets a spurious update. LLM receives `"ok"` with no actual change, misleading the model. Fix: guard `if not new_text: return content, f"Missing required 'content' for {op_type} op"`. _Severity: Med._
- [x] [Review][Defer] **Partial rollback shows intermediate versions to frontend before snap-back** [app/chat.py:239-242] — On a multi-op batch where op N fails, ops 1..N-1 were already streamed to the canvas (with incrementing versions); rollback restores `original_content`/`original_version` correctly, but the frontend transiently saw higher version numbers. Not data corruption, but could confuse the JSX reconciliation if it relies on monotonically increasing versions. Defer: acceptable for now; address if frontend issues arise. _Severity: Med._
- [x] [Review][Defer] **Anchor appearing as substring of its inserted `content` causes ambiguity error in the next op of the same batch** [app/chat.py:203] — `insert_after` replaces `anchor` with `anchor + "\n\n" + new_text`; if `new_text` contains `anchor`, the next op looking for that anchor finds 2 occurrences and returns an ambiguity error. Predictable behaviour (LLM gets actionable error and can retry with a smaller batch), but undocumented. Defer: document in tool description; fix if it proves problematic in practice. _Severity: Low._
- [x] [Review][Defer] **`apply_ops` returns `"Error: dossier canvas is not open"` when canvas failed silently on resume — LLM may retry until `max_tool_rounds`** [app/chat.py:152] — If `open_dossier_canvas()` raised during `on_chat_resume` and was swallowed, `cl.user_session.get("doc")` is `None` for the rest of the session; subsequent `apply_ops` calls return an error the LLM has no system-prompt guidance to recover from. Defer: linked to the known resume-path architectural gap. _Severity: Med._

---

## Dev Notes

### apply_ops Tool Schema (register verbatim)

```python
APPLY_OPS_TOOL = {
    "name": "apply_ops",
    "description": (
        "Apply a sequence of ops to the dossier document. "
        "Each op references exact existing text where applicable. "
        "Use small, surgical ops. Quote anchor text exactly as it appears."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ops": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "enum": [
                                "replace",
                                "insert_after",
                                "insert_before",
                                "delete",
                                "append",
                                "prepend",
                            ]
                        },
                        "find": {
                            "type": "string",
                            "description": (
                                "Exact text to locate. Required for replace, delete."
                            ),
                        },
                        "anchor": {
                            "type": "string",
                            "description": (
                                "Exact text to locate. Required for insert_after, insert_before."
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": (
                                "New text. Required for replace, insert_*, append, prepend."
                            ),
                        },
                    },
                    "required": ["type"],
                },
            },
            "summary": {
                "type": "string",
                "description": "One-line explanation of what changed, shown in chat.",
            },
        },
        "required": ["ops", "summary"],
    },
}
```

### apply_single_op Implementation Notes

The function is a pure string transform. Keep it free of Chainlit session calls so it's testable in isolation.

```python
def apply_single_op(content: str, op: dict) -> tuple[str, str | None]:
    op_type = op["type"]

    if op_type in ("replace", "delete"):
        find = op.get("find", "")
        count = content.count(find)
        if count == 0:
            return content, f"Text not found: '{find}'"
        if count > 1:
            return content, f"Ambiguous match for '{find}' — found {count} times, be more specific"
        if op_type == "replace":
            return content.replace(find, op.get("content", ""), 1), None
        return content.replace(find, "", 1), None

    if op_type in ("insert_after", "insert_before"):
        anchor = op.get("anchor", "")
        count = content.count(anchor)
        if count == 0:
            return content, f"Anchor not found: '{anchor}'"
        if count > 1:
            return content, f"Ambiguous anchor '{anchor}' — found {count} times, be more specific"
        new_text = op.get("content", "")
        if op_type == "insert_after":
            return content.replace(anchor, anchor + "\n\n" + new_text, 1), None
        return content.replace(anchor, new_text + "\n\n" + anchor, 1), None

    if op_type == "append":
        new_text = op.get("content", "")
        return (content + "\n\n" + new_text).strip(), None

    if op_type == "prepend":
        new_text = op.get("content", "")
        return (new_text + "\n\n" + content).strip(), None

    return content, f"Unknown op type: '{op_type}'"
```

### Streaming Feel

The `asyncio.sleep(0.03)` between ops is intentional. It allows the canvas to visibly update section by section rather than all at once. For dossiers with many ops (e.g., initial skeleton fill), this creates a typewriter-like effect.

### Files to Modify

- `app/chat.py` — add `apply_single_op`, `_handle_apply_ops`, `APPLY_OPS_TOOL`, wire dispatch

**Files NOT to touch:**
- `mcp_server/` — no changes
- `app/citations.py` — no changes
- `app/prompts.py` — tool schema lives in `app/chat.py` for now (Story 10.4 may reorganize)

### Anti-Patterns

- **DON'T** apply ops to a local copy and update the session at the end — update `doc.props` after each op so the canvas streams updates
- **DON'T** echo the full document in chat — only `summary` goes to chat
- **DON'T** use line numbers as anchors — the schema uses exact text matching; LLMs drift on line numbers
- **DON'T** swallow op errors silently — return the error to the model so it can retry with better context
- **DON'T** use `Optional[X]` — use `X | None`
- **DON'T** add `# noqa` without approval

### References

- Felipe's original technical prompt (party mode conversation, 2026-05-07) — schema source
- [Chainlit cookbook map-canvas](https://github.com/Chainlit/cookbook/tree/main/map-canvas) — `await doc.update()` pattern
- `_bmad-output/planning-artifacts/epics.md#Story 10.3`
- `app/chat.py` — existing `_agentic_loop()` tool dispatch pattern to replicate

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) via Claude Code (`/bmad-dev-story 10.3`)

### Completion Notes

- Implemented `apply_single_op` as a pure string transform in `app/chat.py` — no Chainlit session access — so it can be unit-tested in isolation.
- Implemented `_handle_apply_ops` to drive the ops list, update `doc.props["content"]`/`version` after each op, `await doc.update()`, and `await asyncio.sleep(0.03)` between ops for the streaming feel (AC2). The full document is never echoed inline; only `summary` is sent via `cl.Message` after all ops succeed (AC8).
- On op failure, returns the error string immediately and stops applying further ops (AC3, AC4) — the error flows back to the LLM as the `tool_result` so it can retry with better anchors.
- Registered `APPLY_OPS_TOOL` constant matching the Dev Notes schema verbatim (AC9) and combined it with MCP tools inside `_agentic_loop`; `apply_ops` is now always available regardless of MCP connectivity (phase gating is deferred to Story 10.4).
- Updated two `test_chat.py` assertions that previously expected the absence of `tools` when no MCP tools were available — now that `apply_ops` is always registered locally, the tests assert its presence instead.
- Added 19 unit tests in `tests/app/test_apply_ops.py` covering each op type, error paths (not found / ambiguous), the unknown-op fallback, and schema shape.

### File List

- `app/chat.py` — added `APPLY_OPS_TOOL`, `apply_single_op`, `_handle_apply_ops`; wired apply_ops dispatch in `_agentic_loop`; always-register tool list
- `tests/app/test_apply_ops.py` — new test file (19 tests)
- `tests/app/test_chat.py` — updated two MCP tool-registration tests to account for always-on `apply_ops`
- `_bmad-output/implementation-artifacts/10-3-apply-ops-patch-engine.md` — task checkboxes, status, Dev Agent Record
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status updated to `review`

### Change Log

- 2026-05-12 — Implemented apply_ops patch engine and registered it as a local tool in the agentic loop; updated test_chat.py to expect the new always-on tool registration.
