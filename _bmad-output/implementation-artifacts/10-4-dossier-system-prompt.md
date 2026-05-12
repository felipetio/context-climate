# Story 10.4: Dossier Phase System Prompt

Status: ready

## Story

As a developer,
I want phase-aware system prompts that govern LLM behavior in investigation and dossier modes,
So that the LLM asks short questions during investigation and edits the document surgically during dossier building.

---

## Acceptance Criteria

**AC1:** Given `app/prompts.py`, when this story is complete, then `INVESTIGATION_SYSTEM_PROMPT` is defined as a module-level constant with the instructions from the Dev Notes verbatim.

**AC2:** Given `app/prompts.py`, when this story is complete, then `DOSSIER_SYSTEM_PROMPT` is defined as a module-level constant with the instructions from the Dev Notes verbatim.

**AC3:** Given the session is in `"investigating"` phase, when `_agentic_loop()` builds the system prompt, then `INVESTIGATION_SYSTEM_PROMPT` is used.

**AC4:** Given the session is in `"dossier"` phase, when `_agentic_loop()` builds the system prompt, then `DOSSIER_SYSTEM_PROMPT` is used, prefixed with the current document state as a system note: `[Current document (v{version}):\n{content}\n]`.

**AC5:** Given the session is in `"dossier"` phase, when `_agentic_loop()` builds the tool list for the Anthropic API call, then `APPLY_OPS_TOOL` (from Story 10.3) is included.

**AC6:** Given the session is in `"investigating"` phase, when `_agentic_loop()` builds the tool list, then `APPLY_OPS_TOOL` is NOT included (it is not available to the LLM yet).

**AC7:** Given `tests/app/test_prompts.py`, when this story is complete, then new tests verify:
- `INVESTIGATION_SYSTEM_PROMPT` contains "one question at a time"
- `INVESTIGATION_SYSTEM_PROMPT` does not mention `apply_ops`
- `DOSSIER_SYSTEM_PROMPT` contains "apply_ops"
- `DOSSIER_SYSTEM_PROMPT` contains "never output the document inline"

---

## Tasks / Subtasks

### Task 1: Add `INVESTIGATION_SYSTEM_PROMPT` to `app/prompts.py` (AC: #1)

- [ ] Add constant after existing prompts (do not modify existing `_BASE_SYSTEM_PROMPT`)
- [ ] Content: see Dev Notes below

### Task 2: Add `DOSSIER_SYSTEM_PROMPT` to `app/prompts.py` (AC: #2)

- [ ] Add constant below `INVESTIGATION_SYSTEM_PROMPT`
- [ ] Content: see Dev Notes below

### Task 3: Update `_agentic_loop()` in `app/chat.py` for phase-aware prompt selection (AC: #3, #4)

- [ ] At the start of `_agentic_loop()`, read phase: `phase = cl.user_session.get("dossier", {}).get("phase", "investigating")`
- [ ] Select system prompt:
  ```python
  if phase == "dossier":
      doc = cl.user_session.get("doc")
      version = doc.props.get("version", 0)
      content = doc.props.get("content", "")
      doc_note = f"[Current document (v{version}):\n{content}\n]\n\n"
      system = doc_note + DOSSIER_SYSTEM_PROMPT
  else:
      system = INVESTIGATION_SYSTEM_PROMPT
  ```
- [ ] Replace the existing system prompt construction with this phase-aware version
- [ ] Import `INVESTIGATION_SYSTEM_PROMPT`, `DOSSIER_SYSTEM_PROMPT` from `app.prompts`

### Task 4: Phase-aware tool list (AC: #5, #6)

- [ ] In `_agentic_loop()`, build the tool list conditionally:
  ```python
  tools = list(MCP_TOOLS)  # existing MCP tools always available
  if phase == "dossier":
      tools.append(APPLY_OPS_TOOL)
  ```
- [ ] Ensure `APPLY_OPS_TOOL` is imported from where it was defined in Story 10.3

### Task 5: Add tests to `tests/app/test_prompts.py` (AC: #7)

- [ ] Add `TestDossierPrompts` test class:
  - `test_investigation_prompt_asks_one_question_at_a_time`: assert "one question at a time" in `INVESTIGATION_SYSTEM_PROMPT`
  - `test_investigation_prompt_no_apply_ops`: assert "apply_ops" not in `INVESTIGATION_SYSTEM_PROMPT`
  - `test_dossier_prompt_uses_apply_ops`: assert "apply_ops" in `DOSSIER_SYSTEM_PROMPT`
  - `test_dossier_prompt_no_inline_output`: assert "never output" in `DOSSIER_SYSTEM_PROMPT` (or equivalent phrase from the prompt text)

### Task 6: Run full test suite and linter (AC: all)

- [ ] `uv run pytest -v` — zero failures
- [ ] `uv run ruff check . && uv run ruff format .` — clean

---

## Dev Notes

### INVESTIGATION_SYSTEM_PROMPT (use verbatim)

```python
INVESTIGATION_SYSTEM_PROMPT = (
    "You are a journalist dossier assistant. Your job is to understand the journalist's "
    "investigation topic before building any document.\n\n"
    "INTERVIEW RULES:\n"
    "- Ask one short question at a time. Never ask multiple questions in one message.\n"
    "- Keep your replies concise (1-3 sentences max). Do not explain what you are doing.\n"
    "- Never output document content, outlines, or draft text in chat.\n"
    "- Call update_investigation_item as soon as you have a clear answer for an item.\n"
    "- When items 1-5 are complete, call propose_structure to generate the dossier skeleton.\n\n"
    "INVESTIGATION CHECKLIST (guide the conversation toward these, in order):\n"
    "1. topic_definition: What is the central theme and editorial angle?\n"
    "2. geography_scope: What geography? (country, state, region, municipality?)\n"
    "3. time_range: Current snapshot, historical trend, or future projection?\n"
    "4. target_audience: Who will read this dossier? (newsroom, NGO, policymakers?)\n"
    "5. data_sources_validation: Run search_indicators to confirm data exists for this topic.\n"
    "6. key_stats_capture: What are the 3-5 most important numbers?\n"
    "7. narrative_structure: What are the main story sections?\n"
    "8. case_studies: Which specific entities (municipalities, regions, countries) to profile?\n"
    "9. story_pitches: What paradoxes or anomalies suggest investigative angles?\n"
    "10. methodology: What are the primary data sources and their limitations?\n"
)
```

### DOSSIER_SYSTEM_PROMPT (use verbatim)

```python
DOSSIER_SYSTEM_PROMPT = (
    "You are a journalist dossier assistant building a structured markdown document "
    "collaboratively with a journalist.\n\n"
    "DOCUMENT EDITING RULES:\n"
    "- Never output the document content inline in chat. The document lives in the right panel.\n"
    "- Always edit the document by calling the apply_ops tool with surgical ops.\n"
    "- Use small ops. Quote anchor text exactly as it appears, including punctuation and whitespace.\n"
    "- If the document is empty or a section is empty, use the append op.\n"
    "- Keep chat replies short (1-3 sentences). The work happens in the document.\n\n"
    "DATA RULES:\n"
    "- Use search_indicators and get_data to ground every factual claim in real data.\n"
    "- Include the DATA_SOURCE value inline when inserting data facts.\n"
    "- If data is not found for a claim, say so explicitly. Do not invent numbers.\n\n"
    "DOSSIER STRUCTURE:\n"
    "- Follow the existing document structure. Do not restructure unless the journalist asks.\n"
    "- Pauta Sugerida callouts use blockquote format: > **PAUTA SUGERIDA** — [angle headline]. [1-2 sentences]\n"
)
```

### System Prompt Assembly for Dossier Phase

The document note is prepended so the LLM always sees the latest state, including any user edits made directly in the canvas:

```python
doc_note = f"[Current document (v{version}):\n{content}\n]\n\n"
system = doc_note + DOSSIER_SYSTEM_PROMPT
```

This approach means the LLM never needs to "remember" the document — it's always in the system prompt. For large documents (>10k tokens), consider truncating the document note to the last N lines as a future optimization.

### What NOT to Change

- Existing `_BASE_SYSTEM_PROMPT` — untouched; it's used for the non-dossier conversational mode
- `app/citations.py` — no changes
- `mcp_server/` — no changes
- The dossier session MCP tools (search_indicators, get_data, etc.) are passed from Epic 1 and remain unchanged

### Phase Determination

The phase lives in `cl.user_session["dossier"]["phase"]`. Default is `"investigating"`. It transitions to `"dossier"` in Epic 11 (Story 11.3). In this Epic 10 story, the transition never happens (no `propose_structure` tool yet), so the dossier system prompt can be manually tested by temporarily hardcoding `phase = "dossier"` during development.

### File Changes

**Files to modify:**
- `app/prompts.py` — add `INVESTIGATION_SYSTEM_PROMPT`, `DOSSIER_SYSTEM_PROMPT`
- `app/chat.py` — update `_agentic_loop()` for phase-aware prompt + tool list selection
- `tests/app/test_prompts.py` — add `TestDossierPrompts`

**Files NOT to touch:**
- `mcp_server/` — no changes
- `app/citations.py` — no changes
- `app/config.py` — no new settings needed

### Anti-Patterns

- **DON'T** modify `_BASE_SYSTEM_PROMPT` — it's used for the existing conversational (non-dossier) mode
- **DON'T** include em dashes in the prompt text — use commas or parentheses (user preference)
- **DON'T** put the document content at the end of the system prompt — put it at the beginning so the model attends to it first
- **DON'T** add `apply_ops` to the investigating phase tool list — it must not be available before the dossier exists
- **DON'T** use `Optional[X]` — use `X | None`

### References

- Felipe's original technical prompt (party mode conversation, 2026-05-07) — system prompt content source
- `_bmad-output/planning-artifacts/epics.md#Story 10.4`
- `app/prompts.py` — existing prompt structure to preserve
- `app/chat.py#_agentic_loop` — integration point (tool list and system prompt assembly)
- Story 10.3 (`APPLY_OPS_TOOL`) — imported here for the dossier tool list
- `_bmad-output/implementation-artifacts/epic-9-retrospective-pre-redesign.md` — lessons about LLM prompt reliability (keep instructions short and concrete)

---

## Dev Agent Record

### Agent Model Used

_To be filled on implementation_

### Completion Notes

_To be filled on implementation_

### File List

_To be filled on implementation_
