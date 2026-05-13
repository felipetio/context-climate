# Story 11.1: Investigation Session State

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want a structured investigation checklist tracked in `cl.user_session`,
So that the LLM knows where it is in the 10-item dossier interview and developers can observe progress at DEBUG level.

This is the **state foundation** for Epic 11. Stories 11.2 (`update_investigation_item` LLM tool), 11.3 (phase gate), and 11.4 (`propose_structure`) all build on the session shape, helper, and prompt-injection points established here. Keep the API thin and minimal — do not pre-implement anything from 11.2/11.3/11.4.

---

## Acceptance Criteria

**AC1: Investigation checklist is initialized on chat start.**
**Given** a brand-new chat session
**When** `@cl.on_chat_start` fires (`app/chat.py:469`)
**Then** `cl.user_session.set("investigation", {...})` is called with **exactly** these 10 keys, in this order, each value being `{"done": False, "value": None}`:
```
topic_definition, geography_scope, time_range, target_audience,
data_sources_validation, key_stats_capture, narrative_structure,
case_studies, story_pitches, methodology
```
**And** initialization happens before the welcome `cl.Message(...).send()` so the very first turn already has state.

**AC2: Investigation checklist is also re-seeded on chat resume.**
**Given** a user resumes a previous thread
**When** `@cl.on_chat_resume` fires (`app/chat.py:408`)
**Then** the same `investigation` dict (10 items, all `done: False`, `value: None`) is set in `cl.user_session`.
**Note:** persistence of investigation answers across sessions is **out of scope** — resumed threads start with a fresh checklist (mirrors how `dossier`/`doc` are handled today on resume — see `app/chat.py:425-433`). A future story can add persistence.

**AC3: A pure helper updates a single item.**
**Given** `app/chat.py`
**When** `update_investigation_item(item_id: str, value: Any) -> dict[str, Any]` is called
**Then** if `item_id` is in the 10-item allowlist, it sets `cl.user_session["investigation"][item_id] = {"done": True, "value": value}`, emits `logger.debug("[INVESTIGATION] item=%s status=complete value=%s", item_id, value)`, and returns:
```python
{"status": "ok", "item": item_id, "items_done": <int>, "phase_gate_reached": False}
```
**And** if `item_id` is not in the allowlist, it returns `{"error": "Unknown item_id: '<item_id>'"}` and emits no DEBUG line and mutates no state.
**And** the helper is idempotent — calling it twice with the same `item_id` simply re-sets the entry (no error, no extra increments — `items_done` reflects the count of `done == True` items, not call count).
**Note:** `phase_gate_reached` is wired here as **always `False`** in this story; Story 11.3 will compute the real value. Including the key now keeps the contract stable and prevents Story 11.2's tool wrapper from changing shape later.

**AC4: System prompt includes the investigation snapshot in the investigating phase.**
**Given** `_agentic_loop._build_call_kwargs()` in `app/chat.py:614-636`
**When** `phase == "investigating"`
**Then** the system prompt sent to Anthropic is `INVESTIGATION_SYSTEM_PROMPT + "\n\n" + <snapshot>` where `<snapshot>` is a deterministic, human-readable serialization built by a new helper `_format_investigation_snapshot(state: dict) -> str` (see Dev Notes for the exact format).
**And** when `phase == "dossier"`, the snapshot is **not** appended — the document state already drives prompt construction (Story 10.4 behavior is preserved untouched).
**And** the snapshot is rebuilt every round (inside `_build_call_kwargs`) so any in-loop updates are reflected on the next API call.

**AC5: Unit tests in `tests/app/test_chat.py` cover the new behavior.**
**Given** the new code paths
**When** the test suite runs
**Then** new tests verify:
- AC1: `on_chat_start` sets `investigation` to the 10-item shape (key order, `done: False`, `value: None`).
- AC2: `on_chat_resume` sets `investigation` to the 10-item shape (key order, all reset).
- AC3a: `update_investigation_item("topic_definition", "x")` mutates state and returns `{"status": "ok", "item": "topic_definition", "items_done": 1, "phase_gate_reached": False}`.
- AC3b: Calling the helper twice for the same item still returns `items_done: 1` (idempotent).
- AC3c: Calling for two different items returns `items_done: 2`.
- AC3d: Unknown `item_id` returns `{"error": "Unknown item_id: 'bogus'"}`, does not mutate state, does not log DEBUG.
- AC3e: DEBUG log is emitted with the expected format (`caplog` at `logging.DEBUG`).
- AC4a: In `investigating` phase, the system prompt sent to the API contains the snapshot marker (e.g. `[Investigation state:`).
- AC4b: In `dossier` phase, the snapshot marker is **not** present in the system prompt (regression guard for Story 10.4).
- AC4c: `_format_investigation_snapshot` produces a stable, ordered string matching the format spec in Dev Notes (snapshot or substring assertions).

**AC6: Lint, format, full suite pass.**
- [x] `uv run ruff check .` clean
- [x] `uv run ruff format --check .` clean
- [x] `uv run pytest -q` — all tests pass (existing 348 + new tests).

---

## Tasks / Subtasks

### Task 1: Add the 10-item investigation initializer (AC: #1, #2)

- [x] In `app/chat.py`, add module-level constant near the dossier helpers (around line 84, beside `_DOSSIER_COMMANDS`):
  ```python
  _INVESTIGATION_ITEMS: tuple[str, ...] = (
      "topic_definition",
      "geography_scope",
      "time_range",
      "target_audience",
      "data_sources_validation",
      "key_stats_capture",
      "narrative_structure",
      "case_studies",
      "story_pitches",
      "methodology",
  )

  def _empty_investigation_state() -> dict[str, dict[str, Any]]:
      return {item: {"done": False, "value": None} for item in _INVESTIGATION_ITEMS}
  ```
- [x] In `on_chat_start` (`app/chat.py:469`), add **before** the welcome message send:
  ```python
  cl.user_session.set("investigation", _empty_investigation_state())
  ```
  Place this immediately after the existing `cl.user_session.set("dossier", ...)` line (`app/chat.py:471`).
- [x] In `on_chat_resume` (`app/chat.py:408`), add the same call adjacent to the existing dossier seed (`app/chat.py:429`):
  ```python
  cl.user_session.set("investigation", _empty_investigation_state())
  ```
- [x] Use `tuple[str, ...]` and `dict[str, dict[str, Any]]` — Python 3.12+ syntax per `project-context.md`.

### Task 2: Implement `update_investigation_item` pure helper (AC: #3)

- [x] Add the function in `app/chat.py` immediately below `_empty_investigation_state()` (keeps all investigation-related code in one block):
  ```python
  def update_investigation_item(item_id: str, value: Any) -> dict[str, Any]:
      """Mark an investigation checklist item as complete and return status.

      Pure-ish helper: reads/writes `cl.user_session["investigation"]`. Returns
      a dict that mirrors the LLM-facing tool contract used by Story 11.2 so
      the wrapper stays trivial.

      `phase_gate_reached` is hard-coded False here — Story 11.3 will replace
      the placeholder with real gate logic.
      """
      if item_id not in _INVESTIGATION_ITEMS:
          return {"error": f"Unknown item_id: '{item_id}'"}

      state = cl.user_session.get("investigation")
      if not isinstance(state, dict):
          state = _empty_investigation_state()
          cl.user_session.set("investigation", state)

      state[item_id] = {"done": True, "value": value}
      logger.debug("[INVESTIGATION] item=%s status=complete value=%s", item_id, value)

      items_done = sum(1 for v in state.values() if isinstance(v, dict) and v.get("done"))
      return {
          "status": "ok",
          "item": item_id,
          "items_done": items_done,
          "phase_gate_reached": False,
      }
  ```
- [x] **Do NOT** register this as an MCP/Anthropic tool in this story. Wrapping it as an `apply_ops`-style tool definition is Story 11.2's job. Keep it a plain async-safe Python function.
- [x] **Do NOT** add a `phase_gate_reached: True` branch — that is Story 11.3.

### Task 3: Inject investigation snapshot into the investigation-phase system prompt (AC: #4)

- [x] Add a snapshot helper in `app/chat.py` immediately above `update_investigation_item`:
  ```python
  def _format_investigation_snapshot(state: dict[str, dict[str, Any]]) -> str:
      """Produce a deterministic, ordered snapshot of the investigation checklist
      for inclusion in the system prompt. Order follows `_INVESTIGATION_ITEMS`.
      """
      lines = ["[Investigation state:"]
      for item in _INVESTIGATION_ITEMS:
          entry = state.get(item) if isinstance(state, dict) else None
          done = bool(entry.get("done")) if isinstance(entry, dict) else False
          marker = "x" if done else " "
          if done and isinstance(entry, dict) and entry.get("value") is not None:
              # Truncate noisy values; keep the snapshot bounded.
              value_repr = str(entry.get("value"))
              if len(value_repr) > 120:
                  value_repr = value_repr[:117] + "..."
              lines.append(f"  [{marker}] {item}: {value_repr}")
          else:
              lines.append(f"  [{marker}] {item}")
      lines.append("]")
      return "\n".join(lines)
  ```
- [x] In `_build_call_kwargs()` (`app/chat.py:614`), update the investigating branch so the snapshot is appended:
  ```python
  if phase == "dossier":
      # ...existing dossier branch unchanged...
  else:
      investigation_state = cl.user_session.get("investigation")
      if isinstance(investigation_state, dict):
          snapshot = _format_investigation_snapshot(investigation_state)
          system_prompt = INVESTIGATION_SYSTEM_PROMPT + "\n\n" + snapshot
      else:
          system_prompt = INVESTIGATION_SYSTEM_PROMPT
  ```
- [x] **Do NOT** modify the `dossier` branch. AC4 is explicit: dossier-phase prompts are unchanged. Story 10.4's `[Current document (vN): ...]` framing is the canonical signal in that phase.
- [x] Build the snapshot **inside** `_build_call_kwargs()` (which runs each round) — never cache it across rounds. Story 11.2 will call `update_investigation_item` mid-loop and the next round must see the update.

### Task 4: Tests in `tests/app/test_chat.py` (AC: #5)

- [x] Add a new test class `TestInvestigationSessionState` near `TestReopenDossierCanvas` (`tests/app/test_chat.py:1753`). Reuse the existing `mock_chainlit`-style monkeypatch pattern from `TestReopenDossierCanvas` so a real Chainlit runtime is not required.
- [x] Tests:
  - `test_on_chat_start_initializes_investigation_state` — patches `app.chat` module, calls `on_chat_start`, asserts `session["investigation"]` is the 10-item dict with correct keys, order, and shape.
  - `test_on_chat_resume_initializes_investigation_state` — same as above for `on_chat_resume`.
  - `test_update_investigation_item_marks_done_and_returns_ok` — calls helper, checks return contract and state mutation.
  - `test_update_investigation_item_is_idempotent` — calls twice with same item, asserts `items_done == 1`.
  - `test_update_investigation_item_counts_done_items` — calls for two items, asserts `items_done == 2` after the second call.
  - `test_update_investigation_item_unknown_id_returns_error` — asserts error dict, no state mutation, no DEBUG log.
  - `test_update_investigation_item_logs_debug` — uses `caplog.at_level(logging.DEBUG)` and asserts the formatted log line.
  - `test_format_investigation_snapshot_includes_all_ten_items_in_order` — pass a state with 2 items done; assert the rendered string starts with `[Investigation state:`, lists items in declared order, marks `[x]` for done items with their value, and `[ ]` for not-done.
- [x] Add a new test class `TestAgenticLoopInvestigationSnapshot` mirroring the `_build_call_kwargs` patterns from `TestDossierPromptIntegration`/`TestAgenticLoopIntegration`:
  - `test_investigation_phase_appends_snapshot_to_system_prompt` — set phase=`investigating`, populate `investigation` state, call `_build_call_kwargs()` (or the loop in a way that exercises it), assert the resulting `system` string contains both `INVESTIGATION_SYSTEM_PROMPT` and `[Investigation state:`.
  - `test_dossier_phase_does_not_append_investigation_snapshot` — set phase=`dossier`, assert resulting `system` does **not** contain `[Investigation state:` (regression guard for Story 10.4).
- [x] Follow the project conventions: tests in classes, docstrings reference AC numbers (e.g. `"""AC3: ..."""`), `dict[str, Any]` typing, `X | None`. `asyncio_mode = "auto"` is global — `@pytest.mark.asyncio` is redundant.

### Task 5: Lint, format, full test suite (AC: #6)

- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pytest -q`

---

## Dev Notes

### What this story is (and is not)

**Is:** the **state foundation** for Epic 11 — session shape, mutation helper, snapshot in the prompt.
**Is not:** the LLM-facing tool (Story 11.2 wraps the helper as an Anthropic tool with `input_schema`); the phase gate (Story 11.3 replaces the `phase_gate_reached: False` placeholder); the `propose_structure` skeleton generator (Story 11.4).

### Why expose `phase_gate_reached: False` now

The contract is published in this story so Story 11.2's tool wrapper is a one-line `return update_investigation_item(...)`. Story 11.3 will swap the boolean for a real computation without touching 11.2. Avoids a churny rename cycle across three stories.

### Why a separate `_format_investigation_snapshot` helper

Keeps `_build_call_kwargs()` readable (it's already 22 lines and handles two phases), and gives Task 4 a tight unit-test target without simulating the agentic loop. The exact format is internal — the LLM prompt is what users observe — but lock it down with snapshot-style assertions so Stories 11.2/11.3 don't drift it accidentally.

### Snapshot format (canonical example)

```
[Investigation state:
  [x] topic_definition: Climate adaptation in Northeast Brazil
  [ ] geography_scope
  [ ] time_range
  [ ] target_audience
  [ ] data_sources_validation
  [ ] key_stats_capture
  [ ] narrative_structure
  [ ] case_studies
  [ ] story_pitches
  [ ] methodology
]
```

- Always opens with `[Investigation state:` and closes with `]`.
- Items always rendered in `_INVESTIGATION_ITEMS` order — even unset ones — so the LLM sees what's still pending.
- Long values truncated at 120 chars to keep the prompt bounded (related to deferred-work item "Unbounded dossier content in system prompt — no token cap" — same reasoning, applied prophylactically here).

### Why no DATA RULES in `INVESTIGATION_SYSTEM_PROMPT` change

Per `_bmad-output/implementation-artifacts/deferred-work.md` (`[10-4] INVESTIGATION_SYSTEM_PROMPT has no DATA RULES`), the deliberate choice is that investigation is interview-only. **Do not** add data/citation rules to `INVESTIGATION_SYSTEM_PROMPT` in this story — the snapshot append is the only prompt change.

### Cross-story context (Epic 10 — already shipped)

- **Story 10.2** introduced `cl.user_session["doc"]` and `open_dossier_canvas()` (`app/chat.py:59-72`). Mirror that init pattern (set state in `on_chat_start` and `on_chat_resume`, do not lazy-init).
- **Story 10.3** added `apply_ops`/`update_dossier_content` (`app/chat.py:106-261`) — these mutate `doc.props` and the `dossier` session dict atomically. Investigation state is independent: `update_investigation_item` writes only to `cl.user_session["investigation"]`. Do not touch `doc` or `dossier`.
- **Story 10.4** added phase-aware system prompts and `_build_call_kwargs()` (`app/chat.py:614-636`). The investigating-phase branch is the **only** prompt-construction site that needs editing. The dossier branch must remain byte-for-byte identical (Task 3 enforces this; AC4b is the regression test).
- **Story 10.5** added `reopen_dossier_canvas()` and the `/dossier` slash command (`app/chat.py:75-104`). Do not interfere with this surface — `reopen_dossier_canvas()` does not need to touch `investigation` state.

### Resume parity

`on_chat_resume` (`app/chat.py:425-429`) currently re-seeds `dossier` with empty state but does NOT restore content from the persisted thread. Investigation state follows the **same** convention: re-seed empty, do not restore. Persisting investigation answers across sessions requires DB plumbing and is explicitly out of scope (mirrors the deferred-work item "Reopen shows empty doc on resumed session").

### Key value type — why `Any`

Some checklist items will hold strings (`topic_definition: "Climate adaptation in NE Brazil"`); others may hold structured payloads in 11.2/11.4 (e.g. `data_sources_validation: {"indicator": "EN.ATM.CO2E.PC", "found": True}`). Typing the value as `Any` keeps 11.1 minimal; Story 11.2 may tighten the schema in the tool's `input_schema` if needed.

---

## Latest Tech Information

### chainlit 2.10 — `cl.user_session` shape (verified surface)

| Symbol | Where | Notes |
|---|---|---|
| `cl.user_session.set(key, value)` | `chainlit/user_session.py` | Per-session dict; survives across `on_chat_start` → `on_message` → `on_chat_end` within a session. |
| `cl.user_session.get(key, default=None)` | same | Returns `None` if unset; fall back manually with `if not isinstance(...)`. |
| Session does NOT persist across processes | — | Confirmed by Story 10.5: `on_chat_resume` always re-seeds `doc`/`dossier`. Investigation state follows the same pattern. |

### Anthropic SDK — system prompt as a single string

`anthropic.AsyncAnthropic` `messages.stream(system=str, ...)` accepts a plain string for `system`. There is no need for prompt caching boundaries in this story — the snapshot is small (≤ ~1 KB even with all items populated). If the snapshot ever grows unbounded, revisit alongside the deferred-work `[10-4]` token-cap item.

### Python 3.12+ syntax checklist

- `tuple[str, ...]`, `dict[str, dict[str, Any]]`, `dict[str, Any]` — never `Tuple` / `Dict`.
- `int | None`, `str | None` — never `Optional[int]`.
- Double quotes; line length 120; ruff E/F/W/I.

---

## Previous Story Intelligence

### From Story 10.4 (`10-4-dossier-system-prompt.md`)

- The `_build_call_kwargs()` closure runs **every round** of the agentic loop — design choice for `apply_ops` to reflect doc mutations in the next prompt. The investigation snapshot exploits the same property (any mid-loop `update_investigation_item` is visible on the next call).
- `INVESTIGATION_SYSTEM_PROMPT` already covers interview rules and the 10-item checklist text. This story does **not** edit the constant; the snapshot is appended at runtime. Tests should not be brittle against constant edits.
- Test pattern for `_build_call_kwargs`: mock `cl.user_session.get` to return phase + dossier dict + (now) investigation dict; call `_build_call_kwargs()`; assert on the returned `system` string.

### From Story 10.5 (`10-5-dossier-canvas-reopen-affordance.md`)

- Test mocking pattern (the gold standard for this codebase):
  ```python
  @pytest.fixture
  def mock_chainlit(monkeypatch):
      session = {}
      monkeypatch.setattr(cl, "user_session", types.SimpleNamespace(
          get=lambda k, default=None: session.get(k, default),
          set=lambda k, v: session.update({k: v}),
      ))
      ...
  ```
  Reuse this for `TestInvestigationSessionState` so the new tests look native.
- `cl.context` is a lazy proxy and **cannot** be patched at module import time — limits Task 4's ability to instantiate a real chainlit context. Don't try; mock the session directly.
- Welcome message currently sends `actions=[cl.Action(name="show_dossier", ...)]`. **Do not** add new welcome actions in this story.

### From Story 10.3 (`10-3-apply-ops-patch-engine.md`)

- Pure-function design (the apply-op transform is a pure string transform, with side effects in a thin async wrapper) makes unit-testing trivial. `update_investigation_item` follows the same pattern: pure logic, the only side effects are `cl.user_session` mutation + a `logger.debug` call — both trivially mockable.

---

## Git Intelligence Summary

Recent commits relevant to this story:

- `78ff32c` `fix(10-3): reject append/prepend ops with empty content (#58)` — most recent on `main`; confirms `apply_ops` shape we must not perturb.
- `7094f0b` `feat(10-5): dossier canvas reopen affordance (#57)` — current `app/chat.py:75-104` shape (reopen helper, slash command, action callback, command registration in both `on_chat_start` and `on_chat_resume`).
- `e32b869` `feat(10-4): phase-aware system prompts for dossier canvas (#55)` — confirms `_build_call_kwargs()` location and structure (`app/chat.py:614-636`); this story extends only its `else` (investigating) branch.
- `ce08a69` `feat(10-3): apply_ops patch engine for dossier canvas (#54)` — `_handle_apply_ops` reads `cl.user_session.get("doc")` and updates `dossier` session dict (`app/chat.py:253-256`). Investigation state is a parallel session key — never co-mutated.
- `9a66bdd` `feat(10-2): ElementSidebar canvas integration (#52)` — established the `dossier` session key pattern; `investigation` follows the same pattern (initialized in `on_chat_start` and `on_chat_resume`, not lazy).

**Branch:** create `story/11-1-investigation-session-state` from `main`.
**Commit format:** `feat(11-1): description` (per project workflow rules).

---

## Project Context Reference

This story must follow the rules in `_bmad-output/project-context.md`. Highlights for this story:

- **Python 3.12+ union syntax** — `dict[str, Any]`, `tuple[str, ...]`, `X | None`. **Never** `Optional`/`Tuple`/`Dict`.
- **Async I/O** — `update_investigation_item` is **synchronous** (it only touches `cl.user_session` and `logger`); don't gratuitously make it `async`. The helpers in `_format_investigation_snapshot` and `_empty_investigation_state` are plain functions too.
- **Type hints required** on every new function signature.
- **System prompt text lives in `app/prompts.py`** — `INVESTIGATION_SYSTEM_PROMPT` is the canonical text. The runtime snapshot append happens in `app/chat.py` (`_build_call_kwargs`), which is correct: it's *runtime composition*, not new prompt text.
- **Citation pipeline untouched** — investigation state has no relationship to `app/citations.py` or the Data Sources block. Do not import from `app/citations.py`.
- **No hardcoded values** — but the 10 item names ARE the spec (per `epics.md:1542-1547`). Encoding them as a module-level tuple is correct, not "hardcoding".
- **Pre-commit ruff hooks** enforce E/F/W/I, double quotes, line length 120. Run `uv run ruff check .` and `uv run ruff format .` before commit.
- **`logger.debug(...)`** is correct — DEBUG level is the contract per AC3 and `epics.md:1552`. **Do not** use `logger.info` (it would pollute production logs).

---

## File Structure Requirements

| Path | Change | Reason |
|---|---|---|
| `app/chat.py` | UPDATE | Add `_INVESTIGATION_ITEMS`, `_empty_investigation_state`, `_format_investigation_snapshot`, `update_investigation_item`. Initialize `investigation` in `on_chat_start` and `on_chat_resume`. Extend `_build_call_kwargs()` investigating branch with snapshot append. |
| `tests/app/test_chat.py` | UPDATE | Add `TestInvestigationSessionState` and `TestAgenticLoopInvestigationSnapshot` classes (~10 new tests). |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | UPDATE (workflow) | Status transitions managed by create-story / dev-story workflows. |

Files this story must **not** touch:

- `app/prompts.py` — no edits to `INVESTIGATION_SYSTEM_PROMPT` or `DOSSIER_SYSTEM_PROMPT` text. Snapshot is composed at runtime in `chat.py`.
- `app/citations.py` — citation pipeline unchanged.
- `app/data.py`, `app/db.py` — no persistence changes (resume re-seeds empty; persistence is a future story).
- `mcp_server/**` — server-side untouched.
- `_bmad-output/implementation-artifacts/deferred-work.md` — no items closed by this story.

---

## Testing Requirements

- Tests in `tests/app/test_chat.py`. Follow conventions from `project-context.md` and the existing `TestReopenDossierCanvas` block:
  - Group tests in classes with docstrings referencing AC numbers (`"""AC3: ..."""`).
  - `asyncio_mode = "auto"` is global — `@pytest.mark.asyncio` is redundant but acceptable.
  - Mock `cl.user_session` via `monkeypatch.setattr(cl, "user_session", SimpleNamespace(get=..., set=...))`.
  - Use `caplog.at_level(logging.DEBUG)` for the DEBUG-log assertion (Python 3.12 `caplog` supports DEBUG cleanly).
- Snapshot string assertions: prefer substring/`startswith`/`endswith` checks over exact-string equality so cosmetic format tweaks don't break tests. **Do** assert the canonical opener `[Investigation state:` so the LLM-visible contract is locked.
- Regression guard: an explicit test asserting that the `dossier`-phase prompt does **NOT** include the snapshot marker (AC4b). This protects Story 10.4's contract.
- Total test count: ~10 new tests. Existing 348 must continue passing.

---

## Anti-Patterns (do NOT do)

- **DON'T** register `update_investigation_item` as an Anthropic tool in this story — that's Story 11.2.
- **DON'T** implement the phase gate transition here — Story 11.3 owns the `dossier` phase flip and `phase_gate_reached: True` logic.
- **DON'T** generate document content in this story — Story 11.4 owns `propose_structure`.
- **DON'T** edit `INVESTIGATION_SYSTEM_PROMPT` text in `app/prompts.py` — the snapshot is appended at runtime in `_build_call_kwargs`.
- **DON'T** modify the dossier-phase branch of `_build_call_kwargs()` — AC4 explicitly requires the snapshot **only** in the investigating phase. AC4b is the regression test.
- **DON'T** re-seed `investigation` lazily inside `_build_call_kwargs()` if state is missing — set it explicitly in `on_chat_start` / `on_chat_resume`. Lazy init creates a divergent code path and breaks AC1/AC2.
- **DON'T** persist investigation state to the DB — out of scope. Resume re-seeds empty (AC2).
- **DON'T** make `update_investigation_item` `async` — no awaits inside; would force gratuitous awaits across the future tool wrapper.
- **DON'T** use `logger.info(...)` for the investigation log line — AC3 mandates DEBUG. Production log volume matters.
- **DON'T** leak `[Investigation state:` text into the dossier prompt path — Story 10.4's `[Current document (vN): ...]` framing is the canonical signal in dossier phase.
- **DON'T** truncate `value` more aggressively than 120 chars per item — too short loses signal for the LLM. Too long is what the deferred-work item warns about; 120 is the conservative middle.

---

## References

- `_bmad-output/planning-artifacts/epics.md` → "Story 11.1: Investigation Session State" (lines 1532–1556).
- `_bmad-output/project-context.md` → Critical Implementation Rules (Python 3.12+, async, type hints, no hardcoded values, ruff).
- `_bmad-output/implementation-artifacts/deferred-work.md` → `[10-4] INVESTIGATION_SYSTEM_PROMPT has no DATA RULES` (justifies leaving prompt text untouched); `[10-4] Unbounded dossier content` (motivates 120-char value cap in snapshot).
- `app/chat.py:59-104` → existing dossier helpers — pattern to mirror.
- `app/chat.py:408-466` → `on_chat_resume` (insertion point #1 for investigation seed).
- `app/chat.py:469-522` → `on_chat_start` (insertion point #2 for investigation seed).
- `app/chat.py:614-636` → `_build_call_kwargs()` — only call site that needs editing for AC4.
- `app/prompts.py:115-135` → `INVESTIGATION_SYSTEM_PROMPT` (read-only reference; do not edit).
- `tests/app/test_chat.py:1753-1894` → `TestReopenDossierCanvas` / `TestOpenDossierCanvasIdempotency` / `TestShowDossierAction` — mocking patterns to reuse.

---

## Dev Agent Record

### Agent Model Used

claude-opus-4-7

### Debug Log References

- None — implementation matched the story spec; tests passed on first run.

### Completion Notes List

- All 6 ACs satisfied. Implementation followed the story spec exactly:
  - `_INVESTIGATION_ITEMS` (10 items, declared order) + `_empty_investigation_state()` factory + `_format_investigation_snapshot()` helper + `update_investigation_item()` mutation helper added to `app/chat.py` between the dossier helpers and `_DOSSIER_COMMANDS`.
  - `cl.user_session.set("investigation", _empty_investigation_state())` added to both `on_chat_start` (immediately after the existing `dossier` seed) and `on_chat_resume` (immediately after the existing `dossier` re-seed).
  - `_build_call_kwargs()` extended only in the `investigating` branch; dossier branch byte-identical (AC4b regression test enforces this).
  - `update_investigation_item` returns the published contract `{"status": "ok", "item": ..., "items_done": <int>, "phase_gate_reached": False}` so Story 11.2's tool wrapper stays trivial. `phase_gate_reached` is hard-coded `False` per Dev Notes — Story 11.3 will compute the real value.
- 11 new tests added across `TestInvestigationSessionState` (9) and `TestAgenticLoopInvestigationSnapshot` (2). One bonus test (`test_format_investigation_snapshot_truncates_long_values`) covers the 120-char truncation Dev-Note guard since it's a behavioural contract worth locking.
- `_make_session_mock_with_history` extended with an `investigation` parameter so the new agentic-loop tests stay native to the existing helper pattern (no fixture sprawl).
- Lint clean (`uv run ruff check .` — All checks passed!). Format clean (`uv run ruff format --check .` — 39 files already formatted).
- Full suite: **363 passed**, 0 failed (baseline at story creation: 348; +11 from this story; +4 from `fix(10-3)` PR #58 merged after the story was drafted).
- No edits to `app/prompts.py`, `app/citations.py`, `mcp_server/**`, or `deferred-work.md` (matches the "must not touch" list).

### File List

- `app/chat.py` — added `_INVESTIGATION_ITEMS`, `_empty_investigation_state()`, `_format_investigation_snapshot()`, `update_investigation_item()`; seeded `investigation` session key in both `on_chat_start` and `on_chat_resume`; extended the `investigating` branch of `_build_call_kwargs()` to append the snapshot.
- `tests/app/test_chat.py` — extended `_make_session_mock_with_history` with an `investigation` kwarg; added `_INVESTIGATION_KEYS` test constant; added two new test classes (`TestInvestigationSessionState`, `TestAgenticLoopInvestigationSnapshot`) totalling 11 new tests.
- `_bmad-output/implementation-artifacts/11-1-investigation-session-state.md` — task checkboxes, status, dev agent record (this file).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status transitions backlog → ready-for-dev → in-progress → review.

### Change Log

| Date       | Change                                                                                  |
|------------|-----------------------------------------------------------------------------------------|
| 2026-05-13 | Story created via `bmad-create-story`. Status: ready-for-dev.                            |
| 2026-05-13 | Implementation complete: investigation state initializer, `update_investigation_item` helper, snapshot injection into investigating-phase system prompt. 11 new tests, full suite green. Status: review. |
