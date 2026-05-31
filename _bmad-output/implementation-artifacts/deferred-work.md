# Deferred Work

## Deferred from: code review of 12-4-no-data-handling-in-investigation (2026-05-30)

_Surfaced while reviewing 12.4 (scope: `app/prompts.py` + `tests/app/test_chat.py`). The items
below are 12.2/12.3-owned (those stories are already `done`), not regressions introduced by 12.4.
12.4's own ACs all passed; its only findings are optional test-hardening tracked in the story file._

- **[12.3] DOSSIER prompt overstates Methodology auto-overwrite (MEDIUM):** `DOSSIER_SYSTEM_PROMPT`
  (`app/prompts.py:194-195`) tells the LLM its edits to `## Methodology and Sources` "will be
  overwritten on the next round", but `_sync_dossier_references_section` only runs on rounds with
  citation-bearing refs. On a no-citation round the LLM's hand-edits to that section persist,
  contradicting the directive. Fix is ambiguous (soften the prompt wording vs. always sync in
  `app/chat.py`) — needs a decision; deferred rather than patched. Found by Edge Case Hunter.

- **[12.3] DOSSIER inline-citation worked example self-contradicts (LOW):** the example at
  `app/prompts.py:186` pairs a water-stress claim ("Water stress risk in 129 municipalities") with
  `WB_WDI_EG_ELC_ACCS_ZS` (the *access-to-electricity* code). Teaches the citation format with a
  mismatched fact/indicator. Trivial fix; left to the 12.3 owner. Found by Blind Hunter.

- **[12.3] `_sync_dossier_references_section` robustness (LOW/latent, `app/chat.py` — out of scope):**
  with `refs=[]` the helper writes an empty Methodology body and bumps the version (only the
  `if raw_refs:` call-site guard prevents this today; untested). Separately, markdown headings inside
  fenced code blocks can false-match the line-anchored `_METHODOLOGY_HEADING_RE`. Found by Edge Case Hunter.

- **[12.3] Mis-named round-finalisation test (LOW):** `test_round_finalisation_skips_dossier_sync_when_no_refs`
  exercises the "no tool calls" path, not the "tools called but no `CITATION_SOURCE`" path its name
  implies; the latter (`extract_references` returns `[]`) is uncovered. Found by Edge Case Hunter.

## Deferred from: code review of 12-2-data-validation-gate (2026-05-30)

- **[12-2] Large `search_indicators` result truncated → validation flag silently never set** (`app/chat.py:684-685, 1042`) — `_extract_tool_result_text` truncates any tool output over `tool_result_max_chars` (default 50000) and appends `"[... truncated, results too large ...]"`. `_record_search_indicators_outcome` then runs `json.loads` on that truncated string → `JSONDecodeError` → the indicators-found flag is never set even though `search_indicators` genuinely returned indicators. Net effect: a >50KB result makes item 5 (`data_sources_validation`) silently un-markable and the investigation can deadlock at the phase gate. Real, but only on large (>50KB) results. Fix when touched: record the outcome from the un-truncated joined text inside the MCP branch before `_extract_tool_result_text` truncates (or have the recorder operate on `call_result.content` directly). Deferred during code review (no reason given). Found by Edge Case Hunter (HIGH) + Blind Hunter. — ✅ **RESOLVED 2026-05-31** (surfaced during Epic 12 UI testing): extracted `_join_tool_result_text(call_result)` (untruncated join); `_extract_tool_result_text` now delegates to it then truncates for the model; the MCP dispatch branch feeds `_record_search_indicators_outcome` the un-truncated text. 2 regression tests added (`test_join_tool_result_text_does_not_truncate_large_success`, `test_dispatch_loop_sets_flag_for_large_search_result`); before/after proof: OLD flag=False → NEW flag=True on a 183KB payload. 436 tests pass, lint+format clean.
- **[12-2] Zero-results deadlock for niche topics** (`app/prompts.py` DATA VALIDATION block + `app/chat.py` `update_investigation_item` gate) — when `search_indicators` legitimately returns `total_count == 0`, both the prompt ("Do not mark the item done if no indicators were found") and the server gate reject marking item 5 (`data_sources_validation`), and the LLM has no instructed escape (e.g. broaden the query or record "no data" explicitly). For a genuinely sparse topic the investigation can never reach the phase gate. **Owned by Story 12.4** (no-data UX): 12.4 should add the "No indicators found for [topic] in [geography]…" copy AND an LLM-side path that lets the journalist proceed or re-scope when zero indicators exist. Found by Edge Case Hunter (HIGH).

## Deferred from: code review of 12-1-mcp-tools-in-dossier-session (2026-05-30)

- **[12-1] MCP error-path branches untested by the 12.1 test class** (`app/chat.py:1005-1012`) — the `except Exception` wrapper around `mcp_session.call_tool` (chat.py:1005-1007) has no coverage in `TestMcpToolsInDossierSession`, and the no-session test (`test_mcp_tool_call_with_no_session_returns_error_string`) asserts the "MCP server is not connected" string but does not prove it came from the specific no-session branch rather than a generic catch-all. The `isError=True` extractor branch is covered elsewhere (`TestMcpToolUse.test_mcp_tool_error_passed_to_claude`). Error/no-data handling is Story 12.4's contract — fold phase-aware error-path tests in there.
- **[12-1] Multiple MCP `tool_use` blocks in a single assistant turn never exercised** (`app/chat.py:963-1023`) — every 12.1 routing test emits exactly one `tool_use` block. A single turn emitting two MCP tool calls (e.g. `search_indicators` + `get_data`) is not asserted to await `call_tool` twice and emit two `tool_result` blocks. General agentic-loop behavior beyond 12.1's availability/routing contract.
- **[12-1] Dossier phase with `doc is None` untested** (`app/chat.py:887-889`) — both dossier-phase tests supply a `doc_mock`; the valid state where the phase flips to `dossier` before `ensure_dossier_doc()` runs (so `doc is None`) is never exercised. A regression to an unconditional `doc.props.get(...)` would `AttributeError` in prod but pass these tests. `_build_call_kwargs` robustness inherited from Epic 10/11.

## Deferred from: code review of 11-4-propose-structure-tool (2026-05-25)

- **[11-4] `on_chat_resume` iterates `thread.get("steps", [])` unguarded** (`app/chat.py:674,696`) — returns `None` if the `steps` key is present-but-null, and a non-dict step element would crash `step.get(...)`. Pre-existing: the loop at line 675 already iterates the same `steps`, so this is not introduced by Story 11.4. Fix when touched: `steps = thread.get("steps") or []` and filter `isinstance(step, dict)`.

## Deferred from: code review of 11-3-phase-gate-logic (2026-05-25)

- **[11-3] `on_chat_resume` resets `dossier["phase"]` to `"investigating"` unconditionally** (`app/chat.py:583`) — gate can never re-trigger after browser reload; user who reached phase gate before closing tab resumes as if in investigation phase with empty checklist. Pre-existing from Stories 11.1/11.2.
- **[11-3] `update_investigation_item` error dict omits `phase_gate_reached` key** (`app/chat.py:108`) — when LLM sends unknown `item_id`, returned `{"error": "..."}` has no `phase_gate_reached`; dispatch reads `None` (falsy) which is safe but LLM receives ambiguous feedback. Pre-existing from Story 11.2.
- **[11-3] `test_dispatch_no_affordance_when_already_dossier` does not assert serialized `tool_output` contains `"phase_gate_reached": true`** (`tests/app/test_chat.py`) — AC4 specifies this return value; implicitly verified through mock setup but not explicitly asserted. Low value given the clear code path.

## Deferred from: code review of 11-1-investigation-session-state (2026-05-23)

- **[11-1] `phase_gate_reached` hardcoded `False` in `update_investigation_item`** (`app/chat.py`) — by-design stub from Story 11.1; returns `False` even when all 10 items are done. Now user-reachable because the Story 11.2 tool wrapper is live in HEAD, so the model receives a misleading `phase_gate_reached: False` on every call. **Owned by Story 11.3** (rewritten 2026-05-23 to compute the real gate on items 1-5 and return `True`). No action needed in 11.1.

## Deferred from: code review of 11-2-update-investigation-item-tool (2026-05-13)

- **[11-2] `update_investigation_item` helper mutates session dict in-place without `cl.user_session.set` on normal path** (`app/chat.py:137`) — pre-existing Story 11.1 design; if Chainlit ever returns a copy instead of a reference from `.get()`, the mutation is silently lost. Fix: add `cl.user_session.set("investigation", state)` after line 137 unconditionally. — ✅ **RESOLVED 2026-05-23** via the Story 11.1 code review (P1): unconditional write-back added.

- **[11-2] Pre-dispatch `json.dumps(tool_input, indent=2)` not in try/except** (`app/chat.py:805`) — pre-existing agentic loop vulnerability; if any MCP tool deserializes a non-serialisable Python object into `tool_input`, this raises before the per-tool dispatch block. Shared exposure with `apply_ops` and MCP path. Fix: wrap in try/except or validate tool_input before logging.

- **[11-2] No per-phase enforcement of legal `item_id` values** (`app/chat.py:816`) — LLM can call `update_investigation_item` with a phase-1 item in dossier phase (or vice-versa), silently overwriting a captured answer. Story 11.3 is the natural place to add phase-aware validation if overwrite protection is needed.

- **[11-2] No investigation snapshot injected in dossier phase** (`app/chat.py:731`) — `_format_investigation_snapshot` is only appended to the system prompt in investigating phase. In dossier phase the LLM has no visibility of the checklist state while `update_investigation_item` remains registered for items 6-10. Story 11.3/11.4 should decide whether to surface the snapshot in dossier phase.

## Deferred from: code review of 10-2/10-3/10-4 (2026-05-13)

- **[10-4] `INVESTIGATION_SYSTEM_PROMPT` has no DATA RULES** (`app/prompts.py:293`) — Accepted gap: investigation phase is interview-only; citation/data-integrity rules are not needed until dossier phase. Revisit if LLM starts producing data output in investigation mode.

- **[10-3] Partial rollback shows intermediate versions to frontend** (`app/chat.py:239-242`) — On multi-op failure, ops 1..N-1 were already streamed with incrementing versions before snap-back to `original_version`. Not data corruption; acceptable for now, address if JSX reconciliation issues arise.
- **[10-3] Anchor substring ambiguity within same batch** (`app/chat.py:203`) — `insert_after` with content containing the anchor causes an ambiguity error for the next op in the same call. Predictable and LLM-recoverable; document in tool description if it proves problematic.
- **[10-3] `apply_ops` returns misleading error when canvas failed silently on resume** (`app/chat.py:152`) — If `open_dossier_canvas()` raised and was swallowed during resume, subsequent `apply_ops` returns `"Error: dossier canvas is not open"` with no LLM recovery path. Linked to the broader dossier persistence gap.
- **[10-4] Unbounded dossier content in system prompt — no token cap** (`app/chat.py:619`) — Full document embedded in every dossier-phase API call. Add a `content[-MAX_CHARS:]` truncation guard before context limits become a real cost concern. (Acknowledged in Story 10.4 Dev Notes.)
- **[10-4] `APPLY_OPS_TOOL` appended to `combined_tools` without name-deduplication** (`app/chat.py:624-626`) — Duplicate tool name if an MCP server also registers `apply_ops`. Deferred until MCP tool-name registry is formalized.

## Deferred from: code review of 10-5-dossier-canvas-reopen-affordance (2026-05-13)

- **`on_chat_start` missing `-> None` return type annotation** (`app/chat.py:466`) — pre-existing issue not introduced by this story.
- **Reopen shows empty doc on resumed session** (`app/chat.py:425-429`) — `on_chat_resume` seeds doc with empty state; `/dossier` after resume shows an empty document. Explicitly out-of-scope for Story 10.5. Future story should replace `open_dossier_canvas()` in `on_chat_resume` with `reopen_dossier_canvas()` and repopulate props from persisted thread state.
- **`_register_dossier_commands` failure swallowed silently** (`app/chat.py:510-513`) — consistent with existing project pattern; acceptable for now but could be improved with a user-facing fallback if the slash command is critical.
