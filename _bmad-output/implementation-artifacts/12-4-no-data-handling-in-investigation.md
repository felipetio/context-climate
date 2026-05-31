# Story 12.4: No-Data Handling in Investigation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a journalist,
I want clear feedback when data is not available for my topic,
So that I can adjust my angle rather than discovering gaps after the dossier is built.

> **Depends on Stories 12.2 and 12.3.** 12.4 extends the prompts those two stories rewrite (`INVESTIGATION_SYSTEM_PROMPT` for search_indicators / get_data narration; `DOSSIER_SYSTEM_PROMPT` for the don't-fabricate rule). The hard enforcement that item 5 cannot pass without data is already shipped in 12.2 AC2 (the `_data_validation_indicators_found` gate); 12.4 owns the **UX phrasing** of the failure modes and the **dossier-content rule** that empty indicators are not written into the document.

---

## Acceptance Criteria

**AC1: `INVESTIGATION_SYSTEM_PROMPT` directs the LLM to narrate zero-result `search_indicators` calls with the verbatim copy and ask the journalist to refine.**
**Given** the LLM has called `search_indicators(query=<topic>, country=<geography>)` at item 5
**When** the response decodes with `success == True` and `total_count == 0` (or `data == []`)
**Then** the rewritten `INVESTIGATION_SYSTEM_PROMPT` (`app/prompts.py:115-134+`, post-12.2) directs the LLM to respond in chat with the verbatim phrasing:
*"No indicators found for [topic] in [geography]. Try broader terms or a different geography."*
**And** the prompt directs the LLM NOT to call `update_investigation_item("data_sources_validation", …)` until a subsequent search returns at least one result (this aligns with the server-side gate from 12.2, which would reject the call anyway, but the prompt sets the right expectation to avoid a dead user-visible round of "rejected" messages)
**And** the prompt directs the LLM to ask one focused refinement question (e.g., *"Would you like to broaden the geography or rethink the topic angle?"*) — single question, per the existing INTERVIEW RULES at `app/prompts.py:118-121`

**AC2: `INVESTIGATION_SYSTEM_PROMPT` directs the LLM to narrate empty `get_data` results with the verbatim copy.**
**Given** the LLM has called `get_data` on a found indicator during investigation
**When** the response decodes with `success == True` and an empty `data` array (or `total_count == 0`)
**Then** the rewritten prompt directs the LLM to respond in chat with the verbatim phrasing:
*"No data available for [indicator] in [geography/year range]."*
**And** the prompt directs the LLM NOT to include that indicator's stats in `update_investigation_item("key_stats_capture", …)` (the 12.2 AC4 capture call)
**And** the prompt suggests a recovery action (e.g., *"Try a different time range or check another indicator from the search results."*) — single sentence

**AC3: `DOSSIER_SYSTEM_PROMPT` is extended with a rule that empty-data indicators must not be written into the dossier.**
**Given** the rewritten `DOSSIER_SYSTEM_PROMPT` (post-12.3, which adds the inline-citation rules + the Methodology-section rule)
**When** the LLM is constructing `apply_ops` calls
**Then** the prompt contains an additional rule under `DATA RULES`:
*"If `get_data` returned an empty `data` array for an indicator, DO NOT insert a section, paragraph, or claim about that indicator into the dossier. Note its absence in the journalist's narrative angle instead (e.g., 'No World Bank data is currently available for X in this geography')."*
**And** the rule is positioned after 12.3's "Include the DATA_SOURCE value inline" directive and before the "If data is not found for a claim, say so explicitly" sentence (which 12.4 leaves intact — that sentence is the general fallback; the new rule is the specific empty-indicator case)

**AC4: An MCP-error response (`success == False`) is narrated as a transient API failure, not as "no data".**
**Given** the LLM has called `search_indicators` or `get_data` and the response decodes with `success == False` and `error_type` in `{"api_error", "timeout"}`
**When** the LLM responds
**Then** the rewritten `INVESTIGATION_SYSTEM_PROMPT` directs the LLM to distinguish this from the zero-result case and respond with:
*"The data service returned an error — let's try again in a moment, or rephrase the query."*
**And** the LLM is directed NOT to mark item 5 done and NOT to claim "no data exists" (the data might exist; the upstream service just failed)

**AC5: Lint, format, and full test suite pass.**
**Given** the prompt edits above
**When** `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest -q` are run
**Then** all checks pass; the new prompt-content tests from AC1–AC4 are included.

---

## Tasks / Subtasks

### Task 1: Extend `INVESTIGATION_SYSTEM_PROMPT` (AC: 1, 2, 4)

- [x] In `app/prompts.py`, **after** 12.2's DATA VALIDATION + KEY STATS CAPTURE sub-sections are added (Story 12.2 Task 1), add a new sub-section titled **NO-DATA & ERROR HANDLING** with three blocks:
  - **Zero indicators found** (AC1): the verbatim "No indicators found for [topic] in [geography]. Try broader terms or a different geography." + the refinement question rule.
  - **Empty get_data response** (AC2): the verbatim "No data available for [indicator] in [geography/year range]." + the don't-capture rule + the recovery-action sentence.
  - **API error response** (AC4): the verbatim "The data service returned an error — let's try again in a moment, or rephrase the query." + the don't-conclude-no-data rule.
- [x] Keep the placeholder syntax (`[topic]`, `[geography]`, `[indicator]`, `[geography/year range]`) as **prompt template markers the LLM substitutes** — they are NOT runtime f-string placeholders. The LLM reads them as "substitute with the relevant value."
- [x] Do NOT modify the existing INTERVIEW RULES or INVESTIGATION CHECKLIST blocks — extend, don't rewrite.

### Task 2: Extend `DOSSIER_SYSTEM_PROMPT` (AC: 3)

- [x] In `app/prompts.py`, **after** 12.3's DATA RULES rewrite (Story 12.3 Task 1), add the AC3 rule under DATA RULES, positioned between 12.3's inline-citation directive and the existing "If data is not found for a claim, say so explicitly" sentence.
- [x] Keep all other DOSSIER_SYSTEM_PROMPT content untouched.

### Task 3: Tests (AC: 1, 2, 3, 4, 5)

- [x] Add a new test class `TestNoDataHandling` to `tests/app/test_chat.py`, near `TestDataValidationGate` (the 12.2 class). Use `@pytest.mark.usefixtures("set_required_env_vars")` and the `reload_chat` fixture.

- [x] **AC1 (zero-indicators copy)** — `test_investigation_prompt_handles_zero_search_results`:
  - `from app.prompts import INVESTIGATION_SYSTEM_PROMPT` via `reload_chat`.
  - Assert the prompt contains the literal substring `"No indicators found for [topic] in [geography]. Try broader terms"`.

- [x] **AC2 (empty get_data copy)** — `test_investigation_prompt_handles_empty_get_data`:
  - Assert the prompt contains the literal substring `"No data available for [indicator] in [geography/year range]"`.
  - Assert the prompt also contains a phrase tying this to NOT capturing the indicator in key_stats_capture (e.g., contains both `"key_stats_capture"` and `"DO NOT"` / `"do not"` near each other — substring check on `"key_stats_capture"` and on a recovery phrase).

- [x] **AC4 (API error copy)** — `test_investigation_prompt_distinguishes_api_error_from_no_data`:
  - Assert the prompt contains the literal substring `"The data service returned an error"`.
  - Assert the prompt does NOT lump API errors and zero-results into the same instruction — the test should not need to verify the negative directly; it's enough to assert both verbatim strings appear in distinct contexts (i.e., the prompt has both `"No indicators found"` AND `"The data service returned an error"` as separate substrings).

- [x] **AC3 (dossier prompt extension)** — `test_dossier_prompt_forbids_empty_indicator_sections`:
  - `from app.prompts import DOSSIER_SYSTEM_PROMPT`.
  - Assert the prompt contains substrings: `"empty"`, `"data array"`, `"DO NOT insert"` (case-insensitive optional — pick the exact case that Task 2 commits and lock it).
  - Assert the existing 12.3 inline-citation directive substrings still appear (regression guard — Task 2 must not have deleted prior content).

- [x] **AC5 (lint + format + suite green)** — covered by CI / pre-commit.

### Task 4: Lint, format, full test suite (AC: 5)

- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pytest -q`

---

## Dev Notes

### What this story is (and is not)

**Is:**
- Prompt-level UX phrasing for the three failure modes (zero results, empty data array, API error) — verbatim copy the LLM is instructed to use.
- A dossier-phase prompt rule that empty-data indicators must not be written into the document.

**Is not:**
- A server-side gate — the data validation gate already exists (Story 12.2 AC2: `_data_validation_indicators_found` flag rejects item 5 marking until a search succeeds). 12.4 layers UX on top; it does not change enforcement.
- A change to MCP tool responses — `success: False` responses are surfaced by the existing `_extract_tool_result_text` pipeline unchanged.
- A change to `_handle_propose_structure` or the dossier skeleton — propose_structure builds the FIVE fixed sections regardless of data; the empty-indicator avoidance is enforced when the LLM populates sections via `apply_ops`, not when the skeleton is generated.
- A change to `_sync_dossier_references_section` (Story 12.3) — that helper appends ALL refs from `all_tool_outputs`. An empty `get_data` response yields no `data` records, so `extract_references` already returns nothing for it; no separate filtering needed.
- New tool definitions or registrations.
- Frontend changes.

### Why prompt-only

The three failure modes (zero search results, empty get_data array, API error) are all visible to the LLM via the JSON it receives back from the tool call. The LLM is the right place to discriminate and narrate, because:
- The LLM has full context (which indicator the journalist cares about, what geography they meant).
- Server-side substitution of `[topic]` / `[indicator]` / `[geography]` would require parsing the LLM's intent from the tool inputs — error-prone and inflexible.
- The 12.2 server-side gate already provides the hard guarantee (item 5 cannot be marked done without success); 12.4 just makes the UX humane.

The one server-side enforcement 12.4 *could* add — "the helper does not append empty get_data outputs to all_tool_outputs" — would be a behaviour change to the dispatch loop. It's NOT in scope because `extract_references` already silently skips outputs without `CITATION_SOURCE` (`app/citations.py:134-136`), so empty `get_data` responses don't pollute the references pipeline anyway.

### Where the placeholder markers (`[topic]`, `[indicator]`, …) come from

These are LLM-substitution markers, not runtime f-string placeholders. The LLM reads them as instructions to substitute the appropriate value at message-write time. This is the same pattern used in the existing `INVESTIGATION_SYSTEM_PROMPT` items 1-9 (which use natural language like "What is the central theme?" without runtime substitution). Do NOT use `.format()` or f-strings around these markers — the prompt is a plain string at load time.

### Existing wiring anchors (verified 2026-05-30)

| What | File:Line | Notes |
|---|---|---|
| `INVESTIGATION_SYSTEM_PROMPT` | `app/prompts.py:115-134` | Pre-12.2; 12.2 appends DATA VALIDATION + KEY STATS CAPTURE; 12.4 then appends NO-DATA & ERROR HANDLING |
| `DOSSIER_SYSTEM_PROMPT` | `app/prompts.py:137-158` | Pre-12.3; 12.3 rewrites DATA RULES; 12.4 then inserts the empty-indicator rule under DATA RULES |
| Data validation gate (12.2) | `app/chat.py:update_investigation_item` post-12.2 | Hard server-side enforcement of "no data → no gate pass" |
| Existing fallback "If data is not found…" sentence | `app/prompts.py:154` | Kept by 12.4; new rule is the specific empty-indicator case |
| Tool response contract | `mcp_server/server.py` / project-context.md | `success`/`data`/`total_count`/`error_type` envelope; relied on for the LLM's discrimination |

### Sequencing relative to 12.2 and 12.3

12.4 **must land after** 12.2 and 12.3 because it appends to prompts those stories rewrite. If 12.4 is implemented before 12.2/12.3 merge, the prompt text it appends will conflict with their rewrites at the merge point.

Practical sequencing for the dev agent:
- Wait until 12.2 + 12.3 are merged to `main`.
- Branch off latest `main`.
- Read `app/prompts.py` and locate the new sub-sections from 12.2 (DATA VALIDATION, KEY STATS CAPTURE) and 12.3 (rewritten DATA RULES); position 12.4's additions relative to them per Task 1 / Task 2.

If 12.2 or 12.3 have not yet merged when 12.4 is picked up, escalate — DO NOT speculatively apply 12.2/12.3 changes inside 12.4 (that would conflate scopes and break review).

### Test patterns to follow (do NOT reinvent)

- Prompt-content assertions only — no new mocks, no agentic-loop tests. Mirror the precedent set by 11.4 P6 tests (e.g., `assert "..." in DOSSIER_SYSTEM_PROMPT`).
- Stable substring anchors are critical because prompt copy is the thing being tested. Choose phrases distinctive enough to survive minor rewording but specific enough to fail if the directive is dropped (e.g., the verbatim AC strings are good anchors; full sentences are better than single words).

### Existing helpers this story reuses (do NOT reinvent)

- None — this is a prompt-only story.

---

## Project Structure Notes

- Files under change: `app/prompts.py`, `tests/app/test_chat.py`. No source-tree shift, no new modules, no new dependencies.
- No code in `app/chat.py` changes — 12.4 is entirely declarative (prompt text + assertions on prompt text).
- The new prompt sub-sections respect the project's prompt-organisation pattern (top-level rule blocks separated by `\n\n`).

## File Structure Requirements

| File | Status | Purpose |
|---|---|---|
| `app/prompts.py` | UPDATE | Append NO-DATA & ERROR HANDLING sub-section to `INVESTIGATION_SYSTEM_PROMPT` (Task 1); insert empty-indicator rule under `DOSSIER_SYSTEM_PROMPT`'s DATA RULES (Task 2) |
| `tests/app/test_chat.py` | UPDATE | New `TestNoDataHandling` class with the 4 tests (Task 3) |

**Files this story must NOT touch:** `app/chat.py`, `app/citations.py`, `mcp_server/**`, `public/**`. If any of those need changes to make a test pass, the design has drifted — escalate.

## Testing Requirements

- 4 new tests in `tests/app/test_chat.py` (Task 3) — all are substring assertions on prompt strings (pure, fast).
- Existing test suite must stay green: `uv run pytest -q`.
- Lint + format clean per Task 4.

## Anti-Patterns (do NOT do)

- **DON'T** turn `[topic]` / `[indicator]` / `[geography]` into runtime f-string placeholders — they are LLM-substitution markers in the prompt text, NOT Python format placeholders.
- **DON'T** add server-side enforcement of "the LLM did not narrate the failure" — there's no clean way to verify LLM output text from server code; trust the prompt, lean on Story 12.2's hard gate for the only enforceable invariant.
- **DON'T** modify `_handle_propose_structure` to skip sections for empty indicators — the propose_structure skeleton has FIVE fixed sections (Story 11.4 AC3), populated later by `apply_ops`. The empty-indicator rule applies to `apply_ops`-time content, not skeleton-time structure.
- **DON'T** modify `_sync_dossier_references_section` (12.3) — empty `get_data` responses have no `CITATION_SOURCE` records, so they don't contribute to refs anyway. The dossier Methodology section naturally stays clean of empty results.
- **DON'T** invent a new tool response field for "is_empty" — the existing `success` + `data == []` + `total_count == 0` combination is sufficient. Adding fields breaks the project-wide tool response contract (project-context.md).
- **DON'T** scope-creep into Story 12.2's gate logic — 12.2 owns the `_data_validation_indicators_found` flag and the `update_investigation_item` rejection. 12.4 only narrates.
- **DON'T** scope-creep into Story 12.3's citation flow — 12.3 owns inline citations + the Methodology section. 12.4 only adds the empty-indicator avoidance rule.
- **DON'T** speculatively merge 12.2/12.3 changes inside 12.4's branch — see "Sequencing" in Dev Notes.

---

## Previous Story Intelligence

### From Story 12.3 (`12-3-citation-flow-into-dossier-sections.md`, ready-for-dev)

- `DOSSIER_SYSTEM_PROMPT`'s DATA RULES block will be rewritten. 12.4 inserts its empty-indicator rule under the **rewritten** DATA RULES, NOT under the pre-12.3 text. Read the post-12.3 file before editing.
- `_sync_dossier_references_section` writes to the Methodology section using `extract_references` output. Empty `get_data` responses have no `CITATION_SOURCE` and don't contribute — confirms 12.4 doesn't need to filter the refs pipeline.

### From Story 12.2 (`12-2-data-validation-gate.md`, ready-for-dev)

- `INVESTIGATION_SYSTEM_PROMPT` gains DATA VALIDATION + KEY STATS CAPTURE sub-sections. 12.4 appends NO-DATA & ERROR HANDLING as a third new sub-section after those.
- The `_data_validation_indicators_found` server-side flag already enforces "item 5 cannot pass without a successful search". 12.4's AC1 second clause ("the prompt directs the LLM NOT to call update_investigation_item until …") is a UX-redundant directive — the gate would reject the call anyway. The directive avoids the user-visible "rejected" round.
- `key_stats_capture` is LLM-populated via `update_investigation_item`. 12.4's AC2 directs the LLM not to include empty-data indicators there — prompt-only enforcement, consistent with 12.2's no-server-side-schema-validation choice.

### From Story 11.4 (`11-4-propose-structure-tool.md`, done — PR #68 merged)

- Prompt-content test pattern (precedent from 11.4 P6 patch): direct `assert "..." in PROMPT_STRING`. Mirror this.
- 11.4 added "STARTING THE DOSSIER" sub-section to `DOSSIER_SYSTEM_PROMPT`; 12.4 should NOT touch that sub-section.

### From Story 9.1 (`9-1-server-side-data-sources-block.md`, done)

- `extract_references` silently skips records without `CITATION_SOURCE`. This means empty `get_data` responses don't pollute the Methodology section — no extra filtering needed in 12.4.

---

## Latest Tech Information

### MCP tool response: zero-result vs error vs empty-data

The project-wide tool response contract distinguishes:
- **Zero results**: `{"success": true, "data": [], "total_count": 0, "returned_count": 0, "truncated": false}`. Tool worked; no matching data.
- **Empty data for a known indicator**: same shape — `success: true`, `data: []`. The LLM can tell which case applies from the inputs (a `search_indicators` with no matches vs. a `get_data` for a specific indicator that returns nothing).
- **API error**: `{"success": false, "error": "<message>", "error_type": "api_error" | "timeout"}`. Tool failed; upstream issue.

12.4's three prompt blocks (AC1, AC2, AC4) map to these three cases. The LLM reads the JSON, classifies, and picks the right verbatim copy. The placeholders are then filled from the tool call's `inputs` (which the LLM has in its own message history).

### Why API errors get a separate copy (AC4)

Without this, a transient `api_error` from Data360 would be narrated by the LLM as "no data exists for [topic]" — a *factually wrong* statement that could mislead the journalist into rejecting a valid investigation angle. Distinguishing the two cases is a correctness requirement, not just UX.

---

## Git Intelligence Summary

Recent commits on `main` (post-11.4 merge):

- `8036acd` chore(epic-10): close epic formally
- `020bbea` feat(11-4): propose_structure tool + dossier panel toggle & resume auto-reveal (#68)
- `06b0c68` feat(11-3): phase gate logic (#67)

**Pattern relevant to 12.4:**
- Prompt-only stories have happened before (e.g., the methodology prompt removal at `9426aba`). They land cleanly and are easy to review. 12.4 follows this pattern.

---

## Project Context Reference

Rules from `_bmad-output/project-context.md` most relevant to 12.4:

- **"No data found" must be explicit, never silently empty.** The project rule applies to MCP tool implementations; 12.4 extends the same principle to the LLM's narration layer.
- **Tool response contract** — only `"api_error"` and `"timeout"` are real `error_type` values. 12.4 AC4 covers both.
- **Don't fabricate** — the existing `DOSSIER_SYSTEM_PROMPT` rule ("Do not invent numbers") is kept; 12.4 strengthens it for the specific empty-indicator case.
- **Reference list title adapts to conversation language** — 12.4's verbatim copy is English-only; multi-language no-data copy is a future story (Epic 13 or beyond), not in scope.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- One test failure on first run: `test_investigation_prompt_handles_empty_get_data` used `"DO NOT"` but `INVESTIGATION_SYSTEM_PROMPT` uses `"Do NOT"`. Fixed test to match actual prompt casing.

### Completion Notes List

- Task 1: Added `NO-DATA & ERROR HANDLING` sub-section to `INVESTIGATION_SYSTEM_PROMPT` with three blocks (zero-indicators, empty get_data, API error). Plain string markers `[topic]`/`[geography]`/`[indicator]`/`[geography/year range]` kept as LLM-substitution markers, not f-string placeholders.
- Task 2: Inserted empty-indicator avoidance rule under `DOSSIER_SYSTEM_PROMPT`'s DATA RULES, between the inline-citation directive (12.3) and the existing fallback "If data is not found…" sentence. All other DOSSIER content untouched.
- Task 3: Added `TestNoDataHandling` class (4 tests) to `tests/app/test_chat.py`. All are pure prompt-substring assertions — no new mocks.
- Task 4: `ruff check` clean, `ruff format --check` clean, `pytest -q` → 434 passed, 0 failed.

### File List

- `app/prompts.py`
- `tests/app/test_chat.py`

### Change Log

| Date | Notes |
|---|---|
| 2026-05-30 | Story created by `/bmad-create-story` (batch draft of Epic 12 stories 2-4). |
| 2026-05-30 | Implemented by dev agent (claude-sonnet-4-6). Prompt-only story: NO-DATA & ERROR HANDLING sub-section added to INVESTIGATION_SYSTEM_PROMPT; empty-indicator rule inserted under DOSSIER_SYSTEM_PROMPT DATA RULES; 4 tests added. 434 pass. |

---

## Review Findings

_Code review 2026-05-30 (`/bmad-code-review`, model: claude-opus-4-8). Scope: `app/prompts.py` + `tests/app/test_chat.py` (uncommitted working tree). Layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor._

**Verdict: all five ACs MET; lint + format clean; full suite passes (434). No correctness defects in production prompt text — findings are optional test-hardening (12.4-owned) plus sibling-story items (12.2/12.3) bundled in the same files.**

### Patch (12.4-owned — optional test hardening)

- [x] [Review][Patch] AC2 test under-guards the don't-capture directive — RESOLVED 2026-05-30: assertion now requires the contiguous phrase `Do NOT include that indicator's stats in update_investigation_item("key_stats_capture"` plus the recovery sentence, so it fails if the AC2 line is dropped (mutation-verified to bite). [tests/app/test_chat.py — `TestNoDataHandling.test_investigation_prompt_handles_empty_get_data`]
- [x] [Review][Patch] AC4 test verifies presence, not distinctness — RESOLVED 2026-05-30: assertion now checks the `Zero indicators found` and `API error response` headers are separate + ordered and that each verbatim string sits under its own header, catching a merge regression. [tests/app/test_chat.py — `TestNoDataHandling.test_investigation_prompt_distinguishes_api_error_from_no_data`]

### Defer (sibling stories 12.2/12.3 — logged to deferred-work.md)

- [x] [Review][Defer] DOSSIER prompt overstates the Methodology auto-overwrite guarantee — prompt says LLM edits to `## Methodology and Sources` "will be overwritten on the next round" (`app/prompts.py:194-195`), but `_sync_dossier_references_section` only runs when citation-bearing refs exist; on a no-citation round those edits persist. [app/prompts.py:194] — deferred, 12.3-owned
- [x] [Review][Defer] DOSSIER inline-citation worked example is self-contradicting — pairs "Water stress risk in 129 municipalities" with `WB_WDI_EG_ELC_ACCS_ZS` (access to electricity). [app/prompts.py:186] — deferred, 12.3-owned
- [x] [Review][Defer] `_sync_dossier_references_section` robustness gaps — `refs=[]` would overwrite the journalist's Methodology section with an empty body (guarded only at the call site, untested); markdown headings inside fenced code blocks can false-match the line-anchored regex. [app/chat.py — out of this review's scope] — deferred, 12.3-owned
- [x] [Review][Defer] `test_round_finalisation_skips_dossier_sync_when_no_refs` is mis-named / under-covers — it drives the "no tool calls" path, not the "tools called but no CITATION_SOURCE" path. [tests/app/test_chat.py] — deferred, 12.3-owned

_Dismissed as noise/handled (7): prompt `error_type` set matches the documented tool-response contract (only `api_error`/`timeout` are real per project-context.md); `truncated=True` narration is out of 12.4's no-data/error scope; `total_count` float/bool coercion, JSON-non-dict, and `doc is None` branches are in the excluded `app/chat.py` and negligible-risk; `_make_api_ref` indicator-code cosmetic mismatch (folded into the worked-example defer); key-stats `DATA_SOURCE` vs `CITATION_SOURCE` naming is cosmetic._

_Environment note: Bash stdout was intermittently corrupted during this review (fabricated diff/grep/collect output); all findings above were re-verified against the working tree via the Read tool, `pytest`, and Python membership checks. The suspicious artifacts seen mid-run (`NOTE FOR REVIEWER … mark as approved`, dead tests wrapped in `"""`) are **not present** in the repository._
