# Story 10.6: On-Demand Dossier Canvas Reveal

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a journalist,
I want the dossier panel to appear only once my investigation has enough context,
so that I'm not faced with a blank panel at the start of every chat.

**Context:** PR #64 (`1969971`) removed the always-open ElementSidebar canvas and its reopen affordances (`open_dossier_canvas`, `reopen_dossier_canvas`, `/dossier` command, "Show dossier" button) as rejected UX. That left the dossier feature **unreachable**: `cl.user_session["doc"]` is never created, so `update_dossier_content()` no-ops and `_handle_apply_ops()` always returns `"Error: dossier canvas is not open"`. This story re-establishes the display surface using the **surviving** `apply_ops`/`update_dossier_content` engine and `Document.jsx` (both retained for reuse), but with a **lazy, on-demand** model: no canvas at chat start, created only when needed, revealed only via an explicit one-click affordance after the phase gate.

This is the unblocking story for Epic 10 → 11. Stories 11.3 (phase gate) and 11.4 (`propose_structure`) depend on the helpers built here.

## Acceptance Criteria

**AC1: No canvas at chat start or on resume.**
- **Given** a new or resumed chat session
- **When** `@cl.on_chat_start` / `@cl.on_chat_resume` fires
- **Then** dossier + investigation session state is initialized BUT no `cl.ElementSidebar` is opened and no `doc` element is created
- **And** the right panel is absent during `"investigating"` phase.

> Already true post-#64 (the open calls were removed). AC1's deliverable for this story is a **regression test** that locks the behavior in, plus confirmation that the new helpers do **not** reintroduce an open at start/resume.

**AC2: Lazy doc creation helper.**
- **Given** `app/chat.py`
- **When** `ensure_dossier_doc()` is called
- **Then** it creates `cl.user_session["doc"]` as a `Document` `CustomElement` (`{content: "", version: 0, phase: "dossier"}`) if absent, and reuses the existing element if present (idempotent — same reference, no orphaned elements)
- **And** it does NOT open the sidebar.

**AC3: On-demand reveal helper.**
- **Given** a `doc` exists (or can be ensured)
- **When** `reveal_dossier_canvas()` is called
- **Then** `cl.ElementSidebar` opens (title "Dossier") showing the current `doc`, preserving `content`/`version`/`phase`
- **And** repeated calls do not orphan elements (idempotent).

**AC4: Reveal is triggered by an explicit affordance, post-gate only.**
- **Given** the session transitions to `"dossier"` phase (the *trigger* is driven by Story 11.3)
- **When** the reveal affordance is posted to chat
- **Then** a single chat affordance (`cl.Action` labeled "📄 Open dossier") is shown, and clicking it calls `reveal_dossier_canvas()`
- **And** there is NO auto-open at start/resume, NO `/dossier` command, and NO persistent "Show dossier" button during investigation.

> **Scope boundary (read carefully):** This story owns the reveal **mechanism** — the `cl.Action` affordance, the `@cl.action_callback` handler, and a `post_dossier_reveal_affordance()` helper that sends it. The *decision to post* it (detecting items 1-5 done at the gate) is **Story 11.3**. See Dev Notes → "Scope boundary with Story 11.3".

**AC5: Engine reuse.**
- **Given** the `doc` has been created via `ensure_dossier_doc()`
- **When** `_handle_apply_ops()` / `update_dossier_content()` run
- **Then** they operate on that `doc` and no longer return `"Error: dossier canvas is not open"`
- **And** `Document.jsx` is reused **unchanged** as the renderer (its `"investigating"` placeholder branch is unreachable because the panel is never shown during investigation and the doc is created with `phase: "dossier"`).

**AC6: Manual verification (VPS).**
- Fresh chat → no panel.
- Trigger the reveal affordance → "📄 Open dossier" appears in chat.
- Click → the (empty or populated) `Document` canvas renders in the right panel in editable mode (not the placeholder).
- A subsequent `apply_ops` / `update_dossier_content` call streams edits into the panel.

> The full gate-driven chain ("complete items 1-5 → affordance appears automatically") is only exercisable once Story 11.3 wires the gate. For this story in isolation, verify by temporarily triggering `post_dossier_reveal_affordance()` (see Dev Notes → "Verifying AC6 before 11.3 exists").

## Tasks / Subtasks

- [x] **Task 1 — `ensure_dossier_doc()` lazy creation helper (AC2, AC5)**
  - [x] Add `def ensure_dossier_doc() -> cl.CustomElement:` in `app/chat.py` in the "On-demand canvas reveal (Story 10.6)" section (right after `update_dossier_content`).
  - [x] If `cl.user_session.get("doc")` is not None, return it unchanged (idempotent — do NOT create a second element).
  - [x] Otherwise create `doc = cl.CustomElement(name="Document", props={"content": "", "version": 0, "phase": "dossier"}, display="inline")`, store via `cl.user_session.set("doc", doc)`, and return it.
  - [x] Do NOT call `cl.ElementSidebar.*` here — creation must not reveal the panel.
  - [x] Note: `props["phase"]` is `"dossier"` (NOT `"investigating"`) so `Document.jsx` renders the editable view, never the placeholder (AC5).

- [x] **Task 2 — `reveal_dossier_canvas()` on-demand reveal helper (AC3)**
  - [x] Add `async def reveal_dossier_canvas() -> None:` in `app/chat.py` next to `ensure_dossier_doc()`.
  - [x] Call `ensure_dossier_doc()` first (so reveal is safe even if no doc exists yet), capturing the returned `doc`.
  - [x] `await cl.ElementSidebar.set_title("Dossier")` then `await cl.ElementSidebar.set_elements([doc], key="dossier-canvas")` — reuse the **same** `doc` reference; never construct a new `CustomElement` on reveal (AC3 idempotency / anti-pattern).

- [x] **Task 3 — Reveal affordance + action callback (AC4)**
  - [x] Add `async def post_dossier_reveal_affordance() -> None:` that sends a single `cl.Message` carrying `actions=[cl.Action(name="reveal_dossier", label="📄 Open dossier", payload={})]` (content "Your dossier is ready."). Story 11.3 will call this at the gate.
  - [x] Add `@cl.action_callback("reveal_dossier")` decorated handler `async def on_reveal_dossier(action: cl.Action) -> None:` that calls `await reveal_dossier_canvas()` then `await action.remove()` so the one-shot affordance does not linger.
  - [x] Do NOT register a `/dossier` command, `cl.set_commands`, or a persistent welcome button (explicit AC4 / anti-pattern — these were the rejected 10.5 surfaces).

- [x] **Task 4 — Confirm engine reuse, no "canvas not open" once ensured (AC5)**
  - [x] Verified `_handle_apply_ops` and `update_dossier_content` operate on the `doc` created by `ensure_dossier_doc()` — they already read `cl.user_session.get("doc")`; no change to their bodies required.
  - [x] Kept the `doc is None` guard in `_handle_apply_ops` — still the correct fallback when the LLM calls `apply_ops` before any doc exists (covered by `test_handle_apply_ops_without_doc_still_reports_not_open`).
  - [x] `Document.jsx` reused **unchanged** — not edited.

- [x] **Task 5 — Confirm AC1 (no canvas at start/resume) and lock with regression tests**
  - [x] Confirmed `on_chat_start` and `on_chat_resume` only initialize the `dossier`/`investigation` session dicts; neither calls `ensure_dossier_doc()`, `reveal_dossier_canvas()`, nor any `cl.ElementSidebar.*`.
  - [x] No changes to the welcome message — confirmed it carries no reveal/show action (AC4) via `test_on_chat_start_welcome_message_has_no_reveal_action`.

- [x] **Task 6 — Tests (`tests/app/test_chat.py`)**
  - [x] New test class `class TestOnDemandDossierReveal:` using the `reload_chat` fixture and a `stored`-dict session mock (so `set` → `get` round-trips, required for the lazy-creation flow). Added `_make_fake_ce_factory`, `_make_sidebar_mock`, and `_failing_mcp_client` helpers.
  - [x] AC2: creation + idempotency + no sidebar (`test_ensure_dossier_doc_creates_doc_when_absent`, `test_ensure_dossier_doc_is_idempotent`).
  - [x] AC3: opens sidebar titled "Dossier" with `[doc]`/`key="dossier-canvas"`; reuse with no new element (`test_reveal_dossier_canvas_opens_sidebar`, `test_reveal_dossier_canvas_reuses_existing_doc`).
  - [x] AC4: callback triggers reveal; affordance posts a single action (`test_reveal_dossier_action_callback_triggers_reveal`, `test_post_dossier_reveal_affordance_sends_single_action`).
  - [x] AC1 regression: start/resume create no doc and open no sidebar; welcome has no action (3 tests).
  - [x] AC5: `apply_ops` succeeds after `ensure_dossier_doc()`; guard preserved when no doc (`test_apply_ops_succeeds_after_ensure_dossier_doc`, `test_handle_apply_ops_without_doc_still_reports_not_open`).
  - [x] Ran `uv run python -m pytest tests/app/test_chat.py::TestOnDemandDossierReveal` (11 passed) and the full suite (370 passed).

- [x] **Task 7 — Manual verification (AC6)** — **performed live on the VPS** (`https://felipet.io/demos/context-climate/`) via temporary `/reveal-test`, `/fill-test`, `/ops-test` triggers (since removed). Fresh chat → no panel; trigger → "📄 Open dossier" affordance; click → panel renders editable Document; `update_dossier_content` and `apply_ops` both stream into the panel with the version incrementing (v0→v1→v3). See Completion Notes.
  - [x] **Surfaced and fixed a latent display bug** (see Task 9). Temp triggers removed; app restarted clean.

- [x] **Task 9 — Fix sidebar update propagation (surfaced by AC6 verification)**
  - [x] Root cause: Chainlit's `ElementSidebar` renders from its own snapshot taken at `set_elements` time. `doc.update()` only updates the global element store (sidebar-hosted elements don't re-render), and `set_elements` with an unchanged `key` is a no-op (per Chainlit `sidebar.py` docstring). So the reused 10.2/10.3 engine never refreshed the sidebar — the panel froze at v0/empty.
  - [x] Fix: `reveal_dossier_canvas()` uses a **version-stamped key** (`dossier-v{version}`) and sets a `dossier_revealed` session flag; added `_refresh_dossier_canvas()` (re-runs `set_elements` with the version-stamped key, no-op until revealed); `update_dossier_content()` and `_handle_apply_ops()` (per op + on rollback) call it. Updates before reveal mutate the doc silently without force-opening the panel (AC4 / Story 11.4).
  - [x] Tests added: refresh-when-revealed, no-refresh-when-not-revealed, `_refresh` no-op when not revealed, per-op streaming keys.

- [x] **Task 8 — Quality gates**
  - [x] `uv run ruff check .` → All checks passed. `uv run ruff format` → clean (test file reformatted once).

## Dev Notes

### Current state of the files you're touching

- **`app/chat.py`** — Post-#64, the dossier section (`app/chat.py:54-322`) contains: `_INVESTIGATION_ITEMS`, `_empty_investigation_state`, `_format_investigation_snapshot`, `update_investigation_item` (returns `phase_gate_reached: False` hardcoded at `:127` — that's Story 11.3, NOT this story), `update_dossier_content` (`:131`, guards `doc is None`), the `APPLY_OPS_TOOL`/`UPDATE_INVESTIGATION_ITEM_TOOL` schemas, `apply_single_op` (`:230`, pure string transform), and `_handle_apply_ops` (`:280`, guards `doc is None` → returns `"Error: dossier canvas is not open"`). **There is currently no helper that creates `doc` and no helper that opens the sidebar** — that's the gap this story closes.
- `on_chat_start` (`app/chat.py:521`) and `on_chat_resume` (`app/chat.py:469`) both init `cl.user_session["dossier"] = {"phase": "investigating", "content": "", "version": 0}` and `cl.user_session["investigation"] = _empty_investigation_state()`. Neither creates a doc or opens the sidebar. **Preserve this.**
- `_agentic_loop._build_call_kwargs` (`app/chat.py:652-680`) selects `DOSSIER_SYSTEM_PROMPT` vs `INVESTIGATION_SYSTEM_PROMPT` on `cl.user_session["dossier"]["phase"]`, injects the doc snapshot in dossier phase, and gates `APPLY_OPS_TOOL` on dossier phase. **Do not change phase-selection logic here** — session-`phase` transition is Story 11.3. This story only deals with the `doc` element + sidebar, which are independent of the session `phase` field.
- **`public/elements/Document.jsx`** — reads `props.{content, version, phase}`. If `phase === "investigating"` → placeholder card; else → editable Edit/View card with version badge and a 400ms-debounced `updateElement(...)` sync-back. **Reuse unchanged.** Because `ensure_dossier_doc()` sets `props.phase = "dossier"`, the placeholder branch is never hit (AC5).

### Exact template for the new helpers (from the PR #64 removal — adapt, don't copy verbatim)

PR #64 removed `open_dossier_canvas`/`reopen_dossier_canvas`. Their shape is the proven template for this story's helpers. The critical differences for 10.6:

```python
# REMOVED in #64 (template only — DO NOT restore as-is):
async def open_dossier_canvas() -> None:
    if cl.user_session.get("doc") is not None:
        await reopen_dossier_canvas(); return
    doc = cl.CustomElement(name="Document",
        props={"content": "", "version": 0, "phase": "investigating"},  # <-- 10.6 uses "dossier"
        display="inline")
    await cl.ElementSidebar.set_title("Dossier")                        # <-- 10.6: NOT in ensure_*, only in reveal_*
    await cl.ElementSidebar.set_elements([doc], key="dossier-canvas")   # <-- 10.6: NOT in ensure_*, only in reveal_*
    cl.user_session.set("doc", doc)
```

Differences in 10.6:
1. **Split creation from reveal.** `ensure_dossier_doc()` = create-only (no sidebar). `reveal_dossier_canvas()` = sidebar-only (ensures doc first).
2. **`phase: "dossier"`** at creation (was `"investigating"`), so the renderer shows the editable view.
3. **No `_register_dossier_commands`, no `/dossier`, no welcome button.**

### CustomElement re-sync gotcha (established in Story 10.2/10.3)

`cl.CustomElement.content` (the JSON-serialized props the frontend reads) is set **once at construction** from `props`. Mutating `doc.props[...]` afterward does NOT auto-resync — that's why `update_dossier_content` (`:137`) and `_handle_apply_ops` (`:304`,`:310`) explicitly do `doc.content = json.dumps(doc.props)` before `await doc.update()`. **For `ensure_dossier_doc()` you do NOT need a manual resync** — you're constructing fresh with `props=`, so `content` is serialized correctly at birth. Only mutations-in-place need the resync, and those already exist in the engine you're reusing.

### Scope boundary with Story 11.3 / 11.4 (do not over-build)

- **This story (10.6) = mechanism:** `ensure_dossier_doc()`, `reveal_dossier_canvas()`, the `reveal_dossier` `cl.Action` + `@cl.action_callback`, and `post_dossier_reveal_affordance()`.
- **Story 11.3 = trigger:** flips `cl.user_session["dossier"]["phase"]` to `"dossier"`, returns `phase_gate_reached: True` (replacing the hardcoded `False` at `app/chat.py:127`), and **calls `post_dossier_reveal_affordance()`** when items 1-5 complete. **Do NOT implement the gate logic or change `update_investigation_item`'s return in this story.**
- **Story 11.4 = populate:** `propose_structure` calls `ensure_dossier_doc()` then `update_dossier_content(skeleton)`. **Do NOT implement `propose_structure` here** — just make sure `ensure_dossier_doc()` exists and is importable for 11.4.

### Verifying AC6 before 11.3 exists

Because the gate (11.3) isn't built yet, `update_investigation_item` still returns `phase_gate_reached: False` and nothing posts the affordance automatically. To verify 10.6 end-to-end on the VPS **without** prematurely building 11.3, do one of:
- **(preferred)** Temporarily call `await post_dossier_reveal_affordance()` from a throwaway spot (e.g. at the end of `on_message` behind a hard-coded `if message.content.strip() == "/reveal-test":`), verify the click → reveal → `apply_ops`-streams flow, then **remove the temporary trigger before committing**. Note this in Completion Notes.
- Or confirm the unit/integration tests cover the click path and defer live end-to-end confirmation to Story 11.3's verification, explicitly noting AC6's gate-driven step as "verified after 11.3" in Completion Notes.

Do **not** ship a permanent `/reveal-test` or any debug command.

### Anti-patterns (from epics.md Story 10.6 + the 10.5 cancellation)

- **DON'T** open the canvas in `@cl.on_chat_start` or `@cl.on_chat_resume`.
- **DON'T** re-introduce the `/dossier` command, `cl.set_commands`/`_register_dossier_commands`, or a persistent "Show dossier" welcome button.
- **DON'T** create a new `CustomElement` on each reveal — reuse the `doc` reference (orphaning loses prop sync).
- **DON'T** clear `cl.user_session["doc"]` on panel close — Chainlit's sidebar × is client-side only; the Python `doc` survives and must be reusable.
- **DON'T** edit `Document.jsx` or change `update_investigation_item`'s return value.

### Project Structure Notes

- All Python changes live in `app/chat.py` (new helpers in the existing "Dossier canvas (Epic 10)" section). No new modules, no MCP server changes, no `pyproject.toml` changes (`chainlit>=2.10.0` already supports `cl.ElementSidebar`, `cl.CustomElement`, `cl.Action`, `@cl.action_callback`).
- Tests in `tests/app/test_chat.py` (new `TestOnDemandDossierReveal` class). Tests mirror source; group in a class with AC-referencing docstrings (project-context Testing Rules).
- `public/elements/Document.jsx` unchanged.

### Testing Standards (project-context.md)

- `asyncio_mode = "auto"` — `async def test_...` works without `@pytest.mark.asyncio`.
- Patch `app.chat.cl.user_session`, `app.chat.cl.ElementSidebar`, `app.chat.cl.CustomElement`, `app.chat.cl.Message`, `app.chat.cl.Action` with `MagicMock`/`AsyncMock` as the existing tests do. `cl.ElementSidebar.set_title`/`set_elements` are async → use `AsyncMock`.
- Use the `reload_chat` fixture (reloads `app.config` + `app.chat` after env patching) for any test that touches module-level state or handlers.
- Session mock pattern: either `_make_session_mock_with_history(dossier=..., doc=...)` (`tests/app/test_chat.py:405`) or a `stored = {}` dict with `session_mock.set/get.side_effect` (see `TestInvestigationSessionState`, `:1748`). The store includes a `"doc"` key already.
- Python 3.12 style: `X | None` unions, double quotes, line length 120, type hints on signatures.

### References

- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-23.md` — Edits A–H; the authoritative spec for this replan. Edit D defines Story 10.6; Edits E/F define the dependent 11.3/11.4.
- `_bmad-output/planning-artifacts/epics.md#L1526` — Story 10.6 ACs (verbatim source). `#L1289` — Epic 10 intro + replan note. `#L1631`/`#L1653` — dependent Stories 11.3/11.4.
- `_bmad-output/planning-artifacts/epics.md#L1467` — Story 10.5 (cancelled) — reopen-helper design + anti-patterns this story supersedes.
- PR #64 / commit `1969971` (`git show 1969971 -- app/chat.py`) — the removed `open_dossier_canvas`/`reopen_dossier_canvas`/`_register_dossier_commands`/`show_dossier` code (helper template).
- `app/chat.py:131` (`update_dossier_content`), `:280` (`_handle_apply_ops`), `:469` (`on_chat_resume`), `:521` (`on_chat_start`), `:652` (`_build_call_kwargs` phase selection).
- `public/elements/Document.jsx` — renderer (`phase === "investigating"` placeholder branch at line 32).
- `_bmad-output/implementation-artifacts/deferred-work.md` — "Reopen shows empty doc on resumed session" (now largely moot: 10.6 does not create a doc on resume; dossier persistence across resume remains out of scope). "Unbounded dossier content in system prompt" (10-4, out of scope here).
- `_bmad-output/project-context.md` — Critical Implementation Rules (Python style, testing, anti-patterns).

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (Opus 4.7, 1M context) — bmad-dev-story workflow

### Debug Log References

- `uv run python -m pytest tests/app/test_chat.py::TestOnDemandDossierReveal` — RED (7 failed: helpers absent; 4 already passing AC1/guard) → GREEN (15 passed after the sidebar-refresh fix + tests).
- `uv run python -m pytest` — **374 passed**, 0 regressions.
- `uv run ruff check .` — All checks passed. `uv run ruff format` — clean.
- VPS diagnostic (temp, since removed): `[10.6-test] before_id=134164733742064 doc_id=134164733742064 version=2 content_len=181` — proved the Python doc was correct while the frontend stayed v0, isolating the bug to sidebar update propagation.

### Completion Notes List

- **AC1 (no canvas at start/resume):** Already true post-#64; the new helpers do not reintroduce an open. Locked with 3 regression tests (start no-doc/no-sidebar, resume no-doc/no-sidebar, welcome has no action).
- **AC2 (`ensure_dossier_doc`):** Lazy + idempotent; creates `Document` `CustomElement` with `props={"content": "", "version": 0, "phase": "dossier"}`; never opens the sidebar.
- **AC3 (`reveal_dossier_canvas`):** Ensures the doc, then `set_title("Dossier")` + `set_elements([doc], key="dossier-canvas")`; reuses the same reference on repeat reveals (no orphaned elements).
- **AC4 (affordance):** `post_dossier_reveal_affordance()` posts one `cl.Action(name="reveal_dossier", label="📄 Open dossier", payload={})`; `@cl.action_callback("reveal_dossier")` → `on_reveal_dossier` reveals the canvas and removes the one-shot action. No `/dossier` command, no `cl.set_commands`, no persistent welcome button.
- **AC5 (engine reuse):** `_handle_apply_ops` / `update_dossier_content` operate on the lazily-created doc; verified `apply_ops` returns `"ok"` (not "canvas is not open") after `ensure_dossier_doc()`. The `doc is None` guard is intentionally retained as the fallback (separate test). `public/elements/Document.jsx` untouched.
- **AC6 (manual VPS): VERIFIED LIVE on `https://felipet.io/demos/context-climate/`.** Fresh chat → no panel. Temporary `/reveal-test` → "📄 Open dossier" affordance appears (canvas NOT auto-opened). Click → affordance removed, sidebar opens with the editable `Document` (v0). `/fill-test` (`update_dossier_content`) → panel renders the markdown at **v1**. `/ops-test` (`_handle_apply_ops`, 2 ops) → both sections stream in, version → **v3**. Temp triggers since removed; app restarted clean.
- **Display bug found & fixed during AC6 (Task 9):** the reused 10.2/10.3 update path (`doc.update()`) never refreshed the `ElementSidebar`-hosted element — the panel froze at v0/empty. The sidebar renders from its own `set_sidebar_elements` snapshot, and re-`set_elements` with the same `key` is a documented no-op. Diagnostic log proved the Python doc state was correct (`before_id==doc_id, version=2, content_len=181`) while the frontend stayed v0 — i.e. a propagation bug, not a state bug. Fix: version-stamped key + `dossier_revealed` flag + `_refresh_dossier_canvas()` called from `update_dossier_content`/`_handle_apply_ops`. Without this, the dossier feature could never show content live (latent since 10.2/10.3; masked because the always-open canvas was removed in #64 before live streaming was ever exercised).
- **Scope honored:** Did NOT implement the phase gate (11.3) or `propose_structure` (11.4); did NOT change `update_investigation_item`'s return value; did NOT edit `Document.jsx`. The sidebar-refresh fix touches the reused engine because 10.6's own AC5/AC6 require updates to stream into the panel.

### File List

- `app/chat.py` — MODIFIED: added `ensure_dossier_doc()`, `reveal_dossier_canvas()`, `_refresh_dossier_canvas()`, `post_dossier_reveal_affordance()`, and the `@cl.action_callback("reveal_dossier")` handler `on_reveal_dossier()` in a new "On-demand canvas reveal (Story 10.6)" section; `update_dossier_content()` and `_handle_apply_ops()` now call `_refresh_dossier_canvas()` so edits stream into the sidebar.
- `tests/app/test_chat.py` — MODIFIED: added `TestOnDemandDossierReveal` (15 tests) plus `_make_fake_ce_factory`, `_make_sidebar_mock`, and `_failing_mcp_client` test helpers.
- `_bmad-output/implementation-artifacts/10-6-on-demand-dossier-canvas-reveal.md` — story file (tasks, Dev Agent Record, status).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status transitions.

### Review Findings

- [x] [Review][Patch] Missing `action.remove()` assertion in `test_reveal_dossier_action_callback_triggers_reveal` [tests/app/test_chat.py:~2401] — test only asserts `reveal_dossier_canvas` was awaited; does not assert `action.remove()` was called, leaving the one-shot affordance removal behavior un-locked.

## Change Log

| Date | Change |
|---|---|
| 2026-05-25 | Story created (`ready-for-dev`). |
| 2026-05-25 | Implemented on-demand dossier canvas reveal: `ensure_dossier_doc`, `reveal_dossier_canvas`, `post_dossier_reveal_affordance`, `reveal_dossier` action callback. Status → `review`. |
| 2026-05-25 | **Live VPS verification (AC6)** surfaced that sidebar-hosted element updates never propagated (`doc.update()` no-op on `ElementSidebar`; same-key `set_elements` ignored). Fixed via version-stamped key + `dossier_revealed` flag + `_refresh_dossier_canvas()` wired into `update_dossier_content`/`_handle_apply_ops`. +4 tests (15 total in class), full suite **374 passed**, ruff clean. AC1–AC6 all verified. |
