# Story 11.2: update_investigation_item Tool

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want the LLM to call `update_investigation_item` as an Anthropic tool to record investigation answers,
So that state transitions are explicit, logged, and visible in the agentic-loop trace — and Story 11.3 can hook the phase gate onto the same call site.

This story is a **thin wrapper**: it exposes the existing `update_investigation_item(item_id, value)` Python helper (Story 11.1, `app/chat.py`) as an Anthropic tool, registers it in both phases, dispatches it inside `_agentic_loop`'s tool-call switch, and JSON-serializes the helper's return dict back to the model. No state-machine logic is added here.

---

## Acceptance Criteria

**AC1: `UPDATE_INVESTIGATION_ITEM_TOOL` is defined as a module-level Anthropic tool dict.**
**Given** `app/chat.py`
**When** this story is complete
**Then** a constant `UPDATE_INVESTIGATION_ITEM_TOOL: dict[str, Any]` exists, placed alongside `APPLY_OPS_TOOL` (mirroring the same shape: `name`, `description`, `input_schema`).
**And** `name == "update_investigation_item"`.
**And** `input_schema` requires `item_id: str` (enum of the 10 keys from `_INVESTIGATION_ITEMS`) and `value` (any JSON-serializable shape — `string | number | boolean | object | array | null`).
**And** `description` instructs the LLM to call this once per checklist item, after gathering enough context for that item, with a concise `value` summarising the answer.

**AC2: The tool is registered for the LLM in both phases.**
**Given** `_build_call_kwargs()` in `_agentic_loop` (`app/chat.py:681-708`)
**When** the system builds `combined_tools` for an Anthropic API call
**Then** `UPDATE_INVESTIGATION_ITEM_TOOL` is appended to `combined_tools` regardless of `phase` (both `"investigating"` and `"dossier"`).
**And** the existing `APPLY_OPS_TOOL` registration (dossier-only) is preserved untouched.
**Rationale:** items 1–5 are gathered in `investigating`; items 6–10 are gathered in `dossier`. The tool must be available across both phases so the LLM can record post-gate items (key_stats_capture, narrative_structure, case_studies, story_pitches, methodology). See Dev Notes.

**AC3: The tool dispatch path executes the helper and returns serialised output to the model.**
**Given** an `assistant_content` block with `block.type == "tool_use"` and `block.name == "update_investigation_item"` (`app/chat.py:761-799`)
**When** the agentic loop processes the block
**Then** it calls `update_investigation_item(tool_input["item_id"], tool_input.get("value"))` from Story 11.1.
**And** the returned dict is JSON-serialised with `json.dumps(...)` and assigned to `tool_output`, so the Anthropic SDK receives a string `content` (matching how the MCP path returns text via `_extract_tool_result_text`).
**And** the dispatch wraps the call in `try/except`; on exception, `tool_output = f"Error calling update_investigation_item: {exc}"` and `logger.error(...)` is emitted (parity with the `apply_ops` and MCP error paths at `app/chat.py:773-790`).
**And** the dispatch ordering keeps `apply_ops` first, then `update_investigation_item`, then the MCP fallback — adding the new branch as `elif tool_name == "update_investigation_item":` between the existing `apply_ops` branch and the `mcp_session is not None` branch.

**AC4: Unknown `item_id` returns the helper's error contract verbatim.**
**Given** an LLM tool call with `item_id` not in the 10-item allowlist
**When** the dispatch executes
**Then** the helper returns `{"error": "Unknown item_id: '<id>'"}` (Story 11.1 contract) and the dispatch JSON-serialises that **without** wrapping it as an exception — the LLM receives a structured error it can recover from.
**And** no DEBUG log is emitted by the helper for unknown IDs (Story 11.1 behaviour, regression-tested there; this story does not duplicate the assertion).

**AC5: The investigation snapshot reflects updates in the very next API round.**
**Given** the LLM calls `update_investigation_item("topic_definition", "Climate adaptation")` in round N
**When** round N+1 begins
**Then** `_build_call_kwargs()` rebuilds the system prompt and the embedded `[Investigation state:` snapshot (Story 11.1) shows `[x] topic_definition: Climate adaptation`.
**Note:** This is a property of Story 11.1's design (snapshot rebuilt every round). The test for this AC verifies the contract holds end-to-end through the dispatch path — no new code needed in 11.2 to satisfy this.

**AC6: Unit tests in `tests/app/test_chat.py` cover the new behaviour.**
**Given** the new code paths
**When** the test suite runs
**Then** new tests verify:
- AC1: `UPDATE_INVESTIGATION_ITEM_TOOL` has `name == "update_investigation_item"`, requires `item_id`, declares the 10-item enum, and accepts `value`.
- AC2a: In `investigating` phase, `combined_tools` includes `update_investigation_item` and **excludes** `apply_ops`.
- AC2b: In `dossier` phase, `combined_tools` includes both `apply_ops` and `update_investigation_item`.
- AC3a: A tool_use block with `name == "update_investigation_item"` triggers the helper and writes the JSON-serialised dict to history as the `tool_result.content`.
- AC3b: The helper's return shape (`{"status": "ok", "item": ..., "items_done": ..., "phase_gate_reached": False}`) survives the JSON round-trip — tests load `tool_output` back via `json.loads` and assert keys/values.
- AC3c: An exception inside the helper (simulate by patching `update_investigation_item` to raise) yields `tool_output.startswith("Error calling update_investigation_item:")` and a `logger.error(...)` call. **No** unhandled exception escapes the agentic loop.
- AC4: An LLM-supplied `item_id == "bogus"` produces `tool_output` that JSON-decodes to `{"error": "Unknown item_id: 'bogus'"}` (no exception path).
- AC5: After dispatching `update_investigation_item("topic_definition", "Climate")` in round 1, the captured `system` prompt for round 2 contains `[x] topic_definition: Climate`. Achievable with a fake stream that returns a `tool_use` block on the first call and a plain text block on the second.

**AC7: Lint, format, full suite pass.**
- [x] `uv run ruff check .` clean
- [x] `uv run ruff format --check .` clean
- [x] `uv run pytest -q` — all tests pass (existing 363 + new tests).

---

## Tasks / Subtasks

### Task 1: Define `UPDATE_INVESTIGATION_ITEM_TOOL` constant (AC: #1)

- [x] In `app/chat.py`, immediately after `APPLY_OPS_TOOL` (`app/chat.py:185-233`), add:
  ```python
  UPDATE_INVESTIGATION_ITEM_TOOL: dict[str, Any] = {
      "name": "update_investigation_item",
      "description": (
          "Record the journalist's answer for one investigation checklist item. "
          "Call this exactly once per item, after you have gathered enough context "
          "to summarise the answer in `value`. Do not call it speculatively. "
          "Items 1-5 (topic_definition, geography_scope, time_range, target_audience, "
          "data_sources_validation) are gathered during the interview phase; items 6-10 "
          "(key_stats_capture, narrative_structure, case_studies, story_pitches, methodology) "
          "are gathered while building the dossier."
      ),
      "input_schema": {
          "type": "object",
          "properties": {
              "item_id": {
                  "type": "string",
                  "enum": list(_INVESTIGATION_ITEMS),
                  "description": "The checklist item being recorded.",
              },
              "value": {
                  "description": (
                      "The journalist's answer for this item. "
                      "Use a concise string for free-text items (topic_definition, geography_scope, etc.) "
                      "or a structured object for items that summarise multiple data points "
                      "(e.g. key_stats_capture, data_sources_validation)."
                  ),
              },
          },
          "required": ["item_id", "value"],
      },
  }
  ```
- [x] **Do NOT** redefine `_INVESTIGATION_ITEMS` — reuse the constant from Story 11.1 (`app/chat.py`).
- [x] **Do NOT** add `value` JSON-type constraints (no `"type": "..."` on the `value` property) — Anthropic's tool schema accepts open-typed fields, and forcing a type would either reject structured payloads (items 6-10) or reject simple strings (items 1-5). The unconstrained schema is intentional.

### Task 2: Register the tool in both phases (AC: #2)

- [x] In `_build_call_kwargs()` (`app/chat.py:681-708`), after `combined_tools = list(tools)` and **before** the `if phase == "dossier":` line, add:
  ```python
  combined_tools.append(UPDATE_INVESTIGATION_ITEM_TOOL)
  ```
- [x] **Do NOT** wrap the append in a phase check — the tool is available in both phases (see AC2 rationale).
- [x] **Do NOT** modify the existing `if phase == "dossier": combined_tools.append(APPLY_OPS_TOOL)` line.
- [x] **Do NOT** change MCP tool registration (`tools` arg passed into `_agentic_loop`) — it's untouched.

### Task 3: Dispatch the tool in the agentic loop (AC: #3, #4)

- [x] In `_agentic_loop`'s tool-handling block (`app/chat.py:761-799`), insert a new dispatch branch between the existing `apply_ops` branch (line 773) and the `elif mcp_session is not None:` branch (line 779):
  ```python
  elif tool_name == "update_investigation_item":
      try:
          result = update_investigation_item(
              tool_input.get("item_id", ""),
              tool_input.get("value"),
          )
          tool_output = json.dumps(result)
      except Exception as exc:
          logger.error("update_investigation_item failed: %s", exc)
          tool_output = f"Error calling update_investigation_item: {exc}"
  ```
- [x] **Use `tool_input.get(...)`** with defaults — never index `tool_input["item_id"]` directly. Even though `input_schema` declares both fields required, defensive access prevents a malformed LLM call from raising `KeyError` instead of returning the helper's structured error.
- [x] `update_investigation_item` is **synchronous** — do **not** `await` it (Story 11.1 deliberately kept it sync; awaiting would raise `TypeError`).
- [x] `json.dumps(result)` is the exact serialisation used here. **Do NOT** stringify with `str(result)` — the LLM expects valid JSON in `tool_result.content` to round-trip the contract dict.
- [x] The `step.output` truncation (`tool_output[:500] + "…"` at `app/chat.py:792`) already runs after the dispatch — leave it untouched. The helper's JSON output is short (~80 chars) and won't truncate in practice.

### Task 4: Unit tests in `tests/app/test_chat.py` (AC: #6)

- [x] Add a new test class `TestUpdateInvestigationItemTool` near `TestInvestigationSessionState`.
- [x] Tests:
  - `test_tool_definition_shape` (AC1) — assert `UPDATE_INVESTIGATION_ITEM_TOOL["name"] == "update_investigation_item"`, `input_schema["required"] == ["item_id", "value"]`, `input_schema["properties"]["item_id"]["enum"]` equals the 10-item list.
  - `test_tool_registered_in_investigating_phase` (AC2a) — patch `cl.user_session` with default `dossier=None`; capture `combined_tools`; assert `"update_investigation_item"` present and `"apply_ops"` absent.
  - `test_tool_registered_in_dossier_phase` (AC2b) — patch `cl.user_session` with `dossier={"phase": "dossier"}` and a `doc_mock`; assert both `"apply_ops"` and `"update_investigation_item"` present.
  - `test_dispatch_calls_helper_and_serializes_result` (AC3a/AC3b) — build a fake stream that returns a `tool_use` block (`name="update_investigation_item"`, input `{"item_id": "topic_definition", "value": "Climate"}`) on call 1, then a plain text block on call 2; capture `history` after the loop; assert one entry has `role == "user"` whose `content[0]["type"] == "tool_result"` and `json.loads(content[0]["content"])` equals `{"status": "ok", "item": "topic_definition", "items_done": 1, "phase_gate_reached": False}`.
  - `test_dispatch_handles_helper_exception` (AC3c) — patch `app.chat.update_investigation_item` with a side-effect that raises `RuntimeError("boom")`; run the dispatch; assert the captured `tool_result.content` starts with `"Error calling update_investigation_item:"` and `caplog` (at `ERROR`) contains a matching record.
  - `test_dispatch_unknown_item_id_returns_structured_error` (AC4) — feed `tool_use` input `{"item_id": "bogus", "value": "x"}`; assert `json.loads(tool_result.content)` equals `{"error": "Unknown item_id: 'bogus'"}`. **Do not** patch the helper — exercise the real Story 11.1 logic.
  - `test_snapshot_reflects_update_in_next_round` (AC5) — two-round fake stream; first round emits `tool_use` for `("topic_definition", "Climate")`; second round emits text. Capture `system` kwarg of each `client.messages.stream(...)` call; assert round 2's system contains `[x] topic_definition: Climate`.
- [x] Reuse the existing fake-stream / fake-content-block helpers (`_make_fake_content_block`, `_make_final_message`, `FakeStream` — `tests/app/test_chat.py:19-110`). Mirror the patterns in `TestMcpToolUse::test_apply_ops_*` (around `tests/app/test_chat.py:511`) and `TestAgenticLoopIntegration` for two-round flows.
- [x] Mock `cl.Step` so the `async with cl.Step(...) as step:` block doesn't require a real Chainlit context (the existing tool-use tests do this — copy the pattern).
- [x] Follow project conventions: tests in classes, docstrings reference AC numbers (`"""AC3a: ..."""`), `dict[str, Any]`, `X | None`. `asyncio_mode = "auto"` is global.

### Task 5: Lint, format, full test suite (AC: #7)

- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pytest -q`

### Review Findings

- [x] [Review][Defer] `update_investigation_item` mutates session dict in-place without `cl.user_session.set` on normal path [`app/chat.py:137`] — deferred, pre-existing (Story 11.1 design)
- [x] [Review][Defer] Pre-dispatch `json.dumps(tool_input, indent=2)` not wrapped in try/except — crash path if tool_input contains non-serialisable value [`app/chat.py:805`] — deferred, pre-existing (agentic loop)
- [x] [Review][Defer] No per-phase enforcement of which `item_id` values are legal — LLM can record phase-1 items in dossier phase or vice-versa [`app/chat.py:816`] — deferred, design concern for Story 11.3
- [x] [Review][Defer] No investigation snapshot injected in dossier phase while `update_investigation_item` is still registered — LLM has no checklist visibility when recording items 6-10 [`app/chat.py:731`] — deferred, Story 11.1 design decision (AC4b)
- [x] [Review][Defer] MCP name collision — local tool appended without deduplication check against MCP tool list [`app/chat.py:734`] — deferred, already tracked in deferred-work.md as `[10-4]`; local dispatch precedence is the mitigation
- [x] [Review][Defer] `phase_gate_reached: False` hardcoded permanently [`app/chat.py:145`] — deferred, intentional placeholder explicitly documented in Dev Notes; Story 11.3 owns the swap

---

## Dev Notes

### What this story is (and is not)

**Is:** the **LLM-facing** layer for the Story 11.1 helper — tool definition, registration, dispatch, JSON serialisation.
**Is not:** the phase gate (Story 11.3 will compute the real `phase_gate_reached` value and flip `dossier.phase`); the `propose_structure` skeleton (Story 11.4); persistence of investigation answers across sessions (out of scope, mirrors Story 11.1 deferral).

### Why register the tool in both phases (not investigating-only)

The 10-item checklist spans both phases:

- **Items 1–5** (`topic_definition`, `geography_scope`, `time_range`, `target_audience`, `data_sources_validation`) — gathered in `investigating`. These trigger the phase gate (Story 11.3).
- **Items 6–10** (`key_stats_capture`, `narrative_structure`, `case_studies`, `story_pitches`, `methodology`) — gathered while the journalist co-edits the dossier in `dossier` phase.

Registering the tool only in `investigating` would block items 6–10. Registering it in both phases is the simplest correct choice and matches the epic intent (`epics.md:1583-1612`). `apply_ops` remains dossier-only because it has no meaning during the interview.

### Why `value` has no JSON type constraint in the schema

Anthropic's tool `input_schema` is JSON Schema. If we set `"type": "string"`, the LLM would refuse structured `value` payloads needed for items 6–10 (e.g. `key_stats_capture: {"indicators": [...], "headline_numbers": [...]}`). If we set `"type": "object"`, free-text items 1–5 would round-trip clumsily. Leaving the type unconstrained — JSON Schema treats this as "any" — lets the LLM use the most natural shape per item. The runtime helper accepts `Any` anyway (Story 11.1 design choice).

### Why JSON-serialise instead of returning a dict directly

Anthropic's `tool_result.content` accepts a string (plain text) or a list of content blocks. Existing dispatch paths already produce strings:

- `apply_ops` returns `"ok"` or an error string.
- MCP path returns text via `_extract_tool_result_text`.

`update_investigation_item` returns a structured dict. Stringifying with `json.dumps` keeps the LLM able to parse the response (`{"status": "ok", "item": ..., "items_done": ..., "phase_gate_reached": ...}`) without changing the dispatch contract. Round-tripping through `json.loads` in tests is the assertion convention.

### Why dispatch ordering matters

Inserting the new `elif` between `apply_ops` and the MCP fallback means:

1. `apply_ops` is checked first (highest precedence).
2. `update_investigation_item` is matched explicitly.
3. Anything else falls through to MCP — including any future MCP server that happens to register a tool named `update_investigation_item`. The local dispatch wins on name collision, which is intentional: the local helper writes to `cl.user_session` synchronously, the MCP path is async and would not update local state.

This collides with the deferred-work item `[10-4] APPLY_OPS_TOOL appended to combined_tools without name-deduplication` (`deferred-work.md:11`). The mitigation here is the same as for `apply_ops`: local dispatch precedence. Do **not** add a name-dedup pass in this story — it's a cross-tool concern still deferred.

### Cross-story context

- **Story 11.1** (`11-1-investigation-session-state.md`, just merged in PR #59) — provides `_INVESTIGATION_ITEMS`, `_empty_investigation_state()`, `_format_investigation_snapshot()`, `update_investigation_item()`, and the snapshot append in `_build_call_kwargs()`. This story extends the **same `_build_call_kwargs()`** with one more `combined_tools.append(...)` line, and the **same `_agentic_loop` dispatch** with one more `elif`. No file beyond `app/chat.py` is touched in source.
- **Story 10.3** (`10-3-apply-ops-patch-engine.md`) — established the `APPLY_OPS_TOOL` constant + dispatch pattern. Mirror it exactly. Do **not** invent a different dispatch shape.
- **Story 10.4** (`10-4-dossier-system-prompt.md`) — introduced `_build_call_kwargs()` and the phase-aware tool list. Story 11.1 extended the prompt; this story extends the tool list. Together with 11.3 (phase flip) the loop is feature-complete for Epic 11's first half.

### Resume parity

`on_chat_resume` already re-seeds `investigation` (Story 11.1). Tool registration is per-call (rebuilt in `_build_call_kwargs` every round), so resumed threads automatically get the new tool with no code change. **Do not** touch `on_chat_resume` in this story.

### What this story does NOT do

- **Does NOT** wrap the helper as `async def` — it's sync per Story 11.1.
- **Does NOT** add a phase gate or flip `dossier.phase` — Story 11.3.
- **Does NOT** change the `phase_gate_reached` value returned by the helper — still hard-coded `False`. Story 11.3 will swap.
- **Does NOT** generate any document content — Story 11.4.
- **Does NOT** edit `INVESTIGATION_SYSTEM_PROMPT` or `DOSSIER_SYSTEM_PROMPT` text. The tool description in the schema is the only LLM-visible new text.
- **Does NOT** persist investigation state across sessions.
- **Does NOT** add tool-name dedup (deferred-work item).

---

## Latest Tech Information

### Anthropic SDK — `tool_use` and `tool_result` round-trip

| Field | Where | Notes |
|---|---|---|
| `tool_use.id` | `assistant_content[i].id` (block-level) | Echoed back as `tool_result.tool_use_id`. |
| `tool_use.name` | `assistant_content[i].name` | Used for dispatch (`if tool_name == ...`). |
| `tool_use.input` | `assistant_content[i].input` | Pre-decoded dict (Anthropic SDK parses JSON for us). |
| `tool_result.content` | string OR list of content blocks | Strings are simplest — keep that. `json.dumps(...)` is the path. |
| `input_schema` | tool definition | JSON Schema; `enum` is supported on `string` properties. |

### JSON Schema — open-typed properties

JSON Schema treats a property without `"type"` as accepting any JSON value (`null`, `boolean`, `number`, `string`, `object`, `array`). Anthropic's tool-use validator follows this. Verified by `apply_ops`'s `input` already using a free-shape `value` style for op `content` strings. No SDK change needed.

### chainlit 2.10 — `cl.Step`

`async with cl.Step(name="🔧 update_investigation_item", type="tool") as step:` already wraps the dispatch in `_agentic_loop`. The step output truncation at `app/chat.py:792` is shared across all tool branches — the new dispatch inherits it for free. **Do not** add a per-tool truncation.

---

## Previous Story Intelligence

### From Story 11.1 (`11-1-investigation-session-state.md`)

- `update_investigation_item(item_id, value)` is a **sync** Python function. **Do not** `await` it.
- Return contract is **stable**: `{"status": "ok", "item": ..., "items_done": ..., "phase_gate_reached": False}` for known IDs; `{"error": "Unknown item_id: '<id>'"}` for unknown IDs. This story serialises both shapes verbatim — no transformation.
- The helper writes to `cl.user_session["investigation"]` directly. In tests, the `_make_session_mock_with_history` helper now accepts an `investigation` kwarg (added in 11.1) — reuse it.
- The DEBUG log emitted by the helper is `caplog`-testable at `logger="app.chat"`. This story doesn't need to re-test it (Story 11.1 covers it; AC4 here just requires that unknown IDs don't emit one).

### From Story 10.3 (`10-3-apply-ops-patch-engine.md`)

- `_handle_apply_ops` returns `"ok"` or an error string. The dispatch uses that string verbatim as `tool_output`. **This story diverges**: the helper returns a dict, so we add a `json.dumps(...)` step. Document this difference in code if helpful but the dispatch shape is otherwise identical.
- Try/except around the call is mandatory — `apply_ops` does it (`app/chat.py:773-778`), MCP path does it. Mirror exactly.

### From Story 10.4 (`10-4-dossier-system-prompt.md`)

- `_build_call_kwargs()` runs **every round**, so a tool list change made here is picked up next round automatically — no special wiring needed for AC5.
- `combined_tools = list(tools)` shallow-copies the MCP tool list each round, so appending `UPDATE_INVESTIGATION_ITEM_TOOL` doesn't mutate the cached MCP list.

---

## Git Intelligence Summary

Recent commits relevant to this story:

- `093fd95` `feat(11-1): investigation session state foundation` (PR #59, on `story/11-1-investigation-session-state`) — **direct dependency**. Provides `_INVESTIGATION_ITEMS`, `update_investigation_item`, snapshot helper. Branch off `main` after #59 merges, OR branch off the 11-1 branch if 11-1 is not yet merged when work begins.
- `78ff32c` `fix(10-3): reject append/prepend ops with empty content (#58)` — confirms `_handle_apply_ops` shape this story mirrors.
- `e32b869` `feat(10-4): phase-aware system prompts for dossier canvas (#55)` — confirms `_build_call_kwargs` location and structure.
- `ce08a69` `feat(10-3): apply_ops patch engine for dossier canvas (#54)` — `APPLY_OPS_TOOL` definition + `_handle_apply_ops` dispatch. The exact pattern this story replicates (with the dict-vs-string serialisation difference).

**Branch:** create `story/11-2-update-investigation-item-tool` from `main` once PR #59 is merged. If implementing before #59 merges, branch from `story/11-1-investigation-session-state`.
**Commit format:** `feat(11-2): description`.

---

## Project Context Reference

This story must follow the rules in `_bmad-output/project-context.md`. Highlights for this story:

- **Python 3.12+ union syntax** — `dict[str, Any]`, `X | None`. **Never** `Optional`.
- **Async I/O** — the dispatch is inside an `async def _agentic_loop`, but `update_investigation_item` is **sync**. Do not `await` a sync function (would raise `TypeError`).
- **Type hints required** on every new function signature (this story adds no new functions — only a constant and dispatch lines — but the existing `_build_call_kwargs()` and `_agentic_loop()` signatures stay typed).
- **System prompt text lives in `app/prompts.py`** — this story adds NO prompt text. The tool's `description` field is part of the tool schema, not a system prompt.
- **Citation pipeline untouched** — investigation tool calls are **not** citation-bearing. They produce JSON status output that should NOT be threaded into `app/citations.py`. Verify: `extract_references(all_tool_outputs)` ignores non-MCP tool outputs naturally (it parses for indicator/database fields). No code change needed, but **do not** filter `update_investigation_item` outputs out of `all_tool_outputs` either — keeping them in is harmless and matches `apply_ops` behavior.
- **No hardcoded values** — the tool `name`, `enum` values, and `description` ARE the spec; encoding them in `app/chat.py` is correct.
- **Pre-commit ruff hooks** enforce E/F/W/I, double quotes, line length 120.

---

## File Structure Requirements

| Path | Change | Reason |
|---|---|---|
| `app/chat.py` | UPDATE | Add `UPDATE_INVESTIGATION_ITEM_TOOL` constant; append it to `combined_tools` in `_build_call_kwargs()`; add `elif tool_name == "update_investigation_item":` dispatch branch in `_agentic_loop`. |
| `tests/app/test_chat.py` | UPDATE | Add `TestUpdateInvestigationItemTool` class (~7 tests). |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | UPDATE (workflow) | Status transitions managed by create-story / dev-story workflows. |

Files this story must **not** touch:

- `app/prompts.py` — no prompt edits.
- `app/citations.py` — citation pipeline unchanged.
- `mcp_server/**` — server-side untouched.
- `app/data.py`, `app/db.py` — no persistence changes.
- `_bmad-output/implementation-artifacts/deferred-work.md` — no items closed.

---

## Testing Requirements

- Tests in `tests/app/test_chat.py`. Conventions:
  - Group tests in classes with docstrings referencing AC numbers (`"""AC3a: ..."""`).
  - `asyncio_mode = "auto"` is global — `@pytest.mark.asyncio` is redundant but acceptable.
  - Reuse `_make_session_mock_with_history(investigation=...)` (Story 11.1 extension).
  - Reuse `_make_fake_content_block(block_type="tool_use", name=..., input=..., id=...)` and `FakeStream` patterns from the top of `tests/app/test_chat.py`.
- For two-round flows (AC3, AC5), build a stream factory that returns different `FakeStream` instances per call. The existing `TestAgenticLoopIntegration` class (`tests/app/test_chat.py:884-1104`) is the gold-standard pattern — copy from there.
- For exception-path test (AC3c), patch `app.chat.update_investigation_item` with `side_effect=RuntimeError("boom")`. Use `caplog.at_level("ERROR", logger="app.chat")` to capture the error log.
- Round-trip JSON in assertions:
  ```python
  result = json.loads(tool_result["content"])
  assert result == {"status": "ok", "item": "topic_definition", "items_done": 1, "phase_gate_reached": False}
  ```
- New test count: ~7. Existing 363 must continue passing.

---

## Anti-Patterns (do NOT do)

- **DON'T** `await update_investigation_item(...)` — the helper is sync. Awaiting would raise `TypeError: object dict can't be used in 'await' expression`.
- **DON'T** stringify the helper's return with `str(result)` — produces a Python repr (`"{'status': 'ok', ...}"`), not valid JSON. Use `json.dumps(result)`.
- **DON'T** index `tool_input["item_id"]` directly — use `.get("item_id", "")` so a malformed LLM call returns the helper's structured error rather than a `KeyError` exception.
- **DON'T** register the tool conditionally on phase — it's needed in both phases (items 1-5 in investigating, items 6-10 in dossier).
- **DON'T** add tool-name deduplication for `update_investigation_item` vs MCP — same deferred-work item as `apply_ops`. Local dispatch precedence is the mitigation.
- **DON'T** change `phase_gate_reached`'s value — it's hard-coded `False` in Story 11.1 deliberately. Story 11.3 owns the swap.
- **DON'T** edit the existing `apply_ops` dispatch branch — only insert a new `elif` between it and the MCP branch. AC2b is the regression guard for `apply_ops` registration.
- **DON'T** add the tool to `INVESTIGATION_SYSTEM_PROMPT` or `DOSSIER_SYSTEM_PROMPT` text. The Anthropic API surfaces tool definitions to the LLM directly via the `tools` parameter; duplicating in the prompt is redundant token waste and a known anti-pattern.
- **DON'T** filter `update_investigation_item` outputs out of `all_tool_outputs` — `extract_references` (Story 9.1) already ignores non-citation outputs by parsing for specific keys. No special-casing needed.
- **DON'T** wire `update_investigation_item` calls into the dossier document — the helper writes only to `cl.user_session["investigation"]`. Document mutation is `apply_ops`'s job (Story 10.3) and the skeleton is Story 11.4's job.
- **DON'T** introduce `cl.Step` customisation for this tool — the generic `🔧 {tool_name}` step works fine and matches `apply_ops` UX.

---

## References

- `_bmad-output/planning-artifacts/epics.md` → "Story 11.2: update_investigation_item Tool" (lines 1558–1574).
- `_bmad-output/project-context.md` → Critical Implementation Rules.
- `_bmad-output/implementation-artifacts/11-1-investigation-session-state.md` → contract for `update_investigation_item` and snapshot append.
- `_bmad-output/implementation-artifacts/10-3-apply-ops-patch-engine.md` → reference pattern for `APPLY_OPS_TOOL` + dispatch.
- `_bmad-output/implementation-artifacts/deferred-work.md` → `[10-4] APPLY_OPS_TOOL appended to combined_tools without name-deduplication` (same mitigation applies here).
- `app/chat.py:185-233` → `APPLY_OPS_TOOL` definition (insertion point for `UPDATE_INVESTIGATION_ITEM_TOOL`).
- `app/chat.py:681-708` → `_build_call_kwargs()` (insertion point for `combined_tools.append(...)`).
- `app/chat.py:761-799` → `_agentic_loop` dispatch switch (insertion point for new `elif`).
- `tests/app/test_chat.py:19-110` → `_make_fake_content_block`, `FakeStream`, `_make_fake_cl_message` helpers.
- `tests/app/test_chat.py:405-426` → `_make_session_mock_with_history` (extended in 11.1 with `investigation`).
- `tests/app/test_chat.py:511-558` → `test_apply_ops_registered_in_dossier_phase` / `test_apply_ops_not_registered_in_investigating_phase` — pattern to mirror for AC2 tests.
- `tests/app/test_chat.py:884-1104` → `TestAgenticLoopIntegration` — pattern for multi-round tool-use tests.

---

## Dev Agent Record

### Agent Model Used

claude-opus-4-7

### Debug Log References

- One pre-existing test (`TestMcpToolUse::test_apply_ops_registered_in_dossier_phase`) broke after Task 2 because it asserted exact equality `passed_names == ["apply_ops"]`. Relaxed to `assert "apply_ops" in passed_names` with an inline note pointing to Story 11.2. The test's intent (Story 10.4: apply_ops registration in dossier phase) is preserved.

### Completion Notes List

- All 7 ACs satisfied. Single-file source change in `app/chat.py`:
  - `UPDATE_INVESTIGATION_ITEM_TOOL` added alongside `APPLY_OPS_TOOL`.
  - `combined_tools.append(UPDATE_INVESTIGATION_ITEM_TOOL)` placed before the dossier-only `APPLY_OPS_TOOL` append (both-phase registration per AC2).
  - New `elif tool_name == "update_investigation_item":` branch inserted between `apply_ops` and the MCP fallback. `json.dumps(result)` serialisation, `try/except` parity with surrounding branches.
- `value` schema property has no `"type"` key (per Dev Notes) — accepts strings and structured objects across items 1–10.
- `update_investigation_item` is sync — no `await`. `tool_input.get(..., default)` used defensively per Dev Notes.
- 7 new tests added (`TestUpdateInvestigationItemTool`) covering tool shape, phase-aware registration, dispatch happy path, exception path, unknown `item_id` round-trip, and snapshot reflection in round N+1.
- Lint clean. Format clean (39 files already formatted).
- Full suite: **370 passed** (363 baseline + 7 new), 0 failed.
- No edits to `app/prompts.py`, `app/citations.py`, `mcp_server/**`, or `deferred-work.md` (matches the "must not touch" list).
- Deferred-work item `[10-4] APPLY_OPS_TOOL appended to combined_tools without name-deduplication` now applies to `update_investigation_item` too. Not addressed here; intentional per Dev Notes (cross-tool concern, deferred).

### File List

- `app/chat.py` — added `UPDATE_INVESTIGATION_ITEM_TOOL` constant; appended to `combined_tools` in `_build_call_kwargs()`; added new `elif tool_name == "update_investigation_item":` dispatch branch in `_agentic_loop`.
- `tests/app/test_chat.py` — added `TestUpdateInvestigationItemTool` (7 tests). Relaxed `test_apply_ops_registered_in_dossier_phase` from list-equality to membership assertion (regression fix from Task 2).
- `_bmad-output/implementation-artifacts/11-2-update-investigation-item-tool.md` — task checkboxes, status, dev agent record (this file).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status transitions backlog → ready-for-dev → in-progress → review.

### Change Log

| Date       | Change                                                                                  |
|------------|-----------------------------------------------------------------------------------------|
| 2026-05-13 | Story created via `bmad-create-story`. Status: ready-for-dev.                            |
| 2026-05-13 | Implementation complete: tool definition, registration in both phases, dispatch with JSON serialisation, 7 new tests. Full suite green. Status: review. |
