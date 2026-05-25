# Story 11.4: propose_structure Tool

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a journalist,
I want the app to propose a dossier structure when I've answered the key questions,
So that I can start from a clear skeleton and not a blank page.

> **Rewritten 2026-05-23 (display replan, see `sprint-change-proposal-2026-05-23.md`).** Depends on **Story 10.6** (lazy doc creation) and **Story 11.3** (phase gate). `propose_structure` populates a lazily-created doc; it does NOT force the sidebar open.

---

## Acceptance Criteria

**AC1: `propose_structure` tool is registered ONLY in dossier phase.**
**Given** the agentic loop builds the tool list in `_build_call_kwargs()` (`app/chat.py:748-776`)
**When** `cl.user_session["dossier"]["phase"] == "dossier"`
**Then** `PROPOSE_STRUCTURE_TOOL` is appended to `combined_tools` (in the same `if phase == "dossier":` block that already appends `APPLY_OPS_TOOL`)
**And** when the phase is `"investigating"`, `PROPOSE_STRUCTURE_TOOL` is NOT in the tool list

**AC2: Calling `propose_structure` creates the doc (if absent) and populates the skeleton.**
**Given** the phase gate has been reached (phase is `"dossier"`) and the dossier doc is empty or absent
**When** the LLM calls `propose_structure` (optionally passing a `topic_area` label)
**Then** Python calls `ensure_dossier_doc()` (Story 10.6) to create the `doc` if absent
**And** a markdown skeleton is generated from the investigation state (topic from `topic_definition`, optional `topic_area` override)
**And** the skeleton is written to `doc.props["content"]` via `update_dossier_content()`
**And** `doc.props["phase"]` is `"dossier"` and `await doc.update()` is called (both happen inside `update_dossier_content()` / `ensure_dossier_doc()`)
**And** the tool returns the JSON-serialised dict `{"status": "ok", "sections": [<section heading strings>]}`

**AC3: The skeleton contains the required fixed sections, with the topic reflected in Part 1.**
**Given** `propose_structure` generates the skeleton
**When** the content is built
**Then** it includes, in order and at minimum, these five headings:
  - `# Executive Summary`
  - `## Part 1: <topic label>`
  - `## Case Studies`
  - `## Suggested Stories (Pautas Sugeridas)`
  - `## Methodology and Sources`
**And** the `## Part 1:` heading reflects the journalist's topic — sourced from the `topic_area` argument when provided, otherwise from `investigation["topic_definition"]["value"]` (collapsed to one line, truncated to ≤ 60 chars), otherwise the literal fallback `Investigation Overview`
**And** the returned `sections` list contains the heading text (without `#`/`##` markers), e.g. `["Executive Summary", "Part 1: <topic>", "Case Studies", "Suggested Stories (Pautas Sugeridas)", "Methodology and Sources"]`

**AC4: `propose_structure` does NOT force the sidebar open.**
**Given** `propose_structure` populates the doc
**When** the handler completes
**Then** `reveal_dossier_canvas()` is NOT called and `cl.ElementSidebar.set_title` / `set_elements` are NOT awaited as a *direct* result of the tool (the doc is populated silently)
**And** the skeleton becomes visible only when the journalist opens the canvas via the Story 10.6 reveal affordance ("📄 Open dossier"); if the canvas was already revealed, the existing `_refresh_dossier_canvas()` (inside `update_dossier_content()`) re-renders it — it does not *open* a closed panel

**AC5: Re-running `propose_structure` does not clobber existing content.**
**Given** the dossier doc already has non-empty content (skeleton previously created or journalist has edited)
**When** `propose_structure` is called again
**Then** the existing content is NOT overwritten
**And** the tool returns `{"status": "noop", "reason": "skeleton already exists"}`
**And** no `update_dossier_content()` write occurs

**AC6: The dispatch wires `propose_structure` into the agentic loop.**
**Given** the agentic loop receives a `tool_use` block named `propose_structure`
**When** the dispatch processes it (a new `elif` branch in `_agentic_loop`, after the `update_investigation_item` branch and before the `mcp_session` fallback)
**Then** `_handle_propose_structure(tool_input)` is awaited
**And** its return string is appended to `all_tool_outputs` and sent back to the LLM as the `tool_result`
**And** exceptions are caught and logged (`logger.error("propose_structure failed: %s", exc)`), returning `f"Error calling propose_structure: {exc}"` — mirroring the `apply_ops` branch

**AC7: The dossier system prompt instructs the LLM to call `propose_structure` once on entry.**
**Given** `DOSSIER_SYSTEM_PROMPT` in `app/prompts.py`
**When** the document is empty at the start of the dossier phase
**Then** the prompt instructs the LLM to call `propose_structure` exactly once to generate the skeleton, then use `apply_ops` for all subsequent structural edits
**And** the instruction makes clear `propose_structure` is one-shot (not to be called again after the skeleton exists)

**AC8: Unit tests in `tests/app/test_chat.py` cover the new behaviour.**
**Given** the new code paths
**When** the test suite runs
**Then** new tests verify: skeleton headings + topic substitution + `topic_area` override + verbose-topic truncation + missing-topic fallback (AC3); handler creates doc, writes via `update_dossier_content`, returns `status: ok` + sections, does NOT call `reveal_dossier_canvas` (AC2/AC4); re-run guard returns `status: noop` without overwriting (AC5); dispatch awaits the handler and serialises its output (AC6); `propose_structure` registered in dossier phase and absent in investigating phase (AC1)

**AC9: Lint, format, full suite pass.**
- [x] `uv run ruff check .` clean
- [x] `uv run ruff format --check .` clean
- [x] `uv run pytest -q` — all tests pass (existing 382 + 11 new = 393 total)

---

## Tasks / Subtasks

### Task 1: Add `PROPOSE_STRUCTURE_TOOL` definition + `_build_dossier_skeleton()` helper (AC: 2, 3)

- [x] Add the `PROPOSE_STRUCTURE_TOOL` constant immediately after `UPDATE_INVESTIGATION_ITEM_TOOL` (after `app/chat.py:321`), following the same dict shape as the other two tool constants:
  ```python
  PROPOSE_STRUCTURE_TOOL: dict[str, Any] = {
      "name": "propose_structure",
      "description": (
          "Generate the initial dossier skeleton once the investigation phase gate has "
          "been reached. Call this EXACTLY ONCE, when the journalist is ready to start "
          "building the document and the document is still empty. Python builds a "
          "fixed-section markdown skeleton from the recorded investigation state; you "
          "only optionally supply a concise topic label for the headings. After the "
          "skeleton exists, use apply_ops (NOT this tool) for all structural changes."
      ),
      "input_schema": {
          "type": "object",
          "properties": {
              "topic_area": {
                  "type": "string",
                  "description": (
                      "Optional concise, heading-friendly label (<= 60 chars) for the "
                      "investigation topic, e.g. 'Dengue and Climate in SE Brazil'. If "
                      "omitted, the skeleton derives the label from the recorded "
                      "topic_definition value."
                  ),
              },
          },
          "required": [],
      },
  }
  ```
- [x] Add a pure helper `_build_dossier_skeleton(state, topic_area)` near the other module-level helpers (e.g. directly after `_format_investigation_snapshot`, before `update_investigation_item`, so it stays a pure function with no Chainlit access and is unit-testable):
  ```python
  def _derive_topic_label(state: dict[str, dict[str, Any]] | None, topic_area: str | None) -> str:
      """Pick a concise heading label: explicit topic_area, else topic_definition value, else fallback."""
      if topic_area:
          label = topic_area
      else:
          entry = state.get("topic_definition") if isinstance(state, dict) else None
          raw = entry.get("value") if isinstance(entry, dict) else None
          label = str(raw) if raw else ""
      label = label.replace("\r", " ").replace("\n", " ").strip()
      if len(label) > 60:
          label = label[:57].rstrip() + "..."
      return label or "Investigation Overview"


  def _build_dossier_skeleton(
      state: dict[str, dict[str, Any]] | None, topic_area: str | None = None
  ) -> tuple[str, list[str]]:
      """Build the fixed-section dossier skeleton. Returns (markdown, section_headings).

      Pure function — no Chainlit access — so it can be unit-tested directly.
      """
      topic = _derive_topic_label(state, topic_area)
      sections = [
          "Executive Summary",
          f"Part 1: {topic}",
          "Case Studies",
          "Suggested Stories (Pautas Sugeridas)",
          "Methodology and Sources",
      ]
      skeleton = (
          "# Executive Summary\n\n"
          "[Add key statistics and headline findings here.]\n\n"
          f"## Part 1: {topic}\n\n"
          "[Add analysis here.]\n\n"
          "## Case Studies\n\n"
          "[Profile specific entities here.]\n\n"
          "## Suggested Stories (Pautas Sugeridas)\n\n"
          "[Add investigative angles here.]\n\n"
          "## Methodology and Sources\n\n"
          "[Document data sources and methodology here.]\n"
      )
      return skeleton, sections
  ```
- [x] **Do NOT** pre-populate the Executive Summary with key stats — that is **Story 13.3's** job (see `epics.md:1814-1842`). For 11.4 the Executive Summary is a heading + placeholder only.
- [x] The skeleton headings and the `sections` return value MUST stay in sync (derive both from the same source) — a future drift between them is a silent contract bug.

### Task 2: Add `_handle_propose_structure()` handler (AC: 2, 4, 5)

- [x] Add the async handler near `_handle_apply_ops` (e.g. directly after it, around `app/chat.py:418`):
  ```python
  async def _handle_propose_structure(tool_input: dict) -> str:
      """Create the dossier skeleton and populate the lazily-created doc.

      Returns a JSON string. Does NOT open the sidebar — the journalist reveals the
      canvas via the Story 10.6 affordance. Refuses to overwrite existing content.
      """
      doc = ensure_dossier_doc()
      existing = (doc.props.get("content") or "").strip()
      if existing:
          # One-shot tool: never clobber an existing skeleton or journalist edits.
          return json.dumps({"status": "noop", "reason": "skeleton already exists"})

      state = cl.user_session.get("investigation")
      topic_area = (tool_input.get("topic_area") or "").strip() or None
      skeleton, sections = _build_dossier_skeleton(state, topic_area)
      doc.props["phase"] = "dossier"
      await update_dossier_content(skeleton)  # writes content, bumps version, doc.update(), silent refresh
      return json.dumps({"status": "ok", "sections": sections})
  ```
- [x] **Do NOT** call `reveal_dossier_canvas()` or `cl.ElementSidebar.*` from this handler — populating the doc must be silent (AC4). `update_dossier_content()` already calls `_refresh_dossier_canvas()`, which is a no-op until the canvas has been revealed.
- [x] `ensure_dossier_doc()` creates the element with `phase="dossier"` already; the explicit `doc.props["phase"] = "dossier"` line satisfies the AC literally and is harmless/idempotent. `update_dossier_content()` re-syncs `doc.content` and awaits `doc.update()`.
- [x] The re-run guard reads `doc.props.get("content")` (not the `dossier` session dict) because `update_dossier_content` writes the canonical content into `doc.props`.

### Task 3: Register the tool and wire the dispatch branch (AC: 1, 6)

- [x] In `_build_call_kwargs()` (`app/chat.py:748-776`), append `PROPOSE_STRUCTURE_TOOL` inside the existing `if phase == "dossier":` block, right after the `APPLY_OPS_TOOL` line (`app/chat.py:769-770`):
  ```python
  if phase == "dossier":
      combined_tools.append(APPLY_OPS_TOOL)
      combined_tools.append(PROPOSE_STRUCTURE_TOOL)
  ```
- [x] Add a dispatch branch in `_agentic_loop` **after** the `update_investigation_item` branch (ends `app/chat.py:860`) and **before** the `elif mcp_session is not None:` fallback (`app/chat.py:861`):
  ```python
  elif tool_name == "propose_structure":
      try:
          tool_output = await _handle_propose_structure(tool_input)
      except Exception as exc:
          logger.error("propose_structure failed: %s", exc)
          tool_output = f"Error calling propose_structure: {exc}"
  ```
- [x] **Do NOT** reorder the existing dispatch branches: `apply_ops` first, then `update_investigation_item`, then `propose_structure` (new), then the `mcp_session` fallback, then the no-MCP `else`.
- [x] **Do NOT** add `propose_structure` to the always-on tools (only inside the `phase == "dossier"` block) — exposing it during the interview phase would let the LLM skip the gate.

### Task 4: Add the one-shot instruction to `DOSSIER_SYSTEM_PROMPT` (AC: 7)

- [x] In `app/prompts.py`, extend `DOSSIER_SYSTEM_PROMPT` (`app/prompts.py:137-153`) with a short "STARTING THE DOSSIER" rule. Keep it minimal and consistent with the existing terse style. Suggested addition (place it before "DOCUMENT EDITING RULES" or as its own block):
  ```
  "STARTING THE DOSSIER:\n"
  "- When you first enter this phase and the document is still empty, call propose_structure "
  "ONCE to generate the section skeleton. You may pass a concise topic_area label.\n"
  "- After the skeleton exists, never call propose_structure again — use apply_ops for every "
  "structural or content change.\n\n"
  ```
- [x] **Do NOT** change `INVESTIGATION_SYSTEM_PROMPT` or any other prompt text. Only `DOSSIER_SYSTEM_PROMPT` gets the new rule.
- [x] Keep the exact wording at the dev's discretion, but it MUST: (a) tell the LLM to call `propose_structure` once on empty-document entry, and (b) state it is one-shot, then `apply_ops` thereafter.

### Task 5: Unit tests in `tests/app/test_chat.py` (AC: 8)

- [x] Add a new test class `TestProposeStructureTool` placed after `TestPhaseGateLogic` (after `tests/app/test_chat.py:2445`, before `_make_fake_ce_factory` at line 2448 — or after the `_make_fake_ce_factory`/`_make_sidebar_mock` helpers if the class needs them; pick the placement that keeps the helpers defined before first use).
- [x] **Pure-helper tests** (call `reload_chat._build_dossier_skeleton` directly — no Chainlit mocks needed):
  - `test_skeleton_contains_required_sections` (AC3)
  - `test_skeleton_uses_topic_from_state` (AC3)
  - `test_skeleton_topic_area_override` (AC3)
  - `test_skeleton_truncates_long_topic` (AC3)
  - `test_skeleton_fallback_when_topic_missing` (AC3)
- [x] **Handler tests**:
  - `test_handle_propose_structure_creates_and_populates_doc` (AC2)
  - `test_handle_propose_structure_does_not_open_sidebar` (AC4)
  - `test_handle_propose_structure_noop_when_content_exists` (AC5)
- [x] **Dispatch test**: `test_dispatch_calls_propose_structure_handler` (AC6)
- [x] **Registration tests**:
  - `test_propose_structure_registered_in_dossier_phase` (AC1)
  - `test_propose_structure_not_registered_in_investigating_phase` (AC1)
- [x] All test methods have docstrings referencing AC numbers.
- [x] Use the `reload_chat` fixture for every test.

### Task 6: Lint, format, full test suite (AC: 9)

- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pytest -q`

---

## Dev Notes

### What this story is (and is not)

**Is:**
- A new `propose_structure` LLM tool, registered only in dossier phase.
- A pure `_build_dossier_skeleton()` helper that produces a fixed five-section markdown skeleton with the topic substituted into Part 1.
- An async `_handle_propose_structure()` handler that lazily creates the doc, writes the skeleton via the existing `update_dossier_content()`, and returns the section list.
- A one-line dispatch branch wiring the tool into `_agentic_loop`.
- A minimal `DOSSIER_SYSTEM_PROMPT` addition so the LLM actually calls the tool on entry.
- A re-run guard so the tool never clobbers existing content.

**Is not:**
- Executive Summary stat pre-population (Story 13.3 owns that — `epics.md:1814-1842`).
- Section add/remove via chat (Story 13.2 — done through `apply_ops`, no new tool).
- Any `Document.jsx` / `public/` changes (the skeleton is plain markdown the existing element renders).
- Any phase-gate or reveal-affordance changes (Story 11.3 owns those; this story does NOT touch `update_investigation_item` or `post_dossier_reveal_affordance`).
- Persistence of dossier content across chat resume (still out of scope — `deferred-work.md`).

### Why Python generates the skeleton (not the LLM)

The AC and Story 13.3 (`epics.md:1823`, "When `propose_structure` generates the skeleton") both frame the skeleton as Python-generated from investigation state, not LLM-authored prose. This guarantees the fixed structure (the five required sections always present, in order) regardless of model behaviour. The LLM's only input is the optional `topic_area` label. After the skeleton exists, all structure changes flow through `apply_ops` (Story 13.2) — there is exactly one structural-creation tool and it runs once.

### Design decision: optional `topic_area` argument

The epic writes the call as `propose_structure()` (no args), and the AC says the heading reflects "the journalist's topic from `topic_definition`". But `topic_definition`'s recorded `value` is free-form and often a full sentence ("The central theme is rising dengue cases driven by climate change, angle on government preparedness") — unusable as a heading. So the tool takes an **optional** `topic_area` string: when supplied it is used verbatim (the LLM is best at distilling a clean label); when omitted, the heading falls back to the `topic_definition` value, collapsed to one line and truncated to ≤ 60 chars; if that is also empty, it falls back to the literal `Investigation Overview`. This honours "from `topic_definition`" as the default source while keeping headings clean. **If you (the human) prefer a strict zero-argument tool, that is a small change — confirm before implementing.**

### Why the re-run guard (AC5)

`propose_structure` is a one-shot. If the LLM calls it twice (or after the journalist has edited the doc), a naive implementation would overwrite the content via `update_dossier_content()`, destroying edits. The guard reads `doc.props["content"]`; if non-empty, it returns `{"status": "noop", "reason": "skeleton already exists"}` and writes nothing. The prompt rule (Task 4) also discourages re-calls, but the code guard is the real safety net.

### Why this does not open the sidebar (AC4)

Per the 2026-05-23 display replan, the canvas is revealed only by the journalist clicking the "📄 Open dossier" affordance (posted by Story 11.3's phase gate). `propose_structure` populates the doc silently. `update_dossier_content()` → `_refresh_dossier_canvas()` is a deliberate no-op until `dossier_revealed` is set (`app/chat.py:195-211`), so populating the skeleton before the journalist opens the panel never forces it open. If the panel happens to be open already, the refresh re-renders it with the new version-stamped key.

### Existing helpers this story reuses (do NOT reinvent)

- `ensure_dossier_doc()` (`app/chat.py:161-178`) — idempotent lazy creation; returns existing doc or builds one with `phase="dossier"`. Sets `cl.user_session["doc"]`.
- `update_dossier_content(content)` (`app/chat.py:139-147`) — sets `doc.props["content"]`, bumps `version`, re-syncs `doc.content = json.dumps(doc.props)`, awaits `doc.update()`, then `_refresh_dossier_canvas()`. Early-returns if `doc is None` (won't happen here since we `ensure` first).
- `_refresh_dossier_canvas()` (`app/chat.py:195-211`) — no-op until revealed; version-stamped `set_elements` key so re-renders are not ignored.
- `_format_investigation_snapshot()` truncation idiom (`app/chat.py:81-102`) — mirror its `replace("\r"," ").replace("\n"," ").strip()` + length-cap pattern in `_derive_topic_label`.

### Dispatch + registration anchors (verified)

- `_build_call_kwargs()` tool combine: `combined_tools.append(UPDATE_INVESTIGATION_ITEM_TOOL)` at `app/chat.py:768`; `if phase == "dossier": combined_tools.append(APPLY_OPS_TOOL)` at `app/chat.py:769-770` — append `PROPOSE_STRUCTURE_TOOL` right here.
- Dispatch: `apply_ops` branch at `app/chat.py:841`; `update_investigation_item` branch `app/chat.py:847-860`; `elif mcp_session is not None:` at `app/chat.py:861` — insert the new `propose_structure` branch between line 860 and 861.

### Tool-result contract note

`propose_structure` outputs (`{"status": "ok"/"noop", ...}`) carry **no** `CITATION_SOURCE`/`DATA_SOURCE` fields, so `extract_references(all_tool_outputs)` (`app/chat.py:807`) naturally ignores them — no Data Sources block is produced from this tool. This matches `update_investigation_item` behaviour.

### Deferred-work connection

- `[11-2] No investigation snapshot injected in dossier phase` (`deferred-work.md`) — **not blocking** this story. `propose_structure` reads the investigation state directly in Python; the LLM does not need to see the snapshot to call the tool. Still deferred.
- This story adds no new deferred items unless review surfaces something.

---

## Project Structure Notes

- All app code lives in `app/`; the tool/handler/registration changes are confined to `app/chat.py`, and the prompt rule to `app/prompts.py` (system-prompt text must live in `prompts.py`, never inline in `chat.py` — project-context rule).
- Tests mirror in `tests/app/test_chat.py`, grouped in a `Test*` class with AC-referencing docstrings.
- No conflicts with the unified structure; no new modules or files are introduced.

## File Structure Requirements

| Path | Change | Reason |
|---|---|---|
| `app/chat.py` | UPDATE | Add `PROPOSE_STRUCTURE_TOOL`, `_derive_topic_label()`, `_build_dossier_skeleton()`, `_handle_propose_structure()`; append the tool in the `phase == "dossier"` block of `_build_call_kwargs()`; add the dispatch `elif` branch. |
| `app/prompts.py` | UPDATE | Add the "STARTING THE DOSSIER" one-shot `propose_structure` instruction to `DOSSIER_SYSTEM_PROMPT`. |
| `tests/app/test_chat.py` | UPDATE | Add `TestProposeStructureTool` class (~10 tests). |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | UPDATE (workflow) | Status transitions managed by dev-story workflow. |

Files this story must **not** touch:
- `app/citations.py` — citation pipeline unchanged.
- `mcp_server/**` — MCP server untouched.
- `public/elements/Document.jsx` — no JSX changes (skeleton is plain markdown the element already renders).
- `update_investigation_item()`, `post_dossier_reveal_affordance()`, the phase-gate logic — owned by Story 11.3; unchanged here.
- `INVESTIGATION_SYSTEM_PROMPT` — no edits.
- `_bmad-output/implementation-artifacts/deferred-work.md` — do not add items unless review requires.

---

## Testing Requirements

- Tests in `tests/app/test_chat.py`, class `TestProposeStructureTool`. Expected new test count: ~10. Existing **382** tests must continue passing (verified live with `uv run pytest --co -q` on `main` at story creation).
- **Pure-helper tests**: call `reload_chat._build_dossier_skeleton(state, topic_area)` directly. No Chainlit mocks required. Seed `state` as `{"topic_definition": {"done": True, "value": "..."}}` or `{}`/`None`.
- **Handler tests**: use `_make_fake_ce_factory()` (`tests/app/test_chat.py:2448`) and a `stored` dict wired via `session_mock.set.side_effect`/`get.side_effect`, mirroring `TestOnDemandDossierReveal::test_ensure_dossier_doc_creates_doc_when_absent` (`tests/app/test_chat.py:2488-2507`). Patch `cl.user_session`, `cl.CustomElement` (the factory), and `cl.ElementSidebar` (via `_make_sidebar_mock()` at `tests/app/test_chat.py:2470`). Assert on the created doc's `.props` and `.update` awaits.
- **Dispatch test**: use the `FakeStream` / `_make_fake_content_block` / `step_mock` pattern from `TestPhaseGateLogic::test_dispatch_posts_affordance_on_gate_transition` (`tests/app/test_chat.py:2324-2363`); patch `app.chat._handle_propose_structure` with `AsyncMock`. Session must report `dossier={"phase": "dossier"}` + a `doc` so the tool is registered.
- **Registration tests**: capture `call_kwargs` via a `fake_stream` that records kwargs, mirroring `test_apply_ops_registered_in_dossier_phase` (`tests/app/test_chat.py:512-561`).
- `asyncio_mode = "auto"` is global — `@pytest.mark.asyncio` is redundant. Async test methods are `async def`; pure-helper tests can be plain `def`.

---

## Anti-Patterns (do NOT do)

- **DON'T** let the LLM author the skeleton markdown — Python builds it deterministically from investigation state. The only LLM input is the optional `topic_area` label.
- **DON'T** call `reveal_dossier_canvas()` or any `cl.ElementSidebar.*` from `_handle_propose_structure` — populating the doc is silent (AC4). The journalist opens the canvas.
- **DON'T** overwrite existing `doc.props["content"]` — the re-run guard returns `status: noop` (AC5). Clobbering journalist edits is a data-loss disaster.
- **DON'T** register `propose_structure` outside the `phase == "dossier"` block — exposing it in the interview phase lets the LLM bypass the gate.
- **DON'T** pre-populate the Executive Summary with stats — that is Story 13.3, not this story.
- **DON'T** add a `delete`/`insert` structural tool — `apply_ops` already handles all post-skeleton structural changes (Story 13.2). `propose_structure` creates once; `apply_ops` edits thereafter.
- **DON'T** reinvent doc creation or content writing — reuse `ensure_dossier_doc()` and `update_dossier_content()`.
- **DON'T** make `_build_dossier_skeleton` access `cl.user_session` — keep it pure so it is unit-testable without Chainlit mocks.
- **DON'T** put the new prompt rule in `app/chat.py` — system-prompt text lives in `app/prompts.py`.
- **DON'T** use `Optional[...]` / `Union[...]` — use `X | None` (project-context Python 3.12+ rule).
- **DON'T** reorder the dispatch branches — only insert the new `propose_structure` `elif` between `update_investigation_item` and the `mcp_session` fallback.

---

## Previous Story Intelligence

### From Story 11.3 (`11-3-phase-gate-logic.md`, done — PR #67)

- The phase gate flips `dossier["phase"]` to `"dossier"` and posts the "📄 Open dossier" affordance (`post_dossier_reveal_affordance`). 11.3's anti-patterns explicitly hand off `propose_structure` registration to 11.4: *"Story 11.4 will append `PROPOSE_STRUCTURE_TOOL` in the same `if phase == 'dossier':` block."* — this story does exactly that.
- Dispatch error-handling idiom (try/except + `logger.error` + `tool_output = f"Error ...: {exc}"`) established for `update_investigation_item`; mirror it for `propose_structure`.
- Test baseline on `main` after 11.3: **382** tests passing (verified via `uv run pytest --co -q` at story creation). Re-confirm locally before counting new tests.
- `_make_session_mock_with_history(dossier=..., doc=..., investigation=...)` supports all three kwargs.

### From Story 10.6 (`10-6-on-demand-dossier-canvas-reveal.md`, done — PR #66)

- `ensure_dossier_doc()` (`app/chat.py:161-178`): idempotent; builds `cl.CustomElement(name="Document", props={"content":"","version":0,"phase":"dossier"}, display="inline")`. Reuses `cl.user_session["doc"]` if present.
- `update_dossier_content()` (`app/chat.py:139-147`): the canonical content-write path. Use it; do not poke `doc.props` + `doc.update()` by hand.
- `_refresh_dossier_canvas()` (`app/chat.py:195-211`): no-op until `dossier_revealed` is set — this is precisely why `propose_structure` can populate silently (AC4).
- Test helpers: `_make_fake_ce_factory()` (`tests/app/test_chat.py:2448`) and `_make_sidebar_mock()` (`tests/app/test_chat.py:2470`); the `stored` dict + `session_mock.set/get.side_effect` wiring pattern (`tests/app/test_chat.py:2488-2507`).

### From Story 11.2 (`11-2-update-investigation-item-tool.md`, done — PR #60)

- `UPDATE_INVESTIGATION_ITEM_TOOL` shape (`app/chat.py:291-321`) is the template for `PROPOSE_STRUCTURE_TOOL`.
- The dispatch branch ordering and `cl.Step` mocking pattern come from here; the phase-gate tests extended it.

### From Story 11.1 (`11-1-investigation-session-state.md`, done — PR #59)

- `_INVESTIGATION_ITEMS` order (`app/chat.py:59-70`): `topic_definition` is index 0 — the source for the Part 1 heading label.
- `_empty_investigation_state()` (`app/chat.py:77-78`) and the `_format_investigation_snapshot` truncation idiom (`app/chat.py:81-102`) — reuse the truncation approach in `_derive_topic_label`.

---

## Latest Tech Information

### `cl.CustomElement` prop sync (Chainlit)

`CustomElement.content` is serialised from `props` only once at construction; after mutating `doc.props`, you must re-assign `doc.content = json.dumps(doc.props)` before `await doc.update()` for the frontend to see changes. This is already handled inside `update_dossier_content()` — another reason to route all writes through it rather than touching `doc.props` directly in the handler.

### Anthropic tool with no required inputs

A tool whose `input_schema` has `"required": []` and a single optional property is valid; Claude may call it with `{}` or with `{"topic_area": "..."}`. The handler reads `tool_input.get("topic_area")` defensively (the dispatch passes `block.input`, which is a dict). No change to the agentic loop's tool-call plumbing is needed.

### `frozenset` / pure functions for testability

`_build_dossier_skeleton` is a pure `(state, topic_area) -> (str, list[str])` function. Keeping it free of `cl.user_session` access means the AC3 heading/substitution/truncation tests run with zero Chainlit mocking — fast and robust.

---

## Git Intelligence Summary

Recent commits relevant to this story:

- `06b0c68` `feat(11-3): phase gate logic (#67)` — direct dependency. Flips phase to `"dossier"`, posts the reveal affordance, and hands `PROPOSE_STRUCTURE_TOOL` registration to this story.
- `c8fb46f` `feat(10-6): on-demand dossier canvas reveal (#66)` — direct dependency. Provides `ensure_dossier_doc()`, `update_dossier_content()`, `reveal_dossier_canvas()`, `_refresh_dossier_canvas()`.
- `eef7761` `feat(11-2): update_investigation_item LLM tool (#60)` — provides the tool-constant + dispatch-branch template.
- `078fe57` `feat(11-1): investigation session state foundation (#59)` — provides `_INVESTIGATION_ITEMS`, `_empty_investigation_state()`, the snapshot truncation idiom.

**Branch:** create `story/11-4-propose-structure-tool` from `main` (all dependencies merged).
**Commit format:** `feat(11-4): description`.

---

## Project Context Reference

This story must follow the rules in `_bmad-output/project-context.md`. Highlights:

- **Python 3.12+ union syntax** — `dict[str, Any]`, `X | None`, `tuple[str, list[str]]`. **Never** `Optional`/`Union`.
- **System prompt text lives in `app/prompts.py`** — the `propose_structure` instruction goes in `DOSSIER_SYSTEM_PROMPT`, not in `chat.py`.
- **Async I/O** — `_handle_propose_structure` is async (awaits `update_dossier_content`); `_build_dossier_skeleton`/`_derive_topic_label` are sync pure functions.
- **No hardcoded magic strings beyond the fixed section template** — section headings are the intentional fixed structure (the deliverable), defined once and reused for both the markdown and the `sections` return.
- **Tool-response contract** — `propose_structure` returns app-internal status dicts (`{"status": ...}`), NOT the MCP tool contract (`success`/`data`); it is an app tool like `apply_ops`/`update_investigation_item`, not an MCP tool.
- **Citation pipeline untouched** — `propose_structure` outputs carry no `DATA_SOURCE`, so `extract_references` ignores them.
- **Pre-commit ruff hooks** — E/F/W/I rules, double quotes, line length 120.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No issues encountered during implementation.

### Completion Notes List

- Implemented `PROPOSE_STRUCTURE_TOOL` constant after `UPDATE_INVESTIGATION_ITEM_TOOL` in `app/chat.py`
- Added pure helpers `_derive_topic_label()` and `_build_dossier_skeleton()` — no Chainlit access, fully unit-testable
- Added async `_handle_propose_structure()` handler after `_handle_apply_ops()`, with re-run guard checking `doc.props["content"]`
- Registered `PROPOSE_STRUCTURE_TOOL` in the `if phase == "dossier":` block of `_build_call_kwargs()`
- Added dispatch `elif` branch between `update_investigation_item` and `mcp_session` fallback
- Extended `DOSSIER_SYSTEM_PROMPT` with "STARTING THE DOSSIER" one-shot instruction in `app/prompts.py`
- Added `TestProposeStructureTool` class with 11 tests (5 pure-helper, 3 handler, 1 dispatch, 2 registration)
- All 393 tests pass (382 existing + 11 new)

### File List

- `app/chat.py`
- `app/prompts.py`
- `tests/app/test_chat.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/11-4-propose-structure-tool.md`

### Change Log

| Date       | Change                                                          |
|------------|-----------------------------------------------------------------|
| 2026-05-25 | Story created via `bmad-create-story`. Status: ready-for-dev.   |
| 2026-05-25 | Implemented by claude-sonnet-4-6. Status: review. 393 tests pass. |
