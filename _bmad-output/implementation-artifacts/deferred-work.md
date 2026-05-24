# Deferred Work

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
