# Story 11.3: Phase Gate Logic

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want the app to transition to dossier mode and offer to reveal the dossier when the investigation prerequisites are met,
So that the dossier surfaces at the right moment via an explicit, non-intrusive affordance.

> **Rewritten 2026-05-23 (display replan, see `sprint-change-proposal-2026-05-23.md`).** Depends on **Story 10.6** (reveal mechanism). The phase transition is automatic; the canvas reveal is an explicit one-click affordance, not an auto-open.

---

## Acceptance Criteria

**AC1: No phase transition when fewer than 5 gate items are done.**
**Given** an investigation session where 0–4 of the five gate items
(`topic_definition`, `geography_scope`, `time_range`, `target_audience`,
`data_sources_validation`) are marked done
**When** `update_investigation_item` is called for any item
**Then** `update_investigation_item` returns `phase_gate_reached: False`
**And** `cl.user_session["dossier"]["phase"]` remains `"investigating"`
**And** no reveal affordance is posted to chat

**AC2: Phase transition fires when all five gate items become done.**
**Given** items 1–4 (`topic_definition`, `geography_scope`, `time_range`,
`target_audience`) are already done
**When** `update_investigation_item("data_sources_validation", value)` is called
**Then** `update_investigation_item` returns `phase_gate_reached: True`
**And** `cl.user_session["dossier"]["phase"]` is set to `"dossier"` (was `"investigating"`)
**And** `logger.debug("[INVESTIGATION] phase_gate=reached, transitioning to dossier mode")`
is emitted
**And** the `propose_structure` tool becomes available to the LLM on the next turn
(because `_build_call_kwargs()` reads the now-`"dossier"` phase and appends `APPLY_OPS_TOOL`;
`propose_structure` itself is registered in Story 11.4 — this AC requires only that the phase
flip drives the tool-list rebuild)

**AC3: Dispatch posts the reveal affordance on the first phase transition.**
**Given** the agentic loop receives a `tool_use` block for `update_investigation_item`
that completes the fifth gate item
**When** the dispatch processes the result
**Then** `post_dossier_reveal_affordance()` is called exactly once
**And** the canvas is NOT auto-opened (no `reveal_dossier_canvas()` call)
**And** the `tool_result` sent back to the LLM contains the JSON-serialised dict with
`phase_gate_reached: True`

**AC4: Affordance is NOT re-posted for post-transition calls.**
**Given** the phase is already `"dossier"` (gate was reached in a prior call)
**When** `update_investigation_item` is called again with any gate-item update
**Then** `post_dossier_reveal_affordance()` is NOT called again
**And** `phase_gate_reached: True` is returned (gate state is still met)
**And** the duplicate-post anti-pattern is avoided (the dispatch checks pre-call phase)

**AC5: `update_investigation_item` remains synchronous.**
**Given** the dispatch in `_agentic_loop` (`app/chat.py`)
**When** it calls `update_investigation_item(item_id, value)`
**Then** the call is **not** awaited — the function stays sync
**And** `post_dossier_reveal_affordance()` (async) is awaited in the dispatch after the
helper returns, not inside the helper

**AC6: Unit tests in `tests/app/test_chat.py` cover the new behaviour.**
**Given** the new code paths
**When** the test suite runs
**Then** new tests verify:
- AC1: updating fewer than 5 gate items returns `phase_gate_reached: False` and leaves phase
  as `"investigating"`
- AC2: completing the 5th gate item returns `phase_gate_reached: True`, flips phase to
  `"dossier"`, emits the debug log
- AC2 idempotent: gate returns `True` even when called again for a gate item already done
  (all five remain done) — but phase flip is a no-op since phase is already `"dossier"`
- AC3: dispatch calls `post_dossier_reveal_affordance()` when `phase_gate_reached: True`
  and phase was `"investigating"` before the call
- AC4: dispatch does NOT call `post_dossier_reveal_affordance()` when phase was already
  `"dossier"` before the call
- Regression: completing only non-gate items (items 6–10) never triggers the gate

**AC7: Lint, format, full suite pass.**
- [ ] `uv run ruff check .` clean
- [ ] `uv run ruff format --check .` clean
- [ ] `uv run pytest -q` — all tests pass (existing 374 + new tests)

---

## Tasks / Subtasks

### Task 1: Add `_PHASE_GATE_ITEMS` constant and replace hardcoded `False` (AC: 1, 2, 5)

- [x] Immediately after `_INVESTIGATION_ITEMS` (around `app/chat.py:59-70`), add:
  ```python
  _PHASE_GATE_ITEMS: frozenset[str] = frozenset(
      [
          "topic_definition",
          "geography_scope",
          "time_range",
          "target_audience",
          "data_sources_validation",
      ]
  )
  ```
- [x] In `update_investigation_item()` (currently `app/chat.py:101-128`), replace the
  hardcoded `"phase_gate_reached": False` with computed gate logic:
  ```python
  # Compute whether the 5-item investigation phase gate is met.
  gate_reached = all(
      isinstance(state.get(k), dict) and bool(state[k].get("done"))
      for k in _PHASE_GATE_ITEMS
  )
  if gate_reached:
      dossier = cl.user_session.get("dossier")
      if isinstance(dossier, dict) and dossier.get("phase") != "dossier":
          dossier["phase"] = "dossier"
          cl.user_session.set("dossier", dossier)
          logger.debug("[INVESTIGATION] phase_gate=reached, transitioning to dossier mode")

  return {
      "status": "ok",
      "item": item_id,
      "items_done": items_done,
      "phase_gate_reached": gate_reached,
  }
  ```
- [x] **Do NOT** mutate the `phase_gate_reached: False` in any **other** function or
  constant — the only change to `update_investigation_item()` is the replacement of the
  final return dict's hardcoded `False`.
- [x] The debug log `"[INVESTIGATION] phase_gate=reached, ..."` is emitted **only** when the
  phase actually flips (inside the `dossier.get("phase") != "dossier"` guard). It is **not**
  emitted on subsequent calls that find the gate already met.
- [x] `update_investigation_item()` remains **synchronous** — no `async def`, no `await`.
  The phase flip touches only `cl.user_session.set()` which is sync.

### Task 2: Post reveal affordance in `_agentic_loop` dispatch (AC: 3, 4)

- [x] In `_agentic_loop`'s `update_investigation_item` dispatch branch
  (currently `app/chat.py:839-848`), capture the pre-call phase and conditionally post the
  affordance:
  ```python
  elif tool_name == "update_investigation_item":
      try:
          # Capture phase before the helper runs so we detect the investigating→dossier
          # transition and post the reveal affordance exactly once.
          _dossier_pre = cl.user_session.get("dossier") or {}
          _phase_before = _dossier_pre.get("phase", "investigating")

          result = update_investigation_item(
              tool_input.get("item_id", ""),
              tool_input.get("value"),
          )
          tool_output = json.dumps(result)

          # Post the one-click affordance only on the first investigating→dossier
          # transition (not on re-entry when phase is already "dossier").
          if result.get("phase_gate_reached") and _phase_before == "investigating":
              await post_dossier_reveal_affordance()
      except Exception as exc:
          logger.error("update_investigation_item failed: %s", exc)
          tool_output = f"Error calling update_investigation_item: {exc}"
  ```
- [x] **Do NOT** call `reveal_dossier_canvas()` here — the canvas open is the journalist's
  choice via the action button, per Story 10.6 AC4.
- [x] The `post_dossier_reveal_affordance()` call is inside the `try` block so that an
  exception in posting is caught and logged uniformly.
- [x] The ordering of dispatch branches is unchanged: `apply_ops` first, then
  `update_investigation_item`, then MCP fallback. Only the body of the
  `update_investigation_item` branch changes.

### Task 3: Unit tests in `tests/app/test_chat.py` (AC: 6)

- [x] Add a new test class `TestPhaseGateLogic` placed after
  `TestUpdateInvestigationItemTool` (around line 2258, before `_make_fake_ce_factory`).
- [ ] Tests to write:

  **Helper-level tests (pure unit, no agentic loop):**

  - `test_gate_not_reached_when_fewer_than_5_items_done` (AC1):
    Update 4 of the 5 gate items. Assert `phase_gate_reached: False` each time and that
    `dossier["phase"]` stays `"investigating"`.

  - `test_gate_reached_when_all_5_items_done` (AC2):
    Pre-seed investigation state with items 1–4 done. Update item 5
    (`data_sources_validation`). Assert:
    - Return dict has `phase_gate_reached: True`
    - `store["dossier"]["phase"] == "dossier"` (phase flipped)
    - `caplog` contains `"[INVESTIGATION] phase_gate=reached, transitioning to dossier mode"`
    at DEBUG level.

  - `test_gate_debug_log_emitted_only_on_transition` (AC2 — idempotent log):
    Phase already `"dossier"`. Call `update_investigation_item` again for a gate item.
    Assert `phase_gate_reached: True` is still returned but the debug log is NOT emitted a
    second time (only fires on actual transition, not on re-entry).

  - `test_non_gate_items_never_trigger_gate` (regression AC1/AC2):
    Update items 6–10 (`key_stats_capture`, …, `methodology`) with all gate items still
    `done: False`. Assert `phase_gate_reached: False` and phase stays `"investigating"`.

  **Dispatch-level tests (agentic loop integration):**

  - `test_dispatch_posts_affordance_when_gate_reached` (AC3):
    Build a fake stream that returns a `tool_use` block for `update_investigation_item`
    with all 5 gate items pre-seeded as done in the investigation state, completing item 5
    (`data_sources_validation`). Mock `post_dossier_reveal_affordance` with `AsyncMock`.
    Assert it is awaited exactly once after the loop completes.

  - `test_dispatch_does_not_post_affordance_when_phase_already_dossier` (AC4):
    Same setup but set `dossier={"phase": "dossier", ...}` in the session mock.
    Assert `post_dossier_reveal_affordance` is NOT called.

  - `test_dispatch_does_not_post_affordance_for_partial_gate` (AC1/dispatch):
    Update only `topic_definition` (1 item). Assert `post_dossier_reveal_affordance` is
    NOT called.

- [x] Reuse `_make_session_mock_with_history(investigation=..., dossier=...)` for all tests.
  For helper-level tests that need the `cl.user_session.set()` side-effect to actually
  update the store, use the inline `session_mock.set.side_effect = lambda k, v: store.update({k: v})`
  pattern (mirroring `TestInvestigationSessionState` at `tests/app/test_chat.py:1796-1813`).
- [x] For dispatch-level tests, use the standard `FakeStream` / `_make_fake_content_block` /
  `step_mock` pattern (mirror `TestUpdateInvestigationItemTool::test_dispatch_calls_helper_and_serializes_result`
  at `tests/app/test_chat.py:2047-2107`).
- [x] Mock `cl.Step` with `AsyncMock` as in all existing dispatch tests.
- [x] All test methods have docstrings referencing AC numbers (`"""AC2: ..."""`).

### Task 4: Lint, format, full test suite (AC: 7)

- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pytest -q`

---

## Dev Notes

### What this story is (and is not)

**Is:**
- Real gate computation in `update_investigation_item()` replacing the hardcoded `False`
- Phase flip (`"investigating"` → `"dossier"`) when gate is first reached
- One-shot dispatch of `post_dossier_reveal_affordance()` after the first transition
- A small, focused change to `app/chat.py` — only the helper body and the dispatch branch

**Is not:**
- `propose_structure` tool definition (Story 11.4 owns that)
- Any `Document.jsx` or `public/` changes
- Any `app/prompts.py` changes
- Persistence of investigation state across sessions (still out of scope)
- Phase-aware item-id enforcement (the deferred-work item from 11.2 review)

### The five gate items

```python
_PHASE_GATE_ITEMS = frozenset([
    "topic_definition",
    "geography_scope",
    "time_range",
    "target_audience",
    "data_sources_validation",
])
```

These are the first five items in `_INVESTIGATION_ITEMS`. Using a `frozenset` makes
membership tests O(1) and the constant immutable. Items 6–10 (`key_stats_capture`,
`narrative_structure`, `case_studies`, `story_pitches`, `methodology`) are gathered during
the dossier phase and never trigger the gate.

### Why `gate_reached` uses `all(...)` over a count check

A count check (`items_done >= 5`) would fire even if 5 *non-gate* items were done (e.g.,
items 6–10 from a previous session). The `all(k in _PHASE_GATE_ITEMS and state[k].get("done")`
pattern is precise: it checks exactly the 5 required items by name, not by count.

### Why the phase flip happens inside `update_investigation_item()` (sync), not in the dispatch

The `cl.user_session.set()` call is synchronous. Doing it inside the sync helper keeps the
gate logic self-contained and unit-testable without a full agentic-loop harness. The dispatch
only handles the async side effect (`post_dossier_reveal_affordance`).

### Why the dispatch captures `_phase_before` instead of checking post-call phase

After the helper runs, `dossier["phase"]` is already `"dossier"` (if the gate was just
reached). If we read the phase *after* the call, we can't distinguish "just transitioned"
from "was already dossier". Capturing it before the call is the reliable idiom.

### Why the affordance is posted inside the `try` block

If `post_dossier_reveal_affordance()` raises (e.g., Chainlit socket error), the exception
is caught and logged uniformly by the same `except` that handles helper failures. This
matches the error-handling pattern of the `apply_ops` and MCP paths.

### Phase flip idempotency

`update_investigation_item()` mutates `dossier["phase"]` **only** when
`dossier.get("phase") != "dossier"`. If the helper is called after the phase is already
`"dossier"` (e.g., the LLM redundantly calls it for an already-done item), the phase is
unchanged and the debug log is NOT emitted again. `phase_gate_reached` still returns `True`
because all 5 items are still done — the gate state reflects reality, not the transition
direction.

### Dispatch AC4: why `_phase_before == "investigating"` is the right guard

Checking `_phase_before == "investigating"` (not `!= "dossier"`) is intentionally strict:
it only posts the affordance during an `investigating → dossier` transition. Any exotic
phase value that somehow exists before the call would not trigger a post. This is
defensive and keeps the affordance to the canonical single-post scenario.

### No changes to `_make_session_mock_with_history` are needed

The helper already accepts `dossier=` and `investigation=` kwargs (added in Story 11.1/11.2).
For helper-unit tests that need `set()` to actually mutate the store, use the inline
`store = {...}; session_mock.set.side_effect = lambda k, v: store.update({k: v})` pattern
(same as `TestInvestigationSessionState`). Do NOT change the shared helper.

### The existing test `test_dispatch_calls_helper_and_serializes_result` still passes

That test updates only `topic_definition` (1 item) → `phase_gate_reached: False` →
affordance NOT posted. The assertion `{"phase_gate_reached": False}` at line 2102 is still
correct after this story.

The test `test_update_investigation_item_marks_done_and_returns_ok` at line 1796 also
still passes — it asserts `{"phase_gate_reached": False}` for a single-item update, which
remains correct.

### Deferred-work connection

- `[11-1] phase_gate_reached hardcoded False` (`deferred-work.md:1-5`) — resolved by this
  story. The deferred item explicitly says "Owned by Story 11.3."
- `[11-2] No per-phase enforcement of legal item_id values` (`deferred-work.md:13`) —
  still deferred. This story does not add phase-aware `item_id` validation.
- `[11-2] No investigation snapshot in dossier phase` (`deferred-work.md:15`) — still
  deferred. This story does not change snapshot injection logic in `_build_call_kwargs`.

---

## File Structure Requirements

| Path | Change | Reason |
|---|---|---|
| `app/chat.py` | UPDATE | Add `_PHASE_GATE_ITEMS` constant; replace hardcoded `False` in `update_investigation_item()` return; add pre-call phase capture and `post_dossier_reveal_affordance()` call in dispatch. |
| `tests/app/test_chat.py` | UPDATE | Add `TestPhaseGateLogic` class (~7 tests). |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | UPDATE (workflow) | Status transitions managed by dev-story workflow. |

Files this story must **not** touch:
- `app/prompts.py` — no prompt edits.
- `app/citations.py` — citation pipeline unchanged.
- `mcp_server/**` — MCP server untouched.
- `public/elements/Document.jsx` — no JSX changes.
- `_bmad-output/implementation-artifacts/deferred-work.md` — do not add items; the resolved
  `[11-1]` item is automatically closed by the implementation.

---

## Testing Requirements

- Tests in `tests/app/test_chat.py`, class `TestPhaseGateLogic`.
- **Helper-level tests** (no agentic loop, direct function calls):
  - Set up a real `store` dict and wire `session_mock.set.side_effect` and
    `session_mock.get.side_effect` to it (pattern at `test_chat.py:1799-1813`).
  - Include `dossier={"phase": "investigating", "content": "", "version": 0}` in the store
    so the helper can read and mutate the phase.
  - Include `investigation=_empty_investigation_state()` for baseline tests;
    pre-seed the 4 gate items as `{"done": True, "value": "x"}` for gate-trigger tests.
- **Dispatch-level tests** (agentic loop integration):
  - Build a `FakeStream` returning a `tool_use` block for `update_investigation_item`.
  - Pass `_make_session_mock_with_history(investigation=..., dossier=...)` with a store that
    has `set.side_effect` to actually update values (so the dispatch's `_phase_before`
    capture reads a live value).
  - Patch `app.chat.post_dossier_reveal_affordance` with `AsyncMock` to assert call count.
  - Mock `cl.Step` as `AsyncMock` (same pattern as `TestUpdateInvestigationItemTool`).
  - Mock `cl.Message` with `_make_fake_cl_message()` or a `return_value` mock.
- `asyncio_mode = "auto"` is global — `@pytest.mark.asyncio` is redundant.
- Expected new test count: ~7. Existing 374 must continue passing.

---

## Anti-Patterns (do NOT do)

- **DON'T** `await update_investigation_item(...)` — it is and must remain a sync function.
  Awaiting it raises `TypeError: object dict can't be used in 'await' expression`.
- **DON'T** call `reveal_dossier_canvas()` from the dispatch — only `post_dossier_reveal_affordance()`
  (posts the action button). The journalist opens the canvas.
- **DON'T** post the affordance inside `update_investigation_item()` — that function is sync
  and has no access to Chainlit's async message API.
- **DON'T** use a count-based gate (`items_done >= 5`) — it would fire for any 5 items, not
  specifically the gate-required 5.
- **DON'T** emit the debug log every time `gate_reached` is `True` — only on the
  `"investigating"` → `"dossier"` transition (guarded by `dossier.get("phase") != "dossier"`).
- **DON'T** add a `propose_structure` tool definition in this story — that belongs to
  Story 11.4.
- **DON'T** change `_build_call_kwargs()`'s tool-list logic — the phase flip is sufficient:
  once phase is `"dossier"`, `APPLY_OPS_TOOL` is already appended (existing code). Story 11.4
  will append `PROPOSE_STRUCTURE_TOOL` in the same `if phase == "dossier":` block.
- **DON'T** modify `INVESTIGATION_SYSTEM_PROMPT` or `DOSSIER_SYSTEM_PROMPT` text.
- **DON'T** add `propose_structure` to the dossier tool list in `_build_call_kwargs()` —
  Story 11.4 owns that registration.

---

## Previous Story Intelligence

### From Story 11.2 (`11-2-update-investigation-item-tool.md`, done)

- `update_investigation_item()` is **sync** — confirmed. Return contract:
  `{"status": "ok", "item": ..., "items_done": ..., "phase_gate_reached": bool}`.
  This story changes the `phase_gate_reached` field from hardcoded `False` to computed.
- The dispatch branch for `update_investigation_item` is at `app/chat.py:839-848`.
  This story adds pre-call phase capture and a conditional `await post_dossier_reveal_affordance()`
  after `json.dumps(result)` inside the `try` block.
- Deferred review finding: `"phase_gate_reached: False hardcoded permanently"` — Story 11.3
  is the explicit owner; this story resolves it.
- Test helper `_make_session_mock_with_history(investigation=..., dossier=...)` is available
  and accepts both kwargs.

### From Story 10.6 (`10-6-on-demand-dossier-canvas-reveal.md`, done)

- `post_dossier_reveal_affordance()` is defined at `app/chat.py:206-216`. It posts a
  `cl.Message` with a single `cl.Action(name="reveal_dossier", label="📄 Open dossier", payload={})`.
- `ensure_dossier_doc()` and `reveal_dossier_canvas()` are idempotent and available, but
  this story does NOT call them from the dispatch — only `post_dossier_reveal_affordance()`.
- The `on_reveal_dossier` action callback (line 219-224) handles the subsequent canvas open
  when the journalist clicks the button.

### From Story 11.1 (`11-1-investigation-session-state.md`, done)

- `_INVESTIGATION_ITEMS` tuple order (line 59-70): `topic_definition`, `geography_scope`,
  `time_range`, `target_audience`, `data_sources_validation` are positions 0–4 (the gate).
  Items 5–9 are post-gate.
- `_empty_investigation_state()` returns a dict with all 10 items as `{"done": False, "value": None}`.
- `cl.user_session.set("investigation", state)` write-back is already in `update_investigation_item`
  (added in the 11.1 code review fix). This story does not change that line.
- `dossier` session state is initialized in `on_chat_start` and `on_chat_resume` as
  `{"phase": "investigating", "content": "", "version": 0}`.

---

## Latest Tech Information

### `cl.user_session.set()` in sync functions

Chainlit's `cl.user_session.set()` is synchronous (writes to a thread-local dict). It can
be called from a sync function inside an async context without issue. No `asyncio.run` or
`loop.call_soon_threadsafe` is needed — this is standard Chainlit usage.

### `frozenset` for constant membership checks

Python `frozenset` is O(1) for `in` checks (hash-based). Declaring `_PHASE_GATE_ITEMS` as
a module-level `frozenset` avoids rebuilding a set on every `update_investigation_item` call
and makes the constant immutable.

### Test fixture for pre-seeded investigation state

```python
def _make_seeded_investigation(done_items: list[str]) -> dict:
    state = reload_chat._empty_investigation_state()
    for item in done_items:
        state[item] = {"done": True, "value": "test-value"}
    return state
```

Use this pattern inline in test methods to avoid shared fixture state pollution.

---

## Git Intelligence Summary

Recent commits relevant to this story:

- `c8fb46f` `feat(10-6): on-demand dossier canvas reveal (#66)` — direct dependency.
  Provides `ensure_dossier_doc()`, `reveal_dossier_canvas()`, `post_dossier_reveal_affordance()`,
  and the `on_reveal_dossier` action callback. All are at `app/chat.py:153-224`.
- `eef7761` `feat(11-2): update_investigation_item LLM tool (#60)` — direct dependency.
  Adds `UPDATE_INVESTIGATION_ITEM_TOOL` constant and dispatch branch. This story extends
  the dispatch body only.
- `078fe57` `feat(11-1): investigation session state foundation (#59)` — provides
  `_INVESTIGATION_ITEMS`, `update_investigation_item()`, `_empty_investigation_state()`,
  `_format_investigation_snapshot()`.

**Branch:** create `story/11-3-phase-gate-logic` from `main` (all dependencies merged).
**Commit format:** `feat(11-3): description`.

---

## Project Context Reference

This story must follow the rules in `_bmad-output/project-context.md`. Highlights:

- **Python 3.12+ union syntax** — `dict[str, Any]`, `X | None`. **Never** `Optional`.
- **`frozenset[str]`** — correct type annotation for `_PHASE_GATE_ITEMS`.
- **Async I/O** — `update_investigation_item()` is sync. `post_dossier_reveal_affordance()` is async.
  The dispatch (`_agentic_loop`) is async, so `await post_dossier_reveal_affordance()` is valid there.
- **No hardcoded values** — gate item names are derived from `_INVESTIGATION_ITEMS` (already
  module-level constants). No magic strings inside the gate logic.
- **Pre-commit ruff hooks** — E/F/W/I rules, double quotes, line length 120.
- **System prompt text lives in `app/prompts.py`** — this story adds no prompt text.
- **Citation pipeline untouched** — `update_investigation_item` tool outputs do not carry
  `CITATION_SOURCE`, so `extract_references(all_tool_outputs)` naturally ignores them.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was straightforward, no unexpected issues.

### Completion Notes List

- Added `_PHASE_GATE_ITEMS: frozenset[str]` constant after `_INVESTIGATION_ITEMS` at `app/chat.py:72-74`.
- Replaced hardcoded `phase_gate_reached: False` with computed `gate_reached` using `all(...)` over `_PHASE_GATE_ITEMS`. Phase flip (`"investigating"` → `"dossier"`) guarded by `dossier.get("phase") != "dossier"` to ensure idempotency.
- Updated dispatch branch at `app/chat.py:839-853`: captures `_phase_before` as a string before calling the sync helper; posts `post_dossier_reveal_affordance()` exactly once when `phase_gate_reached` and `_phase_before == "investigating"`.
- Cleaned up stale Story 11.1/11.2 forward-reference docstring from `update_investigation_item`.
- 7 new tests in `TestPhaseGateLogic`: 4 helper-level (gate False/True/idempotent/non-gate) + 3 dispatch-level (posts affordance / skips if already dossier / skips if gate not reached).
- All 381 tests pass (374 baseline + 7 new). Ruff clean after auto-format.

### File List

- `app/chat.py` — added `_PHASE_GATE_ITEMS`, replaced hardcoded gate return, updated dispatch branch, cleaned docstring
- `tests/app/test_chat.py` — added `TestPhaseGateLogic` class (7 tests)

### Change Log

| Date       | Change                                                                 |
|------------|------------------------------------------------------------------------|
| 2026-05-25 | Story created via `bmad-create-story`. Status: ready-for-dev.          |
| 2026-05-25 | Implementation complete. Status: review. 381/381 tests pass.           |

---

### Review Findings

- [x] [Review][Patch] `dossier=None` skips phase flip silently but affordance still fires — add defensive `logger.warning` when `dossier` is not a dict [app/chat.py:124-127]
- [x] [Review][Patch] `_all_gate_items_done` test helper hardcodes gate item names as strings — iterate `reload_chat._PHASE_GATE_ITEMS` instead to stay in sync [tests/app/test_chat.py:2261-2264]
- [x] [Review][Patch] `test_gate_reached_when_all_five_items_done` missing `caplog` assertion for debug log emission (AC6 requires it) [tests/app/test_chat.py:2282-2296]
- [x] [Review][Patch] `test_gate_idempotent_when_already_dossier` calls `key_stats_capture` (non-gate item) — AC6 requires re-calling a gate item already marked done [tests/app/test_chat.py:2298-2307]
- [x] [Review][Patch] Dispatch test docstrings cite "AC2" but behaviors map to AC3/AC4 — fix traceability [tests/app/test_chat.py:2309, 2347]
- [x] [Review][Patch] No test asserting `update_investigation_item` is not a coroutine function — add `assert not inspect.iscoroutinefunction(...)` (AC5) [tests/app/test_chat.py]
- [x] [Review][Defer] `on_chat_resume` resets `dossier["phase"]` to `"investigating"` unconditionally — gate can never re-trigger after browser reload [app/chat.py:583] — deferred, pre-existing
- [x] [Review][Defer] `update_investigation_item` error dict omits `phase_gate_reached` key — LLM receives ambiguous response on unknown `item_id` [app/chat.py:108] — deferred, pre-existing from Story 11.2
- [x] [Review][Defer] `test_dispatch_no_affordance_when_already_dossier` does not assert serialized `tool_output` contains `"phase_gate_reached": true` (AC4) — deferred, low value, implicitly verified via mock
