# Story 12.1: MCP Tools in Dossier Session

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want the existing MCP tools to be callable during the dossier investigation,
So that the LLM can validate real data before building the document.

> **Verification-first story.** Static analysis shows the production wiring (`combined_tools = list(tools)` at `app/chat.py:900` and the `elif mcp_session is not None:` dispatch branch at `app/chat.py:1001-1015`) **already satisfies both ACs**. This story locks the contract in with explicit phase-aware tests so a future refactor (e.g., making the tool list phase-conditional, or splitting the dispatch loop) cannot silently regress Stories 12.2–12.4. Do NOT modify the wiring unless an AC fails — add tests first.

---

## Acceptance Criteria

**AC1: All five MCP tools are available in the dossier-session tool list, in both `investigating` and `dossier` phases.**
**Given** `mcp_session` is connected and `cl.user_session["mcp_tools"]` contains the 5 MCP tools — `search_indicators`, `get_data`, `get_metadata`, `list_indicators`, `get_disaggregation` — produced by `_mcp_tools_to_anthropic(result.tools)` at `app/chat.py:738` (on chat start) and `:781` (on chat resume)
**When** `_build_call_kwargs()` (`app/chat.py:881`) assembles `combined_tools`
**Then** every one of those 5 tool names is present in the resulting `tools` list that gets passed to `client.messages.stream(...)`
**And** this holds when `cl.user_session["dossier"]["phase"] == "investigating"`
**And** this holds when `cl.user_session["dossier"]["phase"] == "dossier"`

**AC2: An MCP tool call routes through `mcp_session.call_tool` and its output is appended to `all_tool_outputs` — uniformly in both phases.**
**Given** the LLM returns a `tool_use` block whose `name` is one of the 5 MCP tools
**When** the agentic-loop dispatch (`app/chat.py:956-1015`) processes that block
**Then** the `elif mcp_session is not None:` branch (`app/chat.py:1001`) is taken — NOT the `apply_ops` / `update_investigation_item` / `propose_structure` branches
**And** `mcp_session.call_tool(tool_name, arguments=tool_input)` is awaited with the LLM-supplied input
**And** the result is converted via `_extract_tool_result_text(call_result)` and assigned to `tool_output`
**And** `all_tool_outputs.append(tool_output)` is called (`app/chat.py:1015`)
**And** a `tool_result` block carrying `tool_output` is appended to history (`app/chat.py:1017-1024`)
**And** the same routing + collection behaviour holds when phase is `investigating` AND when phase is `dossier`

**AC3: When `mcp_session is None` (MCP unavailable), an MCP tool call surfaces the existing "MCP server is not connected" error string instead of crashing.**
**Given** `mcp_session is None` (auto-connect failed; see `app/chat.py:818-820` warning path)
**When** the LLM (somehow) emits a `tool_use` for an MCP tool name
**Then** the `else:` branch at `app/chat.py:1008-1012` produces `tool_output = "Error: MCP server is not connected. Cannot call tool '<name>'. The Data360 API is currently unavailable."`
**And** the loop does not crash — the error string is appended to `all_tool_outputs` and returned to the model as a `tool_result` so the LLM can narrate the failure

---

## Tasks / Subtasks

### Task 1: Add an explicit test class for the dossier-session MCP tool contract (AC: 1, 2, 3)

- [ ] Add a new test class `TestMcpToolsInDossierSession` to `tests/app/test_chat.py`, after `TestProposeStructureTool` (file currently ends with `TestToggleDossier` around line 3077+; place the new class adjacent to other phase-aware tool tests).
  - [ ] Use `@pytest.mark.usefixtures("set_required_env_vars")` and the existing `reload_chat` fixture pattern (see `TestProposeStructureTool` for the exact shape).
  - [ ] Pull the canonical tool list into a module-level test constant `_EPIC_1_MCP_TOOLS = ("search_indicators", "get_data", "get_metadata", "list_indicators", "get_disaggregation")` at the top of the new class, mirroring the AC text verbatim.

- [ ] **AC1 / investigating phase** — `test_all_mcp_tools_present_in_investigating_phase`:
  - [ ] Build `tools = [{"name": n, "description": "x", "input_schema": {"type": "object"}} for n in _EPIC_1_MCP_TOOLS]`.
  - [ ] Capture `kwargs` via the existing `fake_stream` pattern (see `test_propose_structure_registered_in_dossier_phase` at `tests/app/test_chat.py:3024-3049` for the exact captured-kwargs idiom).
  - [ ] Patch `cl.user_session` with `_make_session_mock_with_history()` (defaults to `dossier={"phase": "investigating"}`).
  - [ ] Send an `on_message` whose content is anything (e.g., `"hello"`).
  - [ ] Assert: `passed_names = [t["name"] for t in captured_kwargs["tools"]]` and `set(_EPIC_1_MCP_TOOLS).issubset(set(passed_names))`.

- [ ] **AC1 / dossier phase** — `test_all_mcp_tools_present_in_dossier_phase`:
  - [ ] Same setup, but `_make_session_mock_with_history(dossier={"phase": "dossier"}, doc=doc_mock)` with `doc_mock.props = {"content": "", "version": 0}` (the dossier branch reads doc props for the system-prompt snapshot — see `app/chat.py:887-890`).
  - [ ] Assert all 5 tool names are present **and** the dossier-phase tools (`apply_ops`, `propose_structure`) are also present (regression guard so this test fails loudly if the dossier branch ever filters MCP tools).

- [ ] **AC2 / investigating phase dispatch** — `test_mcp_tool_call_in_investigating_phase_routes_via_mcp_session`:
  - [ ] Build a tool_use block with `name="search_indicators"`, `input={"query": "deforestation"}`, `id="toolu_si_01"`.
  - [ ] Two streams: first stops on `tool_use`, second on `end_turn` (follow the `test_dispatch_calls_propose_structure_handler` pattern — `tests/app/test_chat.py:3024+`).
  - [ ] Build `mcp_session = AsyncMock()` and configure `mcp_session.call_tool.return_value` to return an MCP `CallToolResult`-like object whose text content equals `"OK_MCP_RESULT"` (use `_make_fake_mcp_result` if present — search `tests/app/test_chat.py` for existing helpers; otherwise inline a `MagicMock` with `.content = [MagicMock(text="OK_MCP_RESULT")]` and patch `_extract_tool_result_text` to return `"OK_MCP_RESULT"`).
  - [ ] Patch `app.chat.cl.user_session` with `_make_session_mock_with_history()` (investigating phase).
  - [ ] **Inject** the `mcp_session` mock into the session under `_MCP_SESSION_KEY` (`"mcp_session"`) so `on_message` reads it at `app/chat.py:840`.
  - [ ] After `await reload_chat.on_message(...)`, assert: `mcp_session.call_tool.assert_awaited_once_with("search_indicators", arguments={"query": "deforestation"})`.
  - [ ] Assert the tool_result content in the second captured stream call equals `"OK_MCP_RESULT"` (lift the `tool_results` extraction idiom from `test_dispatch_calls_propose_structure_handler`).

- [ ] **AC2 / dossier phase dispatch** — `test_mcp_tool_call_in_dossier_phase_routes_via_mcp_session`:
  - [ ] Identical to the investigating-phase test except the session uses `dossier={"phase": "dossier"}` with a `doc_mock`, and the tool name is `get_data` (different MCP tool to broaden coverage).
  - [ ] Assert the same dispatch + collection behaviour.

- [ ] **AC3 / MCP unavailable** — `test_mcp_tool_call_with_no_session_returns_error_string`:
  - [ ] Same fake-stream / tool_use setup, but DO NOT set `_MCP_SESSION_KEY` in the session (so `mcp_session is None` at `app/chat.py:840`).
  - [ ] After `on_message`, assert the captured second stream call's `tool_result` content contains the literal substring `"Error: MCP server is not connected"` and `"search_indicators"` (substring is fine; do not anchor to the full string to keep the test resilient to copy edits in the message).

### Task 2: Confirm — no production code changes

- [ ] Verify by static reading (NOT by running the diff) that:
  - [ ] `app/chat.py:900` still reads `combined_tools = list(tools)` (unconditional).
  - [ ] `app/chat.py:902-904` is the only `if phase == "dossier":` block in `_build_call_kwargs`, and it only **appends** dossier-only tools — it does not filter `tools`.
  - [ ] `app/chat.py:1001-1007` is the `elif mcp_session is not None:` branch and is reachable when `tool_name` matches an MCP tool (i.e., it sits after the three handler-specific `elif`s for `apply_ops` / `update_investigation_item` / `propose_structure` and before the bare `else:`).
- [ ] If any of the above is no longer true, STOP and surface the deviation to the user before adding tests — the wiring has regressed and AC1/AC2 must be re-evaluated.

### Task 3: Lint, format, full test suite (AC: 1, 2, 3)

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pytest -q` — expect the prior baseline + the 5 new tests added in Task 1.

---

## Dev Notes

### What this story is (and is not)

**Is:**
- An explicit, phase-aware **test contract** for the dossier-session MCP tool surface (AC1) and the dispatch-loop routing/collection contract (AC2).
- A regression guard for the MCP-unavailable error path (AC3).
- A documentation anchor that downstream stories (12.2 data-validation gate, 12.3 citation flow, 12.4 no-data handling) can reference instead of re-deriving the wiring.

**Is not:**
- Any change to `_build_call_kwargs` — the existing `combined_tools = list(tools)` line is what the AC requires. **Touching it risks breaking 11.x and Epic 1.**
- Any change to the dispatch loop or `_extract_tool_result_text`.
- Any change to `INVESTIGATION_SYSTEM_PROMPT` or `DOSSIER_SYSTEM_PROMPT` — instructing the LLM **when** to call which MCP tool is Story 12.2's job (data-validation gate logic) and 12.3's (citation flow into sections). 12.1 only proves the tools are *available* and *dispatchable*.
- Any new MCP tool definitions or registrations — Epic 1 already shipped the 5 tools.
- Any RAG-specific coverage. When `DATA360_RAG_ENABLED=true`, the MCP server adds `search_documents` / `list_documents` to `result.tools`; they ride through the same `_mcp_tools_to_anthropic` transform and become available transparently. The AC names exactly the 5 Epic-1 tools — tests cover those 5 only. RAG tool coverage lives with Epic 8.

### Why this is a verification + test-lock-in story (no production code change)

The production wiring already satisfies AC1 and AC2:

- **AC1 (tool availability):** `_build_call_kwargs` at `app/chat.py:881-910` builds `combined_tools` from `list(tools)` (line 900) **before** the `if phase == "dossier":` branch (line 902). `tools` is the snapshot of `_mcp_tools_to_anthropic(result.tools)` stored in `cl.user_session[_MCP_TOOLS_KEY]` at chat-start (`app/chat.py:738`) and on resume (`app/chat.py:781`). The 5 Epic-1 MCP tools therefore appear in `combined_tools` in BOTH phases. The dossier phase ADDS `apply_ops` + `propose_structure`; it does not subtract MCP tools.
- **AC2 (dispatch + collection):** The agentic loop iterates `tool_use` blocks at `app/chat.py:956-1015`. Three `elif`s handle the local tools (`apply_ops` line 974, `update_investigation_item` line 980, `propose_structure` line 996). MCP tools fall through to `elif mcp_session is not None:` at line 1001, which awaits `mcp_session.call_tool(...)`, extracts text, and assigns `tool_output`. Line 1015 — `all_tool_outputs.append(tool_output)` — sits inside the `cl.Step` block and runs for every branch including MCP. Line 1017-1024 then appends the `tool_result` to `history`. Same path in both phases.
- **AC3 (no-session graceful failure):** Line 1008-1012's `else:` returns a structured error string without raising; the loop continues and the LLM receives a narratable error in the next round.

Because the wiring is correct today, **changes to `_build_call_kwargs` or the dispatch loop are out of scope**. The risk this story addresses is *future regression*: someone adds an `if phase != "dossier":` filter to keep MCP tools out of the dossier phase, or splits the dispatch loop and forgets to call `all_tool_outputs.append` in one branch. The new tests fail loudly in either case.

### Existing wiring anchors (verified 2026-05-30 against `app/chat.py`)

| What | File:Line | Notes |
|---|---|---|
| MCP discovery on chat start | `app/chat.py:738` | `result = await session.list_tools()` |
| MCP discovery on resume | `app/chat.py:781` | same call, resume path |
| MCP→Anthropic tool format | `app/chat.py:_mcp_tools_to_anthropic` | converts `result.tools` to the `[{"name", "description", "input_schema"}, …]` shape Claude expects |
| Per-session MCP cache | `cl.user_session[_MCP_TOOLS_KEY]` = `"mcp_tools"` | stored at chat start (`app/chat.py:739`) and resume (`app/chat.py:782`); read back when `on_message` calls `_agentic_loop(loop_history, tools, mcp_session, msg)` at `app/chat.py:850` |
| Per-session MCP session | `cl.user_session[_MCP_SESSION_KEY]` = `"mcp_session"` | stored alongside tools; read at `app/chat.py:840` |
| Tool list assembly | `app/chat.py:881-910` (`_build_call_kwargs`) | unconditional `combined_tools = list(tools)` at line 900 |
| MCP dispatch branch | `app/chat.py:1001-1007` | `elif mcp_session is not None:` |
| MCP-unavailable branch | `app/chat.py:1008-1012` | bare `else:`, returns error string |
| Output collection | `app/chat.py:1015` | `all_tool_outputs.append(tool_output)` inside the `cl.Step` block, runs for every branch |
| Tool-result history append | `app/chat.py:1017-1024` | builds the `{"type": "tool_result", "tool_use_id", "content"}` block |

### Test patterns to follow (do NOT reinvent)

- `_make_session_mock_with_history(dossier=…, doc=…)` — session-mock factory used throughout `TestProposeStructureTool` / `TestApplyOps…` / `TestPhaseGateLogic`. Default phase is `investigating`; pass `dossier={"phase": "dossier"}` to flip.
- `_make_fake_content_block("tool_use", name=…, input=…, id=…)` — builds Anthropic tool_use blocks for tests.
- `FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[…])` — fake of `client.messages.stream`. The captured-kwargs idiom for assertion lives at `tests/app/test_chat.py:3024-3046` (`test_propose_structure_registered_in_dossier_phase`).
- Tool-result extraction idiom (added by Story 11.4, P6 patch — `tests/app/test_chat.py:3030+` after `test_dispatch_calls_propose_structure_handler`):
  ```python
  tool_results = [
      block
      for message in captured_calls[1]["messages"]
      if isinstance(message.get("content"), list)
      for block in message["content"]
      if isinstance(block, dict) and block.get("type") == "tool_result"
  ]
  assert any(tr.get("content") == "OK_MCP_RESULT" for tr in tool_results)
  ```
- For the `mcp_session.call_tool` mock: see `TestMcpToolUse` at `tests/app/test_chat.py:433+` for the existing pattern (look for `fake_mcp_session.call_tool.assert_awaited_once_with(...)` at line 675).
- For `_extract_tool_result_text`: see how it's invoked at `app/chat.py:1004`; if the existing tests mock it or patch it, reuse that approach rather than constructing a real `CallToolResult`.

### Design decision: why the test asserts `set.issubset` instead of equality

`combined_tools` in dossier phase ALSO contains `UPDATE_INVESTIGATION_ITEM_TOOL` (always, see `app/chat.py:901`), `APPLY_OPS_TOOL`, and `PROPOSE_STRUCTURE_TOOL`. Tests use `set(_EPIC_1_MCP_TOOLS).issubset(set(passed_names))` so they don't break when future epics add more tools to the list (Epic 13's section-add/remove tool would otherwise force a test update). The dossier-phase test ALSO explicitly asserts `apply_ops` and `propose_structure` are present, so a regression that drops them would still be caught.

### Existing helpers this story reuses (do NOT reinvent)

- `_make_session_mock_with_history` (`tests/app/test_chat.py`) — session mock with history pre-loaded.
- `_make_fake_content_block` (`tests/app/test_chat.py`) — Anthropic content-block factory.
- `FakeStream` (`tests/app/test_chat.py`) — fake of `client.messages.stream`.
- `_mcp_tools_to_anthropic` (`app/chat.py`) — MCP tool → Anthropic tool dict converter (already tested by `test_mcp_tools_to_anthropic_format` at `tests/app/test_chat.py:847`; do NOT add another conversion test).
- `_extract_tool_result_text` (`app/chat.py`) — MCP result → text extractor (exists; reuse as-is, don't re-mock its internals).

### Dispatch + registration anchors (verified)

- `_build_call_kwargs`: `app/chat.py:881`, returns `dict[str, Any]` with `tools` key.
- Agentic-loop iteration over tool_use blocks: `app/chat.py:956`.
- Local handler branches in order: `apply_ops` (`:974`), `update_investigation_item` (`:980`), `propose_structure` (`:996`).
- MCP branch: `app/chat.py:1001` (`elif mcp_session is not None:`).
- No-MCP branch: `app/chat.py:1008` (`else:`).
- Output collection: `app/chat.py:1015`.

### Tool-result contract note

`mcp_session.call_tool(...)` returns an MCP `CallToolResult`. `_extract_tool_result_text` flattens it to a plain string (the same string the LLM sees as `tool_result.content`). Tests should patch the call boundary, not the internals — pass a mock result whose extracted text is predictable, OR patch `_extract_tool_result_text` directly. The simpler path is usually patching `_extract_tool_result_text` to return a constant.

### Deferred-work connection

- This story does **not** address: prompt updates that tell the LLM *when* to call which MCP tool during investigation (12.2) or how to wire `DATA_SOURCE` into `apply_ops` content (12.3). Those land in their own stories.
- This story does **not** address: persistence of MCP tool outputs across chat resume — currently `_MCP_TOOLS_KEY` is re-populated on resume by re-running `session.list_tools()` (`app/chat.py:781`), not restored from the persisted thread. Out of scope; tracked nowhere.

---

## Project Structure Notes

- The only file under change is `tests/app/test_chat.py`. No source-tree shift, no new modules, no new dependencies.
- Test class placement: after `TestProposeStructureTool` and before/after `TestToggleDossier` is fine — group with the phase-aware tool tests cluster (anchor lookup: search for `class TestProposeStructureTool` and add the new class adjacent to it).
- Test fixture conventions: follow the `reload_chat` + `set_required_env_vars` pattern that Stories 11.1–11.4 cemented. Do not introduce new fixtures.

## File Structure Requirements

| File | Status | Purpose |
|---|---|---|
| `tests/app/test_chat.py` | UPDATE | Add `TestMcpToolsInDossierSession` class with the 5 tests enumerated in Task 1 |
| `app/chat.py` | READ-ONLY (verify, do NOT modify) | Verification anchors per Task 2 |
| `app/prompts.py` | READ-ONLY (no change in 12.1) | Prompt content updates are 12.2/12.3 scope |
| `mcp_server/server.py` | READ-ONLY (no change in 12.1) | The 5 tools are already registered (Epic 1) |

**Files this story must NOT touch:** `app/chat.py`, `app/prompts.py`, `mcp_server/**`, `public/**`, `_bmad-output/planning-artifacts/**`. If any of these need changes to make a test pass, the wiring has regressed — escalate per Task 2 instead of patching.

## Testing Requirements

- 5 new tests in `tests/app/test_chat.py` (Task 1).
- Existing test suite (404 tests as of 2026-05-30, post-11.4) must remain green: `uv run pytest -q`.
- Lint + format clean per Task 3.
- Test class name: `TestMcpToolsInDossierSession`. Test names exactly as enumerated in Task 1 (used as the discoverable contract).
- All tests `async` (project uses `asyncio_mode = "auto"`; `@pytest.mark.asyncio` is redundant — do not add it).
- Mock `client.messages.stream` via the `FakeStream` pattern; do NOT make real Anthropic API calls.
- Mock `mcp_session.call_tool` via `AsyncMock`; do NOT make real MCP calls.

## Anti-Patterns (do NOT do)

- **DON'T** add an `if phase == "investigating":` (or `!= "dossier":`) filter around `combined_tools = list(tools)` to "scope" MCP tools to investigation — the dossier-phase LLM needs them for data lookups (per `DOSSIER_SYSTEM_PROMPT` DATA RULES, `app/prompts.py:151-154`).
- **DON'T** add prompt copy in 12.1 — instructing the LLM *when* to call MCP tools is 12.2's contract.
- **DON'T** assert exact equality of `combined_tools` against a hardcoded list — use `set.issubset` so future tool additions don't break this test.
- **DON'T** add the 5 tools to a static module-level constant in `app/chat.py` — they come from MCP dynamically; hardcoding would duplicate the source of truth and rot the moment Epic 1 ships a 6th tool.
- **DON'T** mock `_mcp_tools_to_anthropic`'s output shape from scratch — use the existing test pattern at `tests/app/test_chat.py:847` (`test_mcp_tools_to_anthropic_format`) as the reference for the dict shape (`{"name", "description", "input_schema"}`).
- **DON'T** construct real `CallToolResult` instances — mock the call boundary.
- **DON'T** rely on patching private attributes — patch at the module boundary (`app.chat.cl.user_session`, `app.chat.client.messages.stream`, `app.chat._extract_tool_result_text`).
- **DON'T** test things 12.2 owns: this story does NOT exercise the data-validation gate (item 5 transition), search-result rendering in chat, or no-data UX. Those are 12.2/12.4's ACs.

---

## Previous Story Intelligence

### From Story 11.4 (`11-4-propose-structure-tool.md`, done — PR #68 merged 2026-05-30)

- **Captured-kwargs assertion idiom is the canonical way** to inspect tool registration: capture `kwargs` from `fake_stream(**kwargs)` into a list and read `kwargs["tools"]`. See `test_propose_structure_registered_in_dossier_phase` (`tests/app/test_chat.py:3024+`) for the exact pattern.
- **Tool-result extraction idiom for AC2-style dispatch tests** lives in `test_dispatch_calls_propose_structure_handler` (`tests/app/test_chat.py:3030+`, added by the 11.4 P6 patch). Reuse it verbatim.
- **`_make_session_mock_with_history` defaults are investigating phase**; pass `dossier={"phase": "dossier"}` explicitly for dossier-phase tests and include a `doc_mock` so the dossier branch's `doc.props` reads at `app/chat.py:887-890` don't `AttributeError`.
- **`UPDATE_INVESTIGATION_ITEM_TOOL` is unconditional in `combined_tools`** (`app/chat.py:901`) — your dossier-phase assertion includes more than just the dossier-only tools. Use `set.issubset` for MCP-tool checks; explicit `in` checks for dossier-only tools.

### From Story 11.3 (`11-3-phase-gate-logic.md`, done — PR #67)

- Phase transitions `investigating` → `dossier` via `update_investigation_item` when checklist items 1–5 are all done; tests can simulate either phase by setting `cl.user_session["dossier"] = {"phase": "..."}` directly.
- The `post_dossier_reveal_affordance` is a chat-side action, NOT a tool — irrelevant for 12.1's tool-list assertions.

### From Story 10.6 (`10-6-on-demand-dossier-canvas-reveal.md`, done — PR #66)

- The `doc` is lazily created via `ensure_dossier_doc()` only when the dossier phase needs it. Dossier-phase tests therefore need a `doc_mock` in the session for the system-prompt-snapshot read (`app/chat.py:887-890`) to succeed.

### From Story 1.x (Epic 1: MCP Server)

- The 5 MCP tools are registered in `mcp_server/server.py` via `@mcp.tool()` decorators. They are discoverable through `session.list_tools()` and converted by `_mcp_tools_to_anthropic` into the Anthropic dict format. **None of this needs to be re-tested in 12.1** — Epic 1's test suite already covers it.

---

## Latest Tech Information

### `cl.user_session` keys touched

`_MCP_SESSION_KEY = "mcp_session"` and `_MCP_TOOLS_KEY = "mcp_tools"` (`app/chat.py:626`-ish — search exact line). When patching `cl.user_session` in tests, populate these alongside `dossier` and `doc` so `on_message` finds them at `:840` and `_agentic_loop` receives the right `tools`.

### Anthropic tool dict shape

```python
{"name": "search_indicators", "description": "<from MCP tool description>", "input_schema": {"type": "object", "properties": {...}}}
```

The MCP tool's `inputSchema` field maps to Anthropic's `input_schema` (note the underscore vs camelCase difference handled inside `_mcp_tools_to_anthropic`). Do NOT re-test this shape — it's covered at `tests/app/test_chat.py:847`.

### `cl.Step(name=f"🔧 {tool_name}", type="tool")` is wrapped around the dispatch

Output collection (`all_tool_outputs.append`) happens **inside** the step's `async with` block (`app/chat.py:954-1015`). Mocks for `cl.Step` must support `__aenter__` / `__aexit__` — see the pattern at `tests/app/test_chat.py:3008-3012` (`step_mock = AsyncMock(); step_mock.__aenter__ = AsyncMock(return_value=step_mock); step_mock.__aexit__ = AsyncMock(return_value=False)`).

---

## Git Intelligence Summary

Recent commits on `main` (post-11.4 merge 2026-05-30):

- `8036acd` chore(epic-10): close epic formally — all stories done/cancelled
- `020bbea` feat(11-4): propose_structure tool + dossier panel toggle & resume auto-reveal (#68)
- `06b0c68` feat(11-3): phase gate logic — transition to dossier mode when all 5 gate items are done (#67)
- `c8fb46f` feat(10-6): on-demand dossier canvas reveal (#66)
- `0f501f7` fix: dossier panel content stale, reopen button dead, tools button missing (#61)
- `eef7761` feat(11-2): update_investigation_item LLM tool (#60)
- `078fe57` feat(11-1): investigation session state foundation (#59)

**Pattern observations relevant to 12.1:**
- All recent dossier-track stories follow the same test idiom (`reload_chat` fixture, `_make_session_mock_with_history`, `FakeStream`). The Epic-12 stories should keep that consistency.
- `app/chat.py` line numbers shift frequently as stories add code. The Task 2 verification step uses **anchor symbols** (`combined_tools = list(tools)`, `elif mcp_session is not None:`) rather than raw line numbers so the verification stays robust across rebases.

---

## Project Context Reference

This story is implemented under the rules captured in `_bmad-output/project-context.md`. Most-relevant rules for 12.1:

- **All I/O methods must be `async`; no blocking calls inside tool handlers.** (Tests are async.)
- **Type hints required on all function signatures; use `dict[str, Any]` not `Dict`.**
- **Tests in `tests/mcp_server/` mirror source structure; `tests/app/` for app tests.** This story extends `tests/app/test_chat.py`.
- **`asyncio_mode = "auto"` in pyproject.toml — `@pytest.mark.asyncio` is redundant but acceptable.** Prefer omitting it.
- **Group tests in classes: `class TestToolName:` with docstrings referencing AC numbers (e.g., `"""AC1: ..."""`).** Follow this convention for the new class.
- **Always preserve real `_map_params` on mocks so param mapping assertions work** — not relevant here (no `_map_params` involved), but a general project mocking caution.
- **`CITATION_SOURCE` enrichment / `DATA_SOURCE` integrity** — out of scope for 12.1; 12.3 owns that flow.
- **Citations are pipeline-guaranteed; the LLM only places `[n]` markers** — out of scope for 12.1.

---

## Dev Agent Record

### Agent Model Used

_To be filled by the dev agent._

### Debug Log References

_To be filled by the dev agent._

### Completion Notes List

_To be filled by the dev agent._

### File List

_To be filled by the dev agent._

### Change Log

| Date | Notes |
|---|---|
| 2026-05-30 | Story created by `/bmad-create-story` (post-11.4 merge to main; sprint-status flips epic-12 → in-progress). |
