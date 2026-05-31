# Story 12.3: Citation Flow into Dossier Sections

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a journalist,
I want every data claim in my dossier to have an inline citation and a live "Methodology and Sources" section,
So that each fact is traceable to its source without manual bookkeeping.

> **Depends on Story 12.2** (data validation gate fires before dossier phase, so `all_tool_outputs` contains at least one successful `get_data` response by the time `apply_ops` runs in the dossier phase). The existing citation pipeline from Story 9.1 (`app/citations.py`: `extract_references` → `deduplicate_references` → `format_reference_list`) is reused unchanged; this story wires it into the dossier document as a live section, in addition to its existing chat-message use.

---

## Acceptance Criteria

**AC1: `DOSSIER_SYSTEM_PROMPT` directs the LLM to include the `DATA_SOURCE` value inline when inserting data facts via `apply_ops`, with a concrete example.**
**Given** the dossier-phase system prompt at `app/prompts.py:137-158` (the `DATA RULES` section currently says *"Include the DATA_SOURCE value inline when inserting data facts."*)
**When** the prompt is rewritten in this story
**Then** the directive includes a concrete worked example using the dossier-track house style:
*"Water stress risk in 129 municipalities (World Development Indicators, WB_WDI_EG_ELC_ACCS_ZS, 2022)"*
**And** the directive explicitly names the format: `(<DATA_SOURCE>, <INDICATOR>, <year or year range>)` in parentheses immediately after the data fact
**And** the directive ties the requirement to the `apply_ops` tool by name: *"When you call `apply_ops` to insert any data fact, the inserted content MUST carry the inline citation in this exact shape."*

**AC2: The dossier document's "Methodology and Sources" section is auto-maintained from collected `all_tool_outputs` at the end of every agentic-loop round when in dossier phase.**
**Given** the agentic loop reaches the round-finalisation block at `app/chat.py:937-950` (the `if stop_reason != "tool_use":` branch that already builds the chat-side `ref_block` via `format_reference_list`)
**When** the round is in dossier phase (`cl.user_session["dossier"]["phase"] == "dossier"`) **and** `cl.user_session["doc"]` exists **and** `extract_references(all_tool_outputs)` returns a non-empty list
**Then** a new helper `_sync_dossier_references_section(doc, refs)` is called **after** the chat-side `ref_block` is appended (so the chat-side behaviour from Story 9.1 is preserved verbatim)
**And** the helper replaces the contents of the `## Methodology and Sources` section of `doc.props["content"]` with `format_reference_list(refs)` (NOT the placeholder text the propose_structure skeleton inserts)
**And** the helper bumps `doc.props["version"]` by 1
**And** the helper re-syncs `doc.content = json.dumps(doc.props)` and awaits `doc.update()` and `_refresh_dossier_canvas()` (the same triad `_handle_apply_ops` uses)
**And** if the `## Methodology and Sources` heading is absent from the current document content (e.g., a custom-restructured dossier), the helper appends a fresh `## Methodology and Sources\n\n<refs block>` at the end of the document instead of failing silently

**AC3: The LLM is instructed not to manually edit the "Methodology and Sources" section.**
**Given** the rewritten `DOSSIER_SYSTEM_PROMPT`
**When** the LLM is constructing `apply_ops` calls
**Then** the prompt contains an explicit rule: *"The `## Methodology and Sources` section is maintained automatically by the system from your tool calls. Do not edit it via apply_ops — your edits will be overwritten."*
**And** `_handle_apply_ops` does NOT enforce this server-side (intentional — keep the LLM-trust model simple; the section is overwritten on the next round anyway)

**AC4: When `all_tool_outputs` has zero extractable references (no API tool calls in the round), the dossier section is NOT touched.**
**Given** the round-finalisation block runs in dossier phase
**When** `extract_references(all_tool_outputs)` returns `[]` (no successful API responses with `CITATION_SOURCE`)
**Then** `_sync_dossier_references_section` is NOT called, the document is unchanged, no `doc.update()` fires
**And** the chat-side `ref_block` behaviour is preserved (also not appended when refs are empty — the existing `if raw_refs:` guard at `app/chat.py:942` continues to gate both paths)

**AC5: Lint, format, and full test suite pass.**
**Given** the changes above
**When** `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest -q` are run
**Then** all checks pass; the new tests from AC1–AC4 are included.

---

## Tasks / Subtasks

### Task 1: Rewrite `DOSSIER_SYSTEM_PROMPT` DATA RULES + add Methodology-section rule (AC: 1, 3)

- [x] In `app/prompts.py` (currently lines 137-158), rewrite the `DATA RULES:` block to:
  - Keep the existing "Use search_indicators and get_data to ground every factual claim in real data." sentence.
  - Replace the bare "Include the DATA_SOURCE value inline when inserting data facts." with a concrete worked example and a format spec — see AC1 for the verbatim shape.
  - Keep the existing "If data is not found for a claim, say so explicitly. Do not invent numbers." sentence — Story 12.4 may extend this.
- [x] Add a new bullet at the end of the `DOSSIER STRUCTURE:` block (currently `app/prompts.py:155-158`):
  - *"The `## Methodology and Sources` section is maintained automatically by the system from your tool calls. Do not edit it via apply_ops — your edits will be overwritten on the next round."*

### Task 2: Add `_sync_dossier_references_section` helper (AC: 2)

- [x] Add an async helper near `_handle_apply_ops` (around `app/chat.py:460-504`) — colocated with the other doc-mutation functions so reviewers see the same pattern:

  ```python
  _METHODOLOGY_HEADING = "## Methodology and Sources"


  async def _sync_dossier_references_section(doc: cl.CustomElement, refs: list[dict[str, Any]]) -> None:
      """Replace the contents of the dossier's "Methodology and Sources" section with
      the deterministic references block built from collected tool outputs.

      The section is the LAST section of the propose_structure skeleton. If the user
      has restructured the dossier and the heading is absent, the references block is
      appended as a fresh section at the end of the document.
      """
      from app.citations import format_reference_list  # local import to keep cycle-free

      block = format_reference_list(refs)
      content: str = doc.props.get("content", "")
      if _METHODOLOGY_HEADING in content:
          before, _, _after = content.partition(_METHODOLOGY_HEADING)
          # Replace EVERYTHING from the heading to end-of-document with heading + fresh block.
          new_content = before.rstrip() + "\n\n" + _METHODOLOGY_HEADING + "\n\n" + block + "\n"
      else:
          new_content = content.rstrip() + "\n\n" + _METHODOLOGY_HEADING + "\n\n" + block + "\n"
      if new_content == content:
          return  # no-op guard so version doesn't tick when nothing changed
      doc.props["content"] = new_content
      doc.props["version"] = int(doc.props.get("version", 0)) + 1
      doc.content = json.dumps(doc.props)  # re-sync: CustomElement.content is set only once
      await doc.update()
      await _refresh_dossier_canvas()
  ```

  **Important details:**
  - Use `content.partition(_METHODOLOGY_HEADING)` so we replace **from the heading to end-of-document** with the fresh block — propose_structure puts `## Methodology and Sources` as the LAST section, so anything after it is either the placeholder or a stale references block. This is intentional; the section is system-owned.
  - The no-op guard (`if new_content == content:`) prevents a spurious `version` bump and a spurious `doc.update()` when the references haven't changed across rounds (which happens whenever a round has no new tool calls).
  - Use the same content-mutation triad as `_handle_apply_ops` (`app/chat.py:482-486` and `:489-493`): set `doc.props["content"]`, bump version, re-sync `doc.content = json.dumps(doc.props)`, await `doc.update()`, then `_refresh_dossier_canvas()`. **DO NOT** call `update_dossier_content` — that helper doesn't bump version and would conflict with the manual version handling here.

### Task 3: Wire the helper into the round-finalisation block (AC: 2, 4)

- [x] In `_agentic_loop` at `app/chat.py:937-950`, modify the `if stop_reason != "tool_use":` block so that **after** the existing chat-side append (lines 940-948 unchanged) and **before** `return final_text`, an in-dossier-phase sync runs:

  ```python
  # Story 12.3: also flow the same references into the dossier doc's
  # "Methodology and Sources" section when in dossier phase.
  dossier_state = cl.user_session.get("dossier")
  if (
      raw_refs
      and isinstance(dossier_state, dict)
      and dossier_state.get("phase") == "dossier"
      and (doc := cl.user_session.get("doc")) is not None
  ):
      await _sync_dossier_references_section(doc, refs)
  ```

- [x] The block reuses `raw_refs` and `refs` from the chat-side build above — do NOT call `extract_references` / `deduplicate_references` a second time.
- [x] The walrus assignment `(doc := …) is not None` keeps the doc lookup inside the guard so it doesn't run when refs are empty or phase is investigating.

### Task 4: Tests (AC: 1, 2, 3, 4, 5)

- [x] Add a new test class `TestCitationFlowIntoDossierSections` to `tests/app/test_chat.py`, near `TestApplyOps…` and `TestProposeStructureTool`. Use `@pytest.mark.usefixtures("set_required_env_vars")` and the `reload_chat` fixture.

- [x] **AC1 (prompt directive)** — `test_dossier_prompt_directs_inline_citation_with_example`:
  - `from app.prompts import DOSSIER_SYSTEM_PROMPT` via `reload_chat`.
  - Assert the string contains: `"DATA_SOURCE"`, the format spec `"(<DATA_SOURCE>, <INDICATOR>, <year or year range>)"`, and a recognisable fragment of the worked example (e.g., `"WB_WDI_EG_ELC_ACCS_ZS"` or `"129 municipalities"` — pick something distinctive enough to anchor the test).

- [x] **AC3 (prompt rule on Methodology section)** — `test_dossier_prompt_warns_against_editing_methodology_section`:
  - Assert the prompt contains the phrases `"Methodology and Sources"` and `"automatically"` and `"apply_ops"` — three substrings together so a rewording can't drift the test silently.

- [x] **AC2 (helper replaces existing section)** — `test_sync_dossier_references_replaces_existing_methodology_section`:
  - Build a fake doc with `props = {"content": "# Exec\n\n[stuff]\n\n## Methodology and Sources\n\n[Document data sources and methodology here.]\n", "version": 1, "phase": "dossier"}` and `update = AsyncMock()`.
  - Call `await reload_chat._sync_dossier_references_section(doc, refs=[<one-ref dict>])` where the ref is shaped like `extract_references` outputs (see `app/citations.py:165-173`).
  - Assert `doc.props["content"]` starts with `"# Exec"`, ends with the freshly formatted references block, and contains exactly ONE `"## Methodology and Sources"` (no duplicates).
  - Assert `doc.props["version"] == 2`.
  - Assert `doc.content == json.dumps(doc.props)` (the re-sync invariant).
  - Assert `doc.update` was awaited once.
  - Patch `_refresh_dossier_canvas` and assert it was awaited once.

- [x] **AC2 (helper appends when section absent)** — `test_sync_dossier_references_appends_section_when_heading_absent`:
  - Same setup but `content = "# Exec\n\nNo methodology heading.\n"`.
  - After the call, assert `"## Methodology and Sources"` appears at the end of `doc.props["content"]` followed by the refs block.

- [x] **AC2 (no-op when content is unchanged)** — `test_sync_dossier_references_is_noop_when_content_unchanged`:
  - First call with `refs=[<ref>]` → bumps version to 2 and writes content.
  - Second call with the same `refs` → assert version stays at 2 and `doc.update.await_count == 1` (no second update).

- [x] **AC4 (round-finalisation skips sync when refs empty)** — `test_round_finalisation_skips_dossier_sync_when_no_refs`:
  - End-to-end through `on_message` with a single round that ends in `stop_reason="end_turn"` and `all_tool_outputs == []` (no tool calls).
  - Patch `_sync_dossier_references_section` (`new_callable=AsyncMock`) and assert it was NOT awaited.

- [x] **AC4 (round-finalisation skips sync in investigating phase)** — `test_round_finalisation_skips_dossier_sync_in_investigating_phase`:
  - End-to-end with a search_indicators tool round whose result has refs; session phase is `investigating`.
  - Assert `_sync_dossier_references_section` was NOT awaited (phase guard).
  - Assert the chat-side `ref_block` WAS appended (existing behaviour preserved).

- [x] **AC2 (round-finalisation calls sync in dossier phase)** — `test_round_finalisation_calls_dossier_sync_in_dossier_phase`:
  - End-to-end with a get_data tool round whose result has refs; session phase is `dossier`; `doc` is in session.
  - Assert `_sync_dossier_references_section` was awaited once with `(doc, refs)` where `refs` is the dedup'd list.
  - Assert the chat-side `ref_block` was ALSO appended (both code paths fire).

### Task 5: Lint, format, full test suite (AC: 5)

- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pytest -q`

### Review Findings

_`/bmad-code-review` (full mode) — 2026-05-30. Target: Story 12.3. Reviewed the uncommitted working-tree diff (`git diff HEAD`), which also bundles uncommitted Story 12.2 code; findings below are scoped to 12.3. Layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor (all 5 ACs confirmed satisfied). Outcome: 1 decision-needed, 1 patch, 0 defer, 9 dismissed._

**decision-needed (resolved):**

- [x] [Review][Decision] `_sync_dossier_references_section` locates the section by substring `partition`, which is neither line-anchored nor section-bounded [app/chat.py:540-545] — (1) **Embedded/deeper-heading false match:** `if _METHODOLOGY_HEADING in content` + `content.partition(...)` match the string anywhere, so `### Methodology and Sources` or the phrase in prose/code-fence splits mid-line, leaving an orphaned `#` → corrupted output. (2) **Trailing-section destruction:** `partition` discards `_after`, deleting everything from the heading to EOF. **RESOLVED 2026-05-30 → Line-anchor only:** fix facet 1 (match the heading only at line-start), keep partition-to-EOF for facet 2 (the spec's documented, accepted tradeoff). Sources: blind+edge.

**patch:**

- [x] [Review][Patch] Line-anchor the `## Methodology and Sources` match in `_sync_dossier_references_section` [app/chat.py] — APPLIED 2026-05-30: added `import re` + module-level `_METHODOLOGY_HEADING_RE = re.compile(r"^## Methodology and Sources[ \t]*$", re.MULTILINE)`; helper now uses `_METHODOLOGY_HEADING_RE.search(content)` instead of substring `in`/`partition`. Deeper/embedded headings no longer false-match; replace-to-EOF semantics and the absent-heading append fallback preserved.
- [x] [Review][Patch] Add regression test for `_sync_dossier_references_section` section-targeting [tests/app/test_chat.py] — APPLIED 2026-05-30: `test_sync_dossier_references_does_not_false_match_deeper_heading` asserts a `### Methodology and Sources` heading + body survive, no orphaned `#`, exactly one line-anchored H2 is appended. Suite: 430 pass, ruff check + format clean.

_Dismissed (9): 12.2 truncation→validation-flag defect (already in `deferred-work.md` from 12.2 review); no-op-guard whitespace divergence (negligible — round-loop output is idempotent); empty-refs writes empty section (unreachable — sync is gated by `if raw_refs:` with non-empty dedup output, verified app/chat.py:1008-1024); non-str `doc.props["content"]` (defensive only — `ensure_dossier_doc` seeds `content=""`); `json.loads`/`int` except-clause asymmetry (non-defect); validation gate before state fallback (non-defect); weak no-session test (12.1 scope, already deferred); tautological prompt substring tests (by-design per spec); Auditor's nested-guard + double-`## References`-heading deviations (documented/intentional)._

---

## Dev Notes

### What this story is (and is not)

**Is:**
- Server-managed "Methodology and Sources" section in the dossier document, populated deterministically from `all_tool_outputs` using the existing Story 9.1 citation pipeline.
- Prompt strengthening: inline `DATA_SOURCE` format with a concrete example; rule that the LLM must not edit the Methodology section.
- Reuse of the existing chat-side citation behaviour at `app/chat.py:937-948` — the dossier sync is an ADDITIONAL flow, not a replacement.

**Is not:**
- A new "Data Sources" section in the dossier — propose_structure already creates `## Methodology and Sources` (Story 11.4 skeleton). This story populates that existing section; it does NOT add a parallel one.
- Server-side enforcement of the inline-citation rule — left as a prompt instruction. The LLM is trusted; if it omits the parenthetical citation, the user reads it without one in that round, but the Methodology section still lists the source.
- Inline citation injection by the server (i.e., post-processing `apply_ops` content to add the citation) — explicitly out of scope. The LLM owns the inline format because only the LLM knows which fact in the inserted text corresponds to which DATA_SOURCE.
- A one-shot "session end" finalisation — Epic 13 (Export/Sharing) owns that. 12.3 maintains the section live, every round.
- Document references (RAG / Story 8.x) inline format — the existing `extract_references` already handles both `"type": "api"` and `"type": "document"` refs; `format_reference_list` formats both. 12.3 inherits that for free.

### Why round-finalisation, not after every apply_ops

The trigger has to be:
- AFTER the agentic loop has finished collecting tool outputs in the round.
- BEFORE returning to the user.
- ONLY when there are refs to flow.

The existing chat-side `ref_block` build at `app/chat.py:937-948` already meets these criteria — it runs exactly once per round, after the LLM stops calling tools (`stop_reason != "tool_use"`). Wiring the dossier sync into the same block:
- Reuses the `raw_refs` / `refs` computation (zero duplicate work).
- Inherits the existing empty-refs guard (chat-side behaviour for "no refs" is unchanged).
- Keeps the dossier and chat reference views in lockstep — they always show the same sources.

Calling sync after every `apply_ops` instead would be noisier (multiple updates per round if the LLM batches edits), and would force a separate refs computation inside `_handle_apply_ops`. Worse, it would update the Methodology section even when no new MCP data arrived in the round.

### Why partition replaces the section *and everything after it*

propose_structure's skeleton (`app/chat.py:_build_dossier_skeleton`) places `## Methodology and Sources` as the LAST section, with `[Document data sources and methodology here.]` as its placeholder body. Anything after the heading is either:
1. The placeholder (first round, never edited).
2. A stale references block from a previous round.

Both cases should be REPLACED, not preserved. `content.partition(_METHODOLOGY_HEADING)` returns `(before, sep, after)`; we discard `after` entirely and write `before + heading + fresh refs`. If a future story makes Methodology a non-trailing section, the partition approach still works but would erase any sections the journalist added below it — that's a tradeoff worth surfacing in the Methodology rule (AC3 prompt directive: "do not edit it via apply_ops", implicitly "do not add sections below it either").

### Why the no-op guard is critical

The agentic loop can finalise multiple rounds in a session. If the LLM does one tool round (3 search/get_data calls) and then 10 chat-only rounds, the helper would otherwise:
- Bump `doc.props["version"]` 10 times unnecessarily.
- Call `doc.update()` 10 times → 10 frontend re-renders of an unchanged section.
- Re-render `_refresh_dossier_canvas` 10 times → 10 ElementSidebar key bumps.

The `if new_content == content: return` guard short-circuits this. It's a string equality check on (often-large) markdown — acceptable for the round-end frequency. If perf becomes an issue, cache the last block hash; not in scope here.

### Existing wiring anchors (verified 2026-05-30)

| What | File:Line | Notes |
|---|---|---|
| Citation pipeline entry points | `app/citations.py:97` (`extract_references`), `:180` (`deduplicate_references`), `:238` (`format_reference_list`) | Reuse unchanged |
| Chat-side ref block append (Story 9.1) | `app/chat.py:937-948` | Existing behaviour preserved verbatim; dossier sync is layered after it |
| `apply_ops` content-mutation triad | `app/chat.py:482-486`, `:489-493` | Pattern to mirror in `_sync_dossier_references_section` |
| `update_dossier_content` helper | `app/chat.py:139-147` | **Do NOT use** — doesn't bump version; would conflict with manual version handling |
| `propose_structure` skeleton (Methodology heading source) | `app/chat.py:_build_dossier_skeleton` (around `:380-407`) | Section is the LAST in the skeleton — partition-replace is safe |
| `_refresh_dossier_canvas` | `app/chat.py:198-215` | No-op when canvas not revealed; safe to call from the sync |
| `DOSSIER_SYSTEM_PROMPT` | `app/prompts.py:137-158` | Target for the prompt edits |

### `extract_references` ref-dict shape (the input to `format_reference_list`)

From `app/citations.py:165-173`, API refs look like:
```python
{
    "source": "<CITATION_SOURCE string>",
    "indicator_code": "EN_ATM_CO2E_KT",
    "indicator_name": "<COMMENT_TS string>",
    "database_id": "WB_WDI",
    "year": 2022,           # backward-compat
    "years": [2020, 2021, 2022],
    "type": "api",
}
```

Document refs (from RAG) look different (`type: "document"` plus `filename`, `page`, `chunk`). `format_reference_list` handles both. Tests should feed API-shaped refs (the dominant case for Epic 12) but include at least one document-ref test if the test scaffolding makes it cheap (it does — just one extra `_make_ref` call).

### Test patterns to follow (do NOT reinvent)

- `TestApplyOps…` (search `tests/app/test_chat.py` for the apply_ops classes) — established the doc-mutation testing pattern: `MagicMock(props={...}, update=AsyncMock())` plus patch of `_refresh_dossier_canvas`. Mirror it.
- `TestProposeStructureTool` (line 2864) — established the `_make_fake_ce_factory` and session-mock plumbing the dossier-doc tests use.
- Prompt-content assertions: `assert "..." in DOSSIER_SYSTEM_PROMPT` (Story 11.4 P6 precedent).
- End-to-end finalisation tests: use the `FakeStream(stop_reason="end_turn", ...)` pattern (single-round, no tool_use) and patch `_sync_dossier_references_section` via `new_callable=AsyncMock` to assert it was/was-not called.

### Existing helpers this story reuses (do NOT reinvent)

- `extract_references` / `deduplicate_references` / `format_reference_list` (`app/citations.py`) — unchanged.
- `_refresh_dossier_canvas` (`app/chat.py:198-215`) — unchanged.
- `cl.user_session` get/set — unchanged.

---

## Project Structure Notes

- Files under change: `app/prompts.py`, `app/chat.py`, `tests/app/test_chat.py`. No new modules, no new files.
- No new dependencies (uses existing `json`, `app.citations`).
- The new helper is colocated with `_handle_apply_ops` in `app/chat.py` for proximity and reviewer convenience.
- `app/citations.py` is NOT modified — it already exports `format_reference_list` and the dedup helpers.

## File Structure Requirements

| File | Status | Purpose |
|---|---|---|
| `app/prompts.py` | UPDATE | Rewrite `DOSSIER_SYSTEM_PROMPT` DATA RULES with example + add Methodology rule (Task 1) |
| `app/chat.py` | UPDATE | Add `_METHODOLOGY_HEADING` constant + `_sync_dossier_references_section` helper + dossier-sync block in `_agentic_loop` finalisation (Tasks 2-3) |
| `tests/app/test_chat.py` | UPDATE | New `TestCitationFlowIntoDossierSections` class with 8 tests (Task 4) |

**Files this story must NOT touch:** `app/citations.py`, `mcp_server/**`, `public/**`, `INVESTIGATION_SYSTEM_PROMPT`. The Story 9.1 chat-side ref pipeline is unchanged; the only addition is the dossier layer.

## Testing Requirements

- 8 new tests in `tests/app/test_chat.py` (Task 4).
- Existing test suite must stay green: `uv run pytest -q`.
- Lint + format clean per Task 5.
- All doc-mutating tests use `MagicMock` docs with `update=AsyncMock()` and patch `_refresh_dossier_canvas`.
- Prompt-content tests use substring assertions with distinctive anchors so minor rewording is OK but structural drift fails loudly.

## Anti-Patterns (do NOT do)

- **DON'T** use `update_dossier_content` — it doesn't bump version, and the sync helper needs explicit version handling to keep ElementSidebar in sync. Use the `apply_ops` triad pattern (set content, bump version, re-sync `doc.content`, await `doc.update`, refresh canvas).
- **DON'T** preserve content after the `## Methodology and Sources` heading — the section is system-owned, partition-replace is intentional.
- **DON'T** add server-side post-processing to `apply_ops` content to inject citations — the LLM owns the inline format (it knows which fact maps to which source). Server-side injection is brittle and out of scope.
- **DON'T** skip the no-op guard — chat-only rounds happen frequently and unguarded sync would thrash the document version + sidebar key.
- **DON'T** call `extract_references` / `deduplicate_references` twice in the finalisation block — the chat-side build at `:941-943` already computes them; reuse the variables.
- **DON'T** add the dossier sync inside `_handle_apply_ops` — the trigger is round-end (after stop_reason != "tool_use"), not per-op.
- **DON'T** create a parallel `## Data Sources` heading in the dossier — propose_structure's `## Methodology and Sources` IS the heading. Duplicating would confuse downstream Export logic (Epic 13).
- **DON'T** touch `INVESTIGATION_SYSTEM_PROMPT` — that's Story 12.2's scope (data validation gate + key stats capture prompts).
- **DON'T** add `extract_references` invocations to investigating-phase rounds expecting refs to flow to a doc — there's no doc in investigating phase (lazy creation happens at phase transition via Story 10.6's `ensure_dossier_doc`).

---

## Previous Story Intelligence

### From Story 12.2 (`12-2-data-validation-gate.md`, ready-for-dev)

- By the time the LLM is in dossier phase, at least one successful `search_indicators` call has fired (gated by 12.2 AC2). It's likely that at least one `get_data` call has also fired (gated by the prompt directive in 12.2 AC4). Therefore `all_tool_outputs` in the first dossier-phase round usually has at least one ref-yielding entry.
- The `key_stats_capture` dict the LLM writes via `update_investigation_item` (12.2 AC4) carries a `source` field — that string is the same `DATA_SOURCE` the LLM is now asked to inline in apply_ops content (12.3 AC1). No conflict; both use the same canonical string.

### From Story 12.1 (`12-1-mcp-tools-in-dossier-session.md`, ready-for-dev)

- MCP tools are available in both phases. 12.3 only cares about the dossier-phase case; the investigating-phase test (AC4 second test) confirms 12.1's wiring stays correct by asserting the existing chat-side ref block still fires.

### From Story 11.4 (`11-4-propose-structure-tool.md`, done — PR #68 merged)

- `propose_structure` builds the skeleton with `## Methodology and Sources` as the LAST section (`app/chat.py:_build_dossier_skeleton`, around `:380-407`). The partition-replace strategy in `_sync_dossier_references_section` depends on this — if a future story reorders sections, the helper needs to learn to find the section more robustly (e.g., regex on the heading + match-until-next-`##`-or-EOF).
- The post-11.4 code-review pattern is `cl.Step(name=f"🔧 {tool_name}", type="tool")` for tool steps; `_sync_dossier_references_section` is NOT a tool step — it's a finalisation side effect, not wrapped in `cl.Step`.
- The 11.4 code-review (P3) established the `delete window.__cc_toggle_dossier` cleanup pattern in `Document.jsx`. Irrelevant for 12.3 (no frontend changes), but confirms the project's UnitOfWork-style discipline for cleanup.

### From Story 10.3 (`10-3-apply-ops-patch-engine.md`, done)

- `_handle_apply_ops` (`app/chat.py:460-504`) is the canonical doc-mutation function: snapshot for rollback, per-op apply, content-mutation triad. `_sync_dossier_references_section` mirrors the triad portion (lines `:489-493`) but has a much simpler structure (single replace, no rollback needed — the references are deterministic from `all_tool_outputs`).

### From Story 9.1 (`9-1-server-side-data-sources-block.md`, done)

- `extract_references` / `deduplicate_references` / `format_reference_list` were designed to be data-source-agnostic (handles both API and document refs). 12.3 reuses them at face value.
- The existing chat-side append at `app/chat.py:937-948` is the canonical use site; 12.3 layers the dossier sync directly after it.

---

## Latest Tech Information

### `format_reference_list` output format

From `app/citations.py:238-…`, the function returns a markdown block titled `## References` (English) / `## Referências` (Portuguese) / `## Referencias` (Spanish), with each reference as a numbered entry. The 12.3 sync wraps the OUTPUT under the `## Methodology and Sources` heading — i.e., the final dossier section looks like:

```markdown
## Methodology and Sources

## References

1. World Development Indicators (WB_WDI) — EN_ATM_CO2E_KT (2020–2022)
2. …
```

The double-heading (`## Methodology and Sources` then `## References`) is intentional — the section is the journalist-facing "Methodology and Sources" container, and the `## References` sub-heading is the machine-generated list. If this reads awkwardly during dev verification, flag it as a follow-up (potentially: pass `heading=None` to `format_reference_list` once that param exists, but it does NOT exist today and adding it is out of scope for 12.3).

### `cl.CustomElement.props["version"]` semantics

`Document.jsx` re-renders when `doc.props["version"]` changes (via the Story 11.4 P3 patch: `useEffect` cleanup makes the bridge robust against stale closures). Bumping `version` from `_sync_dossier_references_section` triggers a re-render. The version is monotonic per session; reaches double digits in long sessions — fine, just an integer.

### Walrus in conditionals (Python 3.12)

`(doc := cl.user_session.get("doc")) is not None` is project-style (CLAUDE.md allows it; line length 120). Used here to avoid a separate `doc = cl.user_session.get("doc")` line that runs even when `raw_refs` is empty.

---

## Git Intelligence Summary

Recent commits on `main` (post-11.4 merge):

- `8036acd` chore(epic-10): close epic formally
- `020bbea` feat(11-4): propose_structure tool + dossier panel toggle & resume auto-reveal (#68)
- `06b0c68` feat(11-3): phase gate logic (#67)
- `c8fb46f` feat(10-6): on-demand dossier canvas reveal (#66)

**Patterns relevant to 12.3:**
- Every dossier-track story that mutates `doc.props` uses the same triad (`doc.props[…] = …; doc.props["version"] += 1; doc.content = json.dumps(doc.props); await doc.update(); await _refresh_dossier_canvas()`). 12.3 follows this pattern verbatim. The 11.4 P3 patch (`Document.jsx` cleanup) makes the frontend resilient to bridge churn from the additional update.
- `app/chat.py` is the busiest file. Symbol anchors (`_handle_apply_ops`, `_refresh_dossier_canvas`, `_agentic_loop`, the `if stop_reason != "tool_use":` block) are stable; line numbers will shift.

---

## Project Context Reference

Rules from `_bmad-output/project-context.md` most relevant to 12.3:

- **Citation integrity: `DATA_SOURCE` from API response must never be modified or removed.** 12.3 reads it via the existing `extract_references` pipeline; no modification.
- **`CITATION_SOURCE` enrichment via `_db_name_cache`** — out of scope here; `extract_references` reads `CITATION_SOURCE` directly. The enrichment runs upstream in `Data360Client`.
- **Downstream code (Epic 3+) must use `CITATION_SOURCE`, not `DATA_SOURCE`, for citation display.** `extract_references` reads `CITATION_SOURCE` for the `source` field (`app/citations.py:134, 143, 166`). The LLM is asked to inline `DATA_SOURCE` (per the AC text) — that string is what the user sees in the prose; `CITATION_SOURCE` populates the structured list. If `CITATION_SOURCE` and `DATA_SOURCE` ever diverge for an API response (per the project rule: enrichment from `_db_name_cache`), the inline value (LLM-chosen `DATA_SOURCE`) and the list value (`CITATION_SOURCE`) may differ — that's intentional per the project's enrichment model.
- **Citations are pipeline-guaranteed: `app/citations.py` builds a structured citation registry from MCP tool responses server-side.** 12.3 reuses this contract verbatim; no LLM-formatted citations.
- **The LLM's only citation responsibility is placing `[n]` markers in prose** — and (per 12.3 AC1) the inline `(<DATA_SOURCE>, …)` parenthetical at the data-fact site. The numbered list is still server-built.
- **Reference list title adapts to conversation language ("References", "Referências", "Referencias").** Inherited via `format_reference_list`'s `language` parameter — 12.3 does NOT pass `language` (defaults to `"en"`); language-aware dossier sections are a future story.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No blockers. All 5 ACs satisfied on first pass.

### Completion Notes List

- Task 1: Rewrote `DOSSIER_SYSTEM_PROMPT` DATA RULES block in `app/prompts.py` — replaced bare "include DATA_SOURCE" with format spec `(<DATA_SOURCE>, <INDICATOR>, <year or year range>)` plus worked example (WB_WDI_EG_ELC_ACCS_ZS, 129 municipalities). Added Methodology-section non-edit rule to DOSSIER STRUCTURE block.
- Task 2: Added `_METHODOLOGY_HEADING` constant and `_sync_dossier_references_section` async helper to `app/chat.py` immediately after `_handle_apply_ops`. Uses `content.partition()` to replace heading-to-EOF; no-op guard prevents spurious version bumps.
- Task 3: Wired helper into `_agentic_loop` round-finalisation block — reuses existing `raw_refs`/`refs` variables; condition guards on `isinstance(dossier_state, dict)`, `phase == "dossier"`, and `doc is not None`; walrus operator keeps the doc lookup inside the guard.
- Task 4: 8 new tests in `TestCitationFlowIntoDossierSections` — all pass. Two prompt tests, three helper unit tests, three end-to-end round-finalisation tests.
- Task 5: ruff check, ruff format --check, full suite — 429 tests pass.

### File List

- `app/prompts.py` — Updated: DOSSIER_SYSTEM_PROMPT DATA RULES rewritten + Methodology rule added
- `app/chat.py` — Updated: `_METHODOLOGY_HEADING` constant + `_sync_dossier_references_section` helper + round-finalisation dossier sync block
- `tests/app/test_chat.py` — Updated: `TestCitationFlowIntoDossierSections` class with 8 tests; helpers `_make_api_ref`, `_make_get_data_mcp_result_with_citation`

### Change Log

| Date | Notes |
|---|---|
| 2026-05-30 | Story created by `/bmad-create-story` (batch draft of Epic 12 stories 2-4). |
| 2026-05-30 | Implemented by dev agent (claude-sonnet-4-6): prompt rewrite (AC1, AC3), `_sync_dossier_references_section` helper (AC2), round-finalisation wiring (AC2, AC4), 8 tests (AC5). 429 tests pass. |
