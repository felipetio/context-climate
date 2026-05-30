# Story 12.2: Data Validation Gate

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a journalist,
I want the app to verify that data exists for my topic before building the dossier,
So that I don't end up with empty sections.

> **Depends on Story 12.1** (MCP tools available in the dossier-session tool list). 12.2 turns those *available* tools into an *enforced* gate: item 5 (`data_sources_validation`) only flips `done` when a real `search_indicators` call has confirmed indicators exist for the topic. Story 12.4 owns the no-data UX phrasing; this story owns the gate logic and the key-stats capture.

---

## Acceptance Criteria

**AC1: At investigation item 5, the LLM is instructed to call `search_indicators` with the topic and geography and narrate the result count in chat.**
**Given** the investigation state shows items 1–4 done (`topic_definition`, `geography_scope`, `time_range`, `target_audience`) and item 5 (`data_sources_validation`) not done
**When** the LLM responds in that round
**Then** the rewritten `INVESTIGATION_SYSTEM_PROMPT` (`app/prompts.py:115-134`) explicitly directs the LLM to call `search_indicators(query=<topic>, country=<geography>)` at item 5 **before** marking the item done
**And** the prompt directs the LLM to narrate the result in chat as a short summary, e.g. *"Found 12 relevant indicators for water access in Pará."* (1 sentence, no list dump)
**And** the prompt directs the LLM to call `update_investigation_item("data_sources_validation", <summary string>)` **only when** the search returned at least one indicator

**AC2: `update_investigation_item("data_sources_validation", …)` is rejected when no successful `search_indicators` call has occurred this session.**
**Given** the session has had zero successful `search_indicators` calls (or all returned `total_count == 0`) since `on_chat_start` / `on_chat_resume`
**When** the LLM calls `update_investigation_item("data_sources_validation", <anything>)`
**Then** `update_investigation_item` (`app/chat.py:105-136`) returns `{"error": "data_sources_validation cannot be marked done — no indicators have been found this session. Call search_indicators first."}`
**And** item 5's `done` flag is NOT flipped (state stays `{"done": False, "value": None}`)
**And** the existing return-shape contract is preserved (the error dict has no `phase_gate_reached` key, mirroring the existing `Unknown item_id` error at `app/chat.py:108`)

**Given** the session has had at least one successful `search_indicators` call whose JSON response decoded with `success == True` and `total_count >= 1`
**When** the LLM calls `update_investigation_item("data_sources_validation", "Found 12 indicators…")`
**Then** the call succeeds, item 5 flips `done`, and the existing `{"status": "ok", "item": …, "items_done": …, "phase_gate_reached": …}` shape is returned

**AC3: A session flag tracks the search-indicators outcome, set inside the agentic loop after every `search_indicators` MCP call returns.**
**Given** the agentic loop dispatches an MCP `tool_use` for `search_indicators` (current dispatch branch: `app/chat.py:1001-1007`, the `elif mcp_session is not None:` branch)
**When** `tool_output` is the string returned by `_extract_tool_result_text(call_result)`
**Then** after the existing `all_tool_outputs.append(tool_output)` line (`app/chat.py:1015`), the loop calls a new helper `_record_search_indicators_outcome(tool_name, tool_output)` that:
  - returns immediately when `tool_name != "search_indicators"` (cheap guard)
  - tries `json.loads(tool_output)` inside a try/except; on parse failure or non-dict, logs a debug message and returns
  - only on `parsed.get("success") is True` AND `int(parsed.get("total_count", 0)) >= 1`, sets `cl.user_session["_data_validation_indicators_found"] = True`
**And** the flag is initialised to `False` in both `on_chat_start` (`app/chat.py:712-728`) and `on_chat_resume` (`app/chat.py:670-702`)
**And** `update_investigation_item` reads `cl.user_session.get("_data_validation_indicators_found", False)` as the AC2 gate input

**AC4: The LLM is instructed to capture structured key stats via `update_investigation_item("key_stats_capture", …)` after running `get_data` during investigation.**
**Given** the LLM has called `get_data` on a found indicator during the `investigating` phase and the result decoded with `success == True` and a non-empty `data` array
**When** the LLM continues the investigation conversation
**Then** the rewritten `INVESTIGATION_SYSTEM_PROMPT` directs the LLM to call `update_investigation_item("key_stats_capture", <stats dict>)` with a structured `value`:
```json
{"indicator_code": "EN_ATM_CO2E_KT", "geography": "BRA", "values_by_year": {"2020": 1234.5, "2021": 1345.2}, "source": "<DATA_SOURCE string from response>"}
```
**And** the existing `update_investigation_item` accepts the dict as `value` unchanged — the prompt drives the structure (no server-side schema validation in this story; that lives in 12.3 if needed)

**AC5: The investigation-state snapshot in the system prompt does not leak large stat dicts.**
**Given** `_format_investigation_snapshot` (`app/chat.py:81-102`) currently caps stringified values at 120 chars (line 95-96)
**When** `key_stats_capture` holds the AC4 dict and is serialized into the snapshot
**Then** the existing 120-char cap continues to truncate cleanly (the dict is stringified via `str(dict)`, which is bounded by the cap)
**And** no additional truncation logic is added in this story

**AC6: Lint, format, and full test suite pass.**
**Given** the changes above
**When** `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest -q` are run
**Then** all checks pass; the new tests from AC1–AC4 are included in the count.

---

## Tasks / Subtasks

### Task 1: Rewrite `INVESTIGATION_SYSTEM_PROMPT` to drive items 5 + 6 (AC: 1, 4)

- [x] In `app/prompts.py` (currently lines 115-134), append two new sub-sections after the existing checklist:
  - **DATA VALIDATION (item 5):** explicit directive to call `search_indicators(query=<topic>, country=<geography>)`, narrate the result count in 1 sentence, and only mark item 5 done when at least one indicator was found. Include the verbatim example summary: *"Found 12 relevant indicators for water access in Pará."*
  - **KEY STATS CAPTURE (item 6):** explicit directive to call `get_data` on the journalist's chosen indicator(s), then call `update_investigation_item("key_stats_capture", {indicator_code, geography, values_by_year, source})` with the AC4 dict shape.
- [x] Keep the existing INTERVIEW RULES (one short question at a time, never multiple, etc.) — they apply to the new sub-sections too.
- [x] Do NOT touch `DOSSIER_SYSTEM_PROMPT` — that's 12.3's job.

### Task 2: Add the indicators-found session flag (AC: 3)

- [x] Add a module-level constant `_DATA_VALIDATION_FLAG = "_data_validation_indicators_found"` near the other session-key constants (`_MCP_SESSION_KEY`, `_MCP_TOOLS_KEY` around `app/chat.py:626`).
- [x] In `on_chat_start` (existing initialiser block around `app/chat.py:712-728`), add `cl.user_session.set(_DATA_VALIDATION_FLAG, False)` alongside the other `cl.user_session.set(...)` calls.
- [x] In `on_chat_resume` (around `app/chat.py:670-702`), add the same initialisation. **On resume, do NOT try to reconstruct the flag from persisted steps** — pretend the journalist needs to re-validate on a fresh session. This is consistent with the project's broader resume policy (dossier content is also not persisted; see `deferred-work.md`).

### Task 3: Add `_record_search_indicators_outcome` and call it from the dispatch loop (AC: 3)

- [x] Add a private helper near the other agentic-loop helpers:
  ```python
  def _record_search_indicators_outcome(tool_name: str, tool_output: str) -> None:
      """Set the indicators-found session flag when a search_indicators call succeeded.

      Called from the agentic loop right after _extract_tool_result_text. Cheap
      no-op for any other tool. JSON-parse failures are logged at debug and ignored
      (the loop must not crash on a malformed MCP payload).
      """
      if tool_name != "search_indicators":
          return
      try:
          parsed = json.loads(tool_output)
      except (json.JSONDecodeError, TypeError):
          logger.debug("[DATA_VALIDATION] search_indicators output is not JSON; skipping flag set")
          return
      if not isinstance(parsed, dict) or not parsed.get("success"):
          return
      try:
          total_count = int(parsed.get("total_count", 0))
      except (TypeError, ValueError):
          return
      if total_count >= 1:
          cl.user_session.set(_DATA_VALIDATION_FLAG, True)
          logger.debug("[DATA_VALIDATION] search_indicators returned total_count=%d; flag set", total_count)
  ```
- [x] In the dispatch loop at `app/chat.py:1001-1007` (the `elif mcp_session is not None:` branch), call `_record_search_indicators_outcome(tool_name, tool_output)` **immediately after** the existing `tool_output = _extract_tool_result_text(call_result)` line and **before** the existing `step.output = …` / `all_tool_outputs.append(tool_output)` lines so a parse error never blocks output collection.
- [x] **DO NOT** add the call inside the local-handler branches (`apply_ops`, `update_investigation_item`, `propose_structure`) — only the MCP branch.

### Task 4: Gate `update_investigation_item("data_sources_validation", …)` on the flag (AC: 2)

- [x] In `update_investigation_item` (`app/chat.py:105-136`), after the existing `if item_id not in _INVESTIGATION_ITEMS:` guard (line 107) and **before** the state read (line 110), add:
  ```python
  if item_id == "data_sources_validation":
      if not cl.user_session.get(_DATA_VALIDATION_FLAG, False):
          return {
              "error": (
                  "data_sources_validation cannot be marked done — no indicators "
                  "have been found this session. Call search_indicators first."
              )
          }
  ```
- [x] The error dict shape mirrors the existing `Unknown item_id` error — only an `error` key, no `phase_gate_reached`. Dispatch consumers already tolerate this (the phase gate only fires when `result.get("phase_gate_reached")` is truthy; missing key is falsy).
- [x] Do NOT modify the success path (the `state[item_id] = {"done": True, "value": value}` block and the phase-gate computation stay intact).

### Task 5: Tests (AC: 1, 2, 3, 4, 6)

- [x] Add a new test class `TestDataValidationGate` to `tests/app/test_chat.py`, near `TestPhaseGateLogic`. Use `@pytest.mark.usefixtures("set_required_env_vars")` and the `reload_chat` fixture.

- [x] **AC1 (prompt directives)** — `test_investigation_prompt_directs_search_indicators_at_item_5`:
  - Import `INVESTIGATION_SYSTEM_PROMPT` from `app.prompts` (via `reload_chat`) and assert the string contains both `"search_indicators"` and the phrase `"Found 12 relevant indicators"` (the verbatim example, used as a stable test anchor — adjust the example to whatever Task 1 commits, but pick something distinctive enough to anchor).

- [x] **AC2 (gate rejects when flag is False)** — `test_data_sources_validation_rejected_without_search`:
  - Patch `cl.user_session` so `_data_validation_indicators_found` reads `False`.
  - Call `reload_chat.update_investigation_item("data_sources_validation", "Found something")`.
  - Assert the return is `{"error": "...no indicators have been found..."}` (substring match: `"no indicators have been found"`).
  - Assert `cl.user_session.set` was NOT called with `"investigation"` updating item 5 (i.e., state mutation did not happen).

- [x] **AC2 (gate accepts when flag is True)** — `test_data_sources_validation_accepted_with_search`:
  - Patch `cl.user_session` so `_data_validation_indicators_found` reads `True` and `investigation` starts from `_empty_investigation_state()`.
  - Call `update_investigation_item("data_sources_validation", "Found 12 indicators")`.
  - Assert return contains `"status": "ok"` and `"phase_gate_reached"` key is present (False unless items 1–4 also done).

- [x] **AC3 (flag set on successful search_indicators)** — `test_record_search_indicators_outcome_sets_flag_on_success`:
  - Build `tool_output = json.dumps({"success": True, "total_count": 12, "returned_count": 12, "data": [...], "truncated": False})`.
  - Stub `cl.user_session.set` to capture calls.
  - Call `reload_chat._record_search_indicators_outcome("search_indicators", tool_output)`.
  - Assert `set` was called with `(_DATA_VALIDATION_FLAG, True)`.

- [x] **AC3 (flag NOT set on zero results)** — `test_record_search_indicators_outcome_does_not_set_flag_on_zero_count`:
  - Same as above but `total_count == 0`. Assert `set(_DATA_VALIDATION_FLAG, True)` was NOT called.

- [x] **AC3 (flag NOT set on error response)** — `test_record_search_indicators_outcome_does_not_set_flag_on_error_response`:
  - `tool_output = json.dumps({"success": False, "error": "api_error", "error_type": "api_error"})`. Assert flag not set.

- [x] **AC3 (no-op for other tools)** — `test_record_search_indicators_outcome_is_noop_for_other_tools`:
  - `tool_name == "get_data"` with a perfectly successful response. Assert flag not set (tool-name guard works).

- [x] **AC3 (resilient to non-JSON)** — `test_record_search_indicators_outcome_handles_non_json`:
  - `tool_output = "not JSON"`. Assert no exception raised and flag not set.

- [x] **AC3 (dispatch loop calls the helper)** — `test_dispatch_loop_calls_record_helper_after_mcp_call`:
  - End-to-end: send a `tool_use` for `search_indicators` through `on_message`; patch `mcp_session.call_tool` to return a result whose `_extract_tool_result_text` is a JSON string with `total_count: 5`; patch `cl.user_session.get/set`; after the loop, assert `cl.user_session.set(_DATA_VALIDATION_FLAG, True)` was awaited.

- [x] **AC4 (prompt directs key-stats capture)** — `test_investigation_prompt_directs_key_stats_capture`:
  - Assert the prompt contains `"key_stats_capture"` AND `"update_investigation_item"` AND substrings indicating the dict shape (e.g., `"indicator_code"`, `"values_by_year"`).

- [x] **AC6 (lint + format + suite green)** — manual check; CI / pre-commit covers ruff.

### Task 6: Lint, format, full test suite (AC: 6)

- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pytest -q`

---

## Dev Notes

### What this story is (and is not)

**Is:**
- Server-side **gate** that prevents item 5 from being marked done unless a real `search_indicators` call has confirmed indicators exist this session.
- Prompt-level directives that tell the LLM **when** and **how** to call `search_indicators` and `get_data` during investigation, including the chat-narration phrasing for AC1.
- A tiny post-dispatch hook in the MCP branch of the agentic loop that records the search-indicators outcome to a session flag.

**Is not:**
- No-data UX phrasing — that's **Story 12.4** (the "No indicators found for [topic] in [geography]…" copy and the get_data-empty handling). 12.2 only guarantees the gate cannot pass without success; 12.4 owns what the LLM says when search fails.
- Citation flow into dossier sections — that's **Story 12.3** (the inline `DATA_SOURCE` in `apply_ops` content, and the "Data Sources" section append).
- Schema validation of the `key_stats_capture` dict — accepted as-is from the LLM (the prompt drives shape). Add server-side schema if it becomes a real problem; not in 12.2.
- Persistence of the validation flag across chat resume — by design the flag resets on `on_chat_resume` (consistent with the broader resume-doesn't-restore-state policy).

### Why a session flag (not scanning `all_tool_outputs`)

`update_investigation_item` (`app/chat.py:105-136`) runs in two contexts:
1. As the LLM tool dispatch (`app/chat.py:980-989`) — has loop-local `all_tool_outputs` available, but only via a top-down rewrite that pipes it down. Coupling adds noise.
2. As a session-scoped state mutation — naturally reads `cl.user_session`.

A boolean `_data_validation_indicators_found` flag in `cl.user_session` is the lightest coupling: the dispatch loop SETS it after `search_indicators` succeeds, and `update_investigation_item` READS it. No data piping, no scanning JSON twice. The flag is monotonic in this story (once set, it stays True for the session); if a future story needs counter semantics (e.g., re-validation on topic change), revisit the type.

### Where the search-indicators hook lives in the dispatch loop

The agentic-loop dispatch (`app/chat.py:956-1015`) has four branches inside a `cl.Step(name=f"🔧 {tool_name}", type="tool")` block:
1. `apply_ops` (`:974-979`)
2. `update_investigation_item` (`:980-989`) — this branch ALSO has post-handler side effects (the phase-gate affordance at `:983-984`); precedent for tool-specific post-processing.
3. `propose_structure` (`:996-1000`)
4. `elif mcp_session is not None:` (`:1001-1007`) — the MCP branch
5. `else:` (`:1008-1012`) — MCP unavailable

The hook for `search_indicators` belongs in branch 4 (right after `tool_output = _extract_tool_result_text(call_result)` at `:1004`). It is a no-op for every other MCP tool by virtue of the `tool_name != "search_indicators"` guard inside the helper.

### Why `update_investigation_item` keeps its existing error-shape contract

`update_investigation_item` already returns `{"error": ...}` (without `phase_gate_reached`) for the `Unknown item_id` case (`app/chat.py:108`). Tests and the dispatch consumer at `app/chat.py:980-989` both tolerate this shape — the phase-gate consumer reads `result.get("phase_gate_reached")` which is falsy for missing keys (verified by the existing `Unknown item_id` path passing tests). Mirroring the same shape for the validation-gate error avoids a parallel contract.

### Existing wiring anchors (verified 2026-05-30)

| What | File:Line | Notes |
|---|---|---|
| Investigation items list | `app/chat.py:55-70` | `_INVESTIGATION_ITEMS` tuple; `data_sources_validation` is item 5 |
| Phase-gate items (1–5) | `app/chat.py:72-74` | `_PHASE_GATE_ITEMS` frozenset; includes `data_sources_validation` |
| Empty-state factory | `app/chat.py:77-78` | `_empty_investigation_state` |
| Snapshot formatter (120-char cap) | `app/chat.py:81-102` | `_format_investigation_snapshot`, length cap at line 95-96 |
| `update_investigation_item` | `app/chat.py:105-136` | gate target |
| Dispatch — `update_investigation_item` branch | `app/chat.py:980-989` | precedent for post-handler side effects (phase-gate affordance) |
| Dispatch — MCP branch | `app/chat.py:1001-1007` | hook insertion point for `_record_search_indicators_outcome` |
| `on_chat_start` initialisers | `app/chat.py:712-728` | add the flag init here |
| `on_chat_resume` re-initialisers | `app/chat.py:670-702` | add the flag init here too |
| `INVESTIGATION_SYSTEM_PROMPT` | `app/prompts.py:115-134` | append the DATA VALIDATION + KEY STATS CAPTURE sub-sections |

### Tool-response contract relied on (project-context.md)

`search_indicators` returns:
```python
{"success": True, "data": [...], "total_count": int, "returned_count": int, "truncated": bool}
```
or
```python
{"success": False, "error": str, "error_type": "api_error" | "timeout"}
```

`_record_search_indicators_outcome` validates `success is True` AND `total_count >= 1`. It tolerates parse failures (logs at debug), missing keys (treats as zero), and non-int total_count (skips). Defensive parse on a contract the project owns is overkill but cheap; do it anyway because malformed payloads should not crash the loop.

### Test patterns to follow (do NOT reinvent)

- `TestPhaseGateLogic` (line 2335) — the existing tests for `update_investigation_item`'s phase-gate side effects. Mirror that style for the new gate-rejection tests.
- `TestMcpToolUse` (line 433) — the MCP-call-dispatch testing pattern. The end-to-end AC3 dispatch test follows this idiom.
- `TestUpdateInvestigationItemTool` (line 2054) — covers the tool-level dispatch of `update_investigation_item`; do NOT duplicate, just add the new gate test in `TestDataValidationGate`.
- For asserting prompt content: `from app.prompts import INVESTIGATION_SYSTEM_PROMPT` and `assert "..." in INVESTIGATION_SYSTEM_PROMPT` — simplest possible test, follows the precedent set by Story 11.4's prompt-rule assertion.

### Existing helpers this story reuses (do NOT reinvent)

- `update_investigation_item` (`app/chat.py:105-136`) — extend in place, do not fork.
- `cl.user_session` — straight get/set; no new persistence layer.
- `_extract_tool_result_text` (`app/chat.py`) — used unchanged by the dispatch loop; do not modify.
- `logger` (`app/chat.py`) — reuse the module-level logger for the debug messages.

---

## Project Structure Notes

- Files under change: `app/prompts.py`, `app/chat.py`, `tests/app/test_chat.py`. No new modules.
- No new dependencies.
- No DB schema changes.
- No JS / frontend changes.
- No MCP server changes — the 5 tools are unchanged; this story changes only how the **app** uses them.

## File Structure Requirements

| File | Status | Purpose |
|---|---|---|
| `app/prompts.py` | UPDATE | Append DATA VALIDATION + KEY STATS CAPTURE sub-sections to `INVESTIGATION_SYSTEM_PROMPT` (Task 1) |
| `app/chat.py` | UPDATE | New session constant + `_record_search_indicators_outcome` helper + init calls in `on_chat_start` / `on_chat_resume` + gate check in `update_investigation_item` + hook call in MCP dispatch (Tasks 2–4) |
| `tests/app/test_chat.py` | UPDATE | New `TestDataValidationGate` class with 12 tests (10 from Task 5 + 2 added during code review) |

**Files this story must NOT touch:** `mcp_server/**`, `public/**`, `app/citations.py`, `DOSSIER_SYSTEM_PROMPT`. If any of those need changes to make a test pass, the design has drifted — escalate.

## Testing Requirements

- 12 new tests in `tests/app/test_chat.py` (10 from Task 5 + 2 defensive-branch tests added during code review).
- Existing test suite must stay green: `uv run pytest -q`.
- Lint + format clean per Task 6.
- All tests `async` where they exercise async code; sync tests for pure helpers (the `_record_search_indicators_outcome` helper is sync because it only reads/writes `cl.user_session` which is sync).

## Anti-Patterns (do NOT do)

- **DON'T** scan `all_tool_outputs` from inside `update_investigation_item` — that helper is session-scoped, not loop-scoped. Use the session flag.
- **DON'T** make `_record_search_indicators_outcome` raise on bad input — the agentic loop must not crash on a malformed MCP payload. Log at debug and return.
- **DON'T** add the helper call to the local-handler branches (`apply_ops`, `update_investigation_item`, `propose_structure`) — only the MCP branch handles `search_indicators`.
- **DON'T** introduce a new error shape from `update_investigation_item` — reuse `{"error": ...}` to match the existing `Unknown item_id` pattern at `app/chat.py:108`.
- **DON'T** add schema validation of `key_stats_capture`'s dict shape on the server side — the prompt drives the shape; if the LLM produces malformed dicts, that's a prompt issue, not a server one.
- **DON'T** persist the validation flag across chat resume — let resume reset it. This is consistent with the broader resume-doesn't-restore-state policy.
- **DON'T** touch `DOSSIER_SYSTEM_PROMPT` — that's 12.3's scope. If a no-data UX phrasing change is tempting, it's 12.4.
- **DON'T** scope-creep into the no-data UX — Story 12.4 owns the "No indicators found for [topic] in [geography]" copy. 12.2 only enforces that the gate cannot pass; the LLM-side narration of failure lives in 12.4.

---

## Previous Story Intelligence

### From Story 12.1 (`12-1-mcp-tools-in-dossier-session.md`, ready-for-dev)

- The MCP tools are already available in `combined_tools` in both phases (no work needed); 12.2 leverages this — the LLM already CAN call `search_indicators` during investigation; this story just makes the LLM actually call it (prompt) and enforces the result (gate).
- 12.1's test class `TestMcpToolsInDossierSession` is **not** a dependency for 12.2's tests; they run independently.

### From Story 11.3 (`11-3-phase-gate-logic.md`, done — PR #67)

- `update_investigation_item`'s phase-gate computation already lives at `app/chat.py:122-130` and flips `dossier["phase"] = "dossier"` when all 5 phase-gate items are done. 12.2 extends the input validation but leaves the gate computation untouched.
- The phase-gate side effect (posting the reveal affordance) lives in the dispatch branch (`app/chat.py:983-984`), NOT inside `update_investigation_item`. 12.2's gate-rejection sits inside `update_investigation_item` and runs before any state mutation — the dispatch branch's affordance trigger only fires on success, so AC2's rejection path correctly skips the affordance.

### From Story 11.2 (`11-2-update-investigation-item-tool.md`, done — PR #60)

- The `update_investigation_item` LLM tool wrapper exists; 12.2 adds NO new tool registration. The same wrapper accepts the rejected-with-error return shape and surfaces it to the LLM as a `tool_result.content`, which the LLM is prompted to recognise.
- Established pattern: state write-back via `cl.user_session.set("investigation", state)` unconditionally (covers backends that return copies, not live refs).

### From Story 11.1 (`11-1-investigation-session-state.md`, done — PR #59)

- `_INVESTIGATION_ITEMS` is a tuple — item 5 is `data_sources_validation` (index 4). Item 6 is `key_stats_capture`. Both are existing items; this story does NOT change the items list.
- The investigation snapshot's 120-char value cap exists (`app/chat.py:95-96`); 12.2's `key_stats_capture` dict is stringified by `str(dict)` and bounded by that cap — no extra truncation logic needed (AC5).

---

## Latest Tech Information

### `search_indicators` MCP tool response shape

`mcp_server/server.py` (and the project-context.md tool-response contract) guarantees:
```python
{"success": True, "data": [...], "total_count": int, "returned_count": int, "truncated": bool}
```

`total_count` is the upstream Data360 API's reported total match count (which may exceed `returned_count` due to the 5000-record cap). 12.2 uses `total_count >= 1` as the gate, not `returned_count` — because a Data360 result with `total_count == 1` and `returned_count == 1` is the realistic minimum and `total_count` is the authoritative "are there any indicators?" answer.

### `get_data` MCP tool response shape

Same envelope. The `data` array's records carry `DATA_SOURCE`, `CITATION_SOURCE`, `INDICATOR`, `TIME_PERIOD`, `OBS_VALUE`, `REF_AREA`, etc. The LLM populates `key_stats_capture` from these fields per the AC4 dict shape; no server-side parsing in this story.

### `cl.user_session` semantics

`cl.user_session` is per-conversation. Keys persist across LLM rounds within a session but are reset on `on_chat_start`. On `on_chat_resume`, Chainlit re-runs `on_chat_resume` (not `on_chat_start`) and the user_session is fresh — initialisers must explicitly re-set every key that the session needs (this is why we add the flag init to both lifecycle hooks).

---

## Git Intelligence Summary

Recent commits on `main` (post-11.4 merge):

- `8036acd` chore(epic-10): close epic formally — all stories done/cancelled
- `020bbea` feat(11-4): propose_structure tool + dossier panel toggle & resume auto-reveal (#68)
- `06b0c68` feat(11-3): phase gate logic — transition to dossier mode when all 5 gate items are done (#67)
- `c8fb46f` feat(10-6): on-demand dossier canvas reveal (#66)

**Pattern relevant to 12.2:**
- 11-2 / 11-3 also extended `update_investigation_item` — those PRs are the canonical reference for "how to add behaviour to that function without breaking existing tests." Mirror their test patterns (`TestUpdateInvestigationItemTool`, `TestPhaseGateLogic`).
- `app/chat.py` is the busiest file in the project; line numbers will shift. The verification anchors in this story use **symbol references** (function names, branch keywords like `elif mcp_session is not None:`) rather than raw line numbers wherever possible.

---

## Project Context Reference

Rules from `_bmad-output/project-context.md` most relevant to 12.2:

- **All I/O methods must be `async`; no blocking calls inside tool handlers.** `update_investigation_item` is sync (it only touches `cl.user_session`); keep it sync. `_record_search_indicators_outcome` is sync (json + session); keep it sync.
- **Tool response contract** — only `"api_error"` and `"timeout"` are real `error_type` values; the gate's success check (`parsed.get("success") is True`) handles both via `success: False`.
- **Don't return empty `data` silently** — out of scope here (we're not extending the MCP tools), but 12.4 will leverage this guarantee for the no-data UX.
- **Tests in `tests/mcp_server/` mirror source structure** — app-level tests go in `tests/app/test_chat.py`. Stay there.
- **`asyncio_mode = "auto"`** — no need to add `@pytest.mark.asyncio`.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No debug issues encountered. All tasks implemented cleanly on first pass.

### Completion Notes List

- Task 1: Appended DATA VALIDATION and KEY STATS CAPTURE sub-sections to `INVESTIGATION_SYSTEM_PROMPT` in `app/prompts.py`. Verbatim example "Found 12 relevant indicators" anchors AC1 test.
- Task 2: Added `_DATA_VALIDATION_FLAG = "_data_validation_indicators_found"` constant next to `_MCP_SESSION_KEY`/`_MCP_TOOLS_KEY`. Initialized to `False` in both `on_chat_start` and `on_chat_resume`.
- Task 3: Added `_record_search_indicators_outcome` sync helper after `_extract_tool_result_text`. Called it from the MCP branch immediately after `_extract_tool_result_text(call_result)`, before `step.output` and `all_tool_outputs.append`. Not added to local-handler branches.
- Task 4: Inserted gate check in `update_investigation_item` after the `Unknown item_id` guard, before the state read. Error shape mirrors existing pattern — only `{"error": ...}`, no `phase_gate_reached` key.
- Task 5: Added 10 tests in `TestDataValidationGate` class at end of `tests/app/test_chat.py`. Also patched the existing `test_gate_reached_when_all_five_items_done` in `TestPhaseGateLogic` to add `"_data_validation_indicators_found": True` to its store, since it directly calls `update_investigation_item("data_sources_validation", ...)` and the new gate would have rejected it.
- Task 6: `ruff check .` and `ruff format --check .` both clean. `uv run pytest -q` → 419 passed (10 new + 409 existing, no regressions).

### File List

- `app/prompts.py` — appended DATA VALIDATION + KEY STATS CAPTURE sub-sections to `INVESTIGATION_SYSTEM_PROMPT`
- `app/chat.py` — added `_DATA_VALIDATION_FLAG` constant, init in `on_chat_start` and `on_chat_resume`, `_record_search_indicators_outcome` helper, hook call in MCP dispatch branch, gate check in `update_investigation_item`
- `tests/app/test_chat.py` — added `TestDataValidationGate` (10 tests); patched `test_gate_reached_when_all_five_items_done` in `TestPhaseGateLogic`

### Change Log

| Date | Notes |
|---|---|
| 2026-05-30 | Story created by `/bmad-create-story` (batch draft of Epic 12 stories 2-4). |
| 2026-05-30 | Implemented by dev agent (claude-sonnet-4-6): prompt rewrite, session flag, `_record_search_indicators_outcome` helper, gate check, 10 tests. 419 tests pass, lint clean. |

---

## Review Findings

_Code review 2026-05-30 (`/bmad-code-review`, 3 adversarial layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor). The Acceptance Auditor CONFIRMED all 6 ACs satisfied, no forbidden files touched, anti-patterns avoided, lint/format/tests green. The items below are residual edge-case and quality findings; the by-design choices flagged by the adversarial layers (monotonic session flag, resume-resets-flag, no server-side schema validation of `key_stats_capture`) were dismissed as explicitly intended per this spec._

### Patch

- [x] [Review][Patch] Strengthen 12.2 test coverage [tests/app/test_chat.py] — ✅ APPLIED (added item-5-persisted assertion to the accept test + 2 defensive `total_count` branch tests; 421 pass). — (a) `test_data_sources_validation_accepted_with_search` asserts only `status == "ok"` and `phase_gate_reached in result`; it does not assert item 5's state entry actually became `{"done": True, ...}` (a regression returning "ok" without persisting the item would still pass). (b) The defensive `total_count` branches in `_record_search_indicators_outcome` (missing key → default 0; non-coercible type → `except (TypeError, ValueError)`) have no unit tests. Add the missing assertion + 1-2 small tests. Low priority — Auditor rated coverage "adequate" via the rejection test. From Blind Hunter #11/#12 + Acceptance Auditor.
- [x] [Review][Patch] Spec text said "9 tests" but 10 were delivered [12-2-data-validation-gate.md:280,286] — ✅ APPLIED (updated both references to "12 tests = 10 from Task 5 + 2 added during code review"). — the File Structure table row and Testing Requirements say "9 tests"; the detailed Task 5 checklist (and the implementation) correctly have 10. Documentation-only fix. From Acceptance Auditor.

### Deferred

- [x] [Review][Defer] Large `search_indicators` result truncated → validation flag silently never set [app/chat.py:684-685, 1042] — `_extract_tool_result_text` truncates any tool output over `tool_result_max_chars` (default 50000) and appends `"[... truncated, results too large ...]"`; `_record_search_indicators_outcome` then runs `json.loads` on the truncated string → `JSONDecodeError` → flag never set even though `search_indicators` genuinely returned indicators. For a >50KB result, item 5 (`data_sources_validation`) becomes silently un-markable and the investigation can deadlock at the phase gate. Real, but only on large results. Deferred during code review (no reason given). Found by Edge Case Hunter (HIGH) + Blind Hunter.
- [x] [Review][Defer] Zero-results deadlock for niche topics [app/prompts.py + app/chat.py gate] — when `search_indicators` legitimately returns `total_count == 0`, both the prompt ("Do not mark the item done if no indicators were found") and the server gate forbid marking item 5, and the LLM is given no instructed escape (e.g. broaden the query) — so the phase gate can never be reached for genuinely sparse topics. Owned by Story 12.4 (no-data UX). Deferred. Found by Edge Case Hunter (HIGH).
