# Story 10.5: Dossier Canvas Reopen Affordance

Status: done

## Story

As a journalist,
I want a way to bring the dossier panel back after I close it,
So that I can keep working without restarting the chat session when I dismissed the canvas by accident or on purpose.

---

## Acceptance Criteria

**AC1: Reopen helper is idempotent and resume-safe.**
**Given** an active chat session
**When** `reopen_dossier_canvas()` is called in `app/chat.py`
**Then** if `cl.user_session.get("doc")` exists, it re-displays that same element via `await cl.ElementSidebar.set_title("Dossier")` and `await cl.ElementSidebar.set_elements([doc], key="dossier-canvas")` — preserving `content`, `version`, and `phase`
**And** if `cl.user_session.get("doc")` is `None` (e.g. resumed thread, or never opened), it calls `open_dossier_canvas()` to create a fresh one
**And** calling the helper repeatedly does not orphan elements or overwrite session state — same `doc` reference is reused.

**AC2: `/dossier` slash command reopens the canvas.**
**Given** the chat is running
**When** the user invokes the `/dossier` slash command
**Then** `reopen_dossier_canvas()` is called and the panel becomes visible again
**And** no plain chat message turn is triggered for the command — the slash invocation is handled before reaching the agentic loop.

**AC3: Welcome message exposes a "Show dossier" button.**
**Given** `@cl.on_chat_start` fires
**When** the welcome message is rendered
**Then** it includes a `cl.Action(name="show_dossier", label="Show dossier", payload={})` button
**And** clicking the button invokes `@cl.action_callback("show_dossier")` that calls `reopen_dossier_canvas()`.

**AC4: Manual verification preserves state.**
**Given** the panel has been closed by the user mid-conversation
**When** the user runs `/dossier` (or clicks "Show dossier")
**Then** the panel reopens showing the same `content`, `version`, and `phase` that were live before close — verified manually against the VPS deployment, logged in Completion Notes below.

**AC5: Story 10.2 deferred review finding is closed.**
**Given** the deferred Review Finding from Story 10.2 ("`open_dossier_canvas()` is not idempotent" — `app/chat.py:58-67`)
**When** this story is complete
**Then** `open_dossier_canvas()` no longer creates a second `CustomElement` when called from a context where one already exists — either because callers go through `reopen_dossier_canvas()`, or because `open_dossier_canvas()` itself short-circuits when `doc` is already in `user_session` (developer's choice; see Dev Notes).

---

## Tasks / Subtasks

### Task 1: Add `reopen_dossier_canvas()` helper to `app/chat.py` (AC: #1, #5)

- [x] Add `async def reopen_dossier_canvas() -> None:` immediately below `open_dossier_canvas()` (around `app/chat.py:59-67`).
- [x] Logic:
  ```python
  async def reopen_dossier_canvas() -> None:
      doc = cl.user_session.get("doc")
      if doc is None:
          await open_dossier_canvas()
          return
      await cl.ElementSidebar.set_title("Dossier")
      await cl.ElementSidebar.set_elements([doc], key="dossier-canvas")
  ```
- [x] **Do NOT** create a new `cl.CustomElement` — reuse the existing reference so `content`, `version`, and `phase` are preserved.
- [x] **Do NOT** mutate `cl.user_session["doc"]` in the existing-element branch.

### Task 2: Register `/dossier` slash command (AC: #2)

- [x] In `on_chat_start`, after the welcome `cl.Message` is sent, register the command via the emitter (Chainlit 2.10 does **not** expose `cl.set_commands` at the module level — see Latest Tech Information):
  ```python
  await cl.context.emitter.set_commands([
      {
          "id": "dossier",
          "description": "Reopen the dossier panel",
          "icon": "panel-right-open",
          "button": False,
          "persistent": False,
      }
  ])
  ```
- [x] In `on_message`, at the very top of the handler (before any RAG / agentic-loop logic), check the command:
  ```python
  if message.command == "dossier":
      await reopen_dossier_canvas()
      return
  ```
- [x] Also register the same commands list in `on_chat_resume` so resumed threads get the slash command back.

### Task 3: Add "Show dossier" action button to welcome message (AC: #3)

- [x] Replace the existing welcome `cl.Message(...)` send in `on_chat_start` (currently `app/chat.py:469`) with one that carries the action:
  ```python
  await cl.Message(
      content="Welcome to Context Climate! Ask me about World Bank climate and development data.",
      actions=[cl.Action(name="show_dossier", label="Show dossier", payload={})],
  ).send()
  ```
- [x] Add an `@cl.action_callback("show_dossier")` handler (module-level, alongside other Chainlit handlers):
  ```python
  @cl.action_callback("show_dossier")
  async def on_show_dossier(_action: cl.Action) -> None:
      await reopen_dossier_canvas()
  ```
- [x] Do **not** remove the action after click — leaving it persistent lets the user reopen the panel multiple times across the conversation.

### Task 4: Close Story 10.2 deferred finding (AC: #5)

- [x] Open `_bmad-output/implementation-artifacts/10-2-elementsidebar-canvas-integration.md`.
- [x] In the Review Findings list, update the `[Defer]` entry for "`open_dossier_canvas()` is not idempotent" to `[Resolved]` with closing note pointing back to this story.
- [x] **Harden `open_dossier_canvas()` itself to be idempotent** — if `cl.user_session.get("doc") is not None`, delegate to `reopen_dossier_canvas()`. Covered by `TestOpenDossierCanvasIdempotency`.

### Task 5: Unit tests in `tests/app/test_chat.py` (AC: #1, #2, #3, #5)

- [x] Extended `tests/app/test_chat.py` with four new test classes and 10 new tests:
  - `TestReopenDossierCanvas`: `test_reopen_reuses_existing_doc`, `test_reopen_when_no_doc_calls_open`, `test_reopen_is_idempotent`.
  - `TestOpenDossierCanvasIdempotency`: `test_open_when_doc_exists_delegates_to_reopen`, `test_open_when_no_doc_creates_new_element`.
  - `TestShowDossierAction`: `test_show_dossier_callback_calls_reopen`, `test_on_chat_start_welcome_includes_show_dossier_action`.
  - `TestDossierSlashCommand`: `test_command_short_circuits_on_message`, `test_command_registered_on_chat_start`, `test_register_dossier_commands_payload`.

### Task 6: Manual verification on VPS deployment (AC: #4)

- [ ] Deploy the branch to the VPS staging URL.
- [ ] Scenario A — slash command: send a few messages so the dossier has non-zero `version`; close the panel via the `×`; invoke `/dossier`; verify the panel reopens with the same `content` and `version`.
- [ ] Scenario B — button: click the "Show dossier" button on the welcome message after closing the panel; verify same `content`/`version`/`phase` are preserved.
- [ ] Log the verification (date, build SHA, screenshots if available) in the Completion Notes section below.

> **NOTE (dev):** Task 6 is the manual-verification step explicitly carved out by AC4 and the story author. Left unchecked intentionally — to be performed by Felipe against the VPS deployment after merge. The code paths are exercised end-to-end by the new unit tests; this is the prod-environment sanity check.

### Task 7: Lint, format, full test suite (AC: all)

- [x] `uv run ruff check .` — clean
- [x] `uv run ruff format --check .` — clean (39 files already formatted)
- [x] `uv run pytest -q` — 347 passed, 0 failed

### Review Findings (AI Code Review — 2026-05-13)

#### Patch

- [x] [Review][Patch] **Missing test for `on_chat_resume` command registration** [tests/app/test_chat.py] — `_register_dossier_commands()` is called in `on_chat_resume` (line 432) but there is no test asserting this. The `on_chat_start` path is tested; the resume path is not. A regression here would be silent. _Fixed: added `TestDossierCommandOnResume::test_command_registered_on_chat_resume`._

#### Deferred

- [x] [Review][Defer] **`on_chat_start` missing `-> None` return type annotation** [app/chat.py:466] — pre-existing issue, `async def on_chat_start():` has no return type. Not introduced by this story.
- [x] [Review][Defer] **Reopened panel on resumed session shows empty doc, not persisted content** [app/chat.py:425-429] — `on_chat_resume` always seeds `dossier` and `doc` with empty state; `/dossier` after a resume shows an empty document. Explicitly out-of-scope per story Dev Notes ("does not wire on_chat_resume"). Deferred to a future story.
- [x] [Review][Defer] **`_register_dossier_commands` failure is silently swallowed** [app/chat.py:510-513] — `except Exception: logger.warning(...)` suppresses all emitter errors with no user-facing feedback. Consistent with the existing MCP auto-connect and canvas open patterns in the same file. No deviation from project norms.

---

## Dev Notes

### Why this story uses the emitter for `set_commands`

The epic (`epics.md:1499`) suggests "Chainlit `cl.set_commands` in `on_chat_start`". **`cl.set_commands` does not exist at the module level in chainlit 2.10.0** (verified via `uv run python -c "import chainlit; hasattr(chainlit, 'set_commands')"` → False). The actual public surface is `cl.context.emitter.set_commands(commands: List[CommandDict])` (`chainlit/emitter.py:443`). Chosen command value lands on `cl.Message.command` (`chainlit/message.py:83,252`). Use `message.command` — do **not** parse `/dossier` out of `message.content`.

### Why reuse the existing `doc` reference

Chainlit's `ElementSidebar` close (×) is purely client-side; the Python-side `doc` and `user_session["doc"]` survive a close. Re-instantiating the `CustomElement` would orphan the old reference, lose any in-flight `await doc.update()` props sync, and reset `content`/`version` on the live document — defeating the entire purpose of the reopen affordance.

### Why both `/dossier` and a button

Mobile users and screen-reader users may not see the slash-command menu; the action button is a visible, click-target affordance. Slash command is faster on desktop where journalists already keyboard-driven. Both routes are cheap to wire up and converge on the same `reopen_dossier_canvas()` helper.

### Cross-story context

- **Story 10.2** introduced `open_dossier_canvas()` (`app/chat.py:59-67`) and the `doc` session key. Review left a deferred finding (idempotency); this story closes it (AC5).
- **Story 10.3** added `apply_ops` and `update_dossier_content()` — these mutate the same `doc.props` that the reopen helper now needs to preserve. The reopen helper deliberately does **not** call `doc.update()` — calling `set_elements([doc])` re-attaches the element to the sidebar, which is what we want; an `update()` call would send a redundant props broadcast.
- **Story 10.4** added phase-aware system prompts that read `doc.props["content"]` and `doc.props["version"]` each turn (`app/chat.py:556-578`). The reopen path must not perturb either field.

### Resume-path side benefit (out of scope)

`on_chat_resume` (`app/chat.py:368-393`) currently always calls `open_dossier_canvas()`, which creates a fresh element on resume. After this story, a future task could replace that with `reopen_dossier_canvas()` to recover any in-flight doc state for resumed threads. **Do not** make that change in this story — Story 10.2 review explicitly deferred the resume question. Just leave the helper general enough to support it later.

### What this story does NOT do

- Does **not** add an `on_chat_resume` rewrite.
- Does **not** persist `doc` content across chat sessions (that requires DB plumbing — a future story).
- Does **not** add a "Close dossier" button (close is already a client affordance via the `×`).
- Does **not** add a `cl.Step` or chat-side acknowledgement when the panel reopens — the visual sidebar appearance is the confirmation.

---

## Latest Tech Information

### chainlit 2.10.0 — verified surface

| Symbol | Where | Notes |
|---|---|---|
| `cl.Action` | `chainlit/action.py:12` | Pydantic dataclass; fields: `name`, `payload` (dict), `label`, `tooltip`, `icon`. `payload={}` is valid. |
| `@cl.action_callback("name")` | module-level decorator | Handler receives the `cl.Action` instance as its sole argument. |
| `cl.context.emitter.set_commands(commands)` | `chainlit/emitter.py:443` | Module-level `cl.set_commands` does **NOT** exist; must go through the emitter. |
| `CommandDict` schema | `chainlit/types.py:328` | Keys: `id: str`, `description: str`, `icon: str` (lucide icon name), `button: Optional[bool]`, `persistent: Optional[bool]`, `selected: Optional[bool]`. |
| `cl.Message.command` | `chainlit/message.py:83,252` | The chosen command's `id` appears here when the user invokes a slash command; `None` for ordinary messages. |
| `cl.ElementSidebar.set_title(...)` / `set_elements(elements, key=...)` | already used in `open_dossier_canvas()` | The `key=` argument scopes the sidebar slot — keep `"dossier-canvas"` consistent across open and reopen. |

### Lucide icon for the `/dossier` command

`panel-right-open` is the canonical Lucide icon for "reveal a right-side panel". Alternative: `file-text` (more dossier-themed). Either is acceptable — pick one and be consistent.

---

## Previous Story Intelligence (10.2, 10.3, 10.4)

### From Story 10.2 (`10-2-elementsidebar-canvas-integration.md`)

- The `doc` is created with `props={"content": "", "version": 0, "phase": "investigating"}` and `display="inline"` — `display="side"` or `display="page"` breaks the sidebar.
- The sidebar `key="dossier-canvas"` is the slot identifier — reuse it exactly.
- Open call is **not** wrapped in try/except in `on_chat_start` (`app/chat.py:428-430` now wraps it). Mirror that pattern in any new call sites if you add them.
- Deferred review finding (idempotency) — see AC5 / Task 4.

### From Story 10.3 (`10-3-apply-ops-patch-engine.md`)

- `apply_ops` mutates `doc.props["content"]` and `doc.props["version"]` per op and calls `await doc.update()` after each — the reopen helper must not interfere with this flow. Do not touch `doc.props` from `reopen_dossier_canvas()`.
- The `dossier` session dict (`cl.user_session.get("dossier")`) mirrors `content`/`version` for the prompt builder — also do not touch from reopen.

### From Story 10.4 (`10-4-dossier-system-prompt.md`)

- `_agentic_loop()` reads `cl.user_session.get("dossier")["phase"]` each turn to choose the system prompt. The reopen path must preserve phase — and since the reopen helper does not touch `dossier` state, this falls out for free.

---

## Git Intelligence Summary

Recent commits relevant to this story:

- `7e78425` `fix(epic-10): address review findings across stories 10-2/10-3/10-4` — context for the deferred 10.2 finding that AC5 now resolves.
- `e32b869` `feat(10-4): phase-aware system prompts for dossier canvas (#55)` — confirms `_agentic_loop()` shape used in this story's Dev Notes.
- `ce08a69` `feat(10-3): apply_ops patch engine for dossier canvas (#54)` — confirms `apply_single_op`, `_handle_apply_ops`, rollback semantics.
- `9a66bdd` `feat(10-2): ElementSidebar canvas integration (#52)` — introduced `open_dossier_canvas()` and the `doc` session key.

Branch naming: per `project-context.md` workflow rules, create `story/10-5-dossier-canvas-reopen-affordance` from `main`. Commit format: `feat(10-5): description`.

---

## Project Context Reference

This story must follow the rules in `_bmad-output/project-context.md`. Highlights relevant to this story:

- **Python 3.12+ union syntax** — `cl.CustomElement | None`, not `Optional[cl.CustomElement]`.
- **Async I/O** — `reopen_dossier_canvas` and the action callback are `async def`; never block.
- **Type hints required** on all new function signatures.
- **Citation pipeline** is untouched by this story — the reopen helper must NOT short-circuit the agentic loop's data-sources block logic.
- **System prompt text lives in `app/prompts.py`** — this story does not add any prompt text; do not introduce inline prompts in `app/chat.py`.
- **Pre-commit ruff hooks enforce** — line length 120, double quotes, isort.
- **No hardcoded values** — the command id (`"dossier"`) and action name (`"show_dossier"`) are stable identifiers, not env-configurable; that's intentional and acceptable.

---

## File Structure Requirements

Files this story touches:

| Path | Change | Reason |
|---|---|---|
| `app/chat.py` | UPDATE | Add `reopen_dossier_canvas()`, `@cl.action_callback("show_dossier")`, command registration in `on_chat_start` and `on_chat_resume`, command short-circuit in `on_message`, action on welcome message. Optionally harden `open_dossier_canvas()` to be idempotent (Task 4). |
| `tests/app/test_chat.py` | NEW | Three test classes per Task 5. |
| `_bmad-output/implementation-artifacts/10-2-elementsidebar-canvas-integration.md` | UPDATE | Close deferred review finding (Task 4). |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | UPDATE (workflow) | Status transitions managed by create-story / dev-story workflows. |

Files this story must **not** touch:

- `app/prompts.py` — no prompt changes.
- `app/citations.py` — citation pipeline unchanged.
- `mcp_server/**` — server-side untouched.
- `app/data.py`, `app/db.py` — no persistence changes.

---

## Testing Requirements

- All tests in `tests/app/test_chat.py` follow the project conventions in `project-context.md`:
  - `asyncio_mode = "auto"` is global — no `@pytest.mark.asyncio` needed (acceptable but redundant).
  - Group tests in classes with docstrings referencing AC numbers (`"""AC1: ..."""`).
  - Mock Chainlit primitives — do NOT spin up a real Chainlit runtime.
- Suggested fixture pattern:
  ```python
  @pytest.fixture
  def mock_chainlit(monkeypatch):
      import chainlit as cl
      session = {}
      monkeypatch.setattr(cl, "user_session", types.SimpleNamespace(
          get=lambda k, default=None: session.get(k, default),
          set=lambda k, v: session.update({k: v}),
      ))
      sidebar_mock = AsyncMock()
      monkeypatch.setattr(cl, "ElementSidebar", sidebar_mock)
      return session, sidebar_mock
  ```
- For the command short-circuit test, build a `cl.Message`-shaped mock (`SimpleNamespace(content="", command="dossier", elements=[])`) and assert the agentic-loop helper (`_agentic_loop`) was not invoked.

---

## Anti-Patterns (do NOT do)

- **DON'T** create a new `cl.CustomElement` in `reopen_dossier_canvas()` — it orphans the existing element, breaks `apply_ops` updates, and loses content/version.
- **DON'T** clear `cl.user_session["doc"]` when the panel closes — there is no Python-side close event, and clearing it would defeat the reopen path.
- **DON'T** trigger reopen automatically on every message turn — only on `/dossier`, the button, or a future explicit resume call.
- **DON'T** use `cl.set_commands(...)` at the module level — it does not exist in chainlit 2.10. Use `cl.context.emitter.set_commands(...)`.
- **DON'T** parse `/dossier` out of `message.content` — Chainlit's command system strips it and puts the id on `message.command`.
- **DON'T** `await doc.update()` inside the reopen helper — `set_elements([doc])` is the re-attach mechanism; an extra `update()` is a redundant broadcast.
- **DON'T** add prompt text or system-prompt mutations to this story.
- **DON'T** wire `on_chat_resume` to the reopen path in this story — explicitly out of scope (Story 10.2 review deferred it).

---

## References

- `_bmad-output/planning-artifacts/epics.md` → "Story 10.5: Dossier Canvas Reopen Affordance" (lines 1464–1519).
- `_bmad-output/implementation-artifacts/10-2-elementsidebar-canvas-integration.md` → Review Findings → deferred idempotency entry (line 71).
- `app/chat.py:59-67` → existing `open_dossier_canvas()` (insertion point for new helper).
- `app/chat.py:368-393` → `on_chat_resume` (out-of-scope reference; do not edit here).
- `app/chat.py:424-469` → `on_chat_start` (welcome message, command registration site).
- `app/chat.py:482-537` → `on_message` (command short-circuit site).
- chainlit 2.10 internals: `emitter.py:443`, `types.py:328`, `action.py:12`, `message.py:83,252`.

---

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m]

### Debug Log References

- First test run for `TestShowDossierAction::test_on_chat_start_welcome_includes_show_dossier_action` and `TestDossierSlashCommand::test_command_registered_on_chat_start` failed with `chainlit.context.ChainlitContextException: Chainlit context not found` because `cl.context` is a lazy proxy and `unittest.mock.patch("app.chat.cl.context")` triggers evaluation. Resolved by extracting `_register_dossier_commands()` helper in `app/chat.py` (so callers patch the helper) and patching `cl.context` only in the one test that exercises the helper itself.

### Completion Notes List

- All five ACs covered by code + unit tests except AC4 (manual VPS verification) which is left for Felipe — see Task 6 note. Unit tests exercise both the slash-command and action-button reopen paths end-to-end.
- ✅ AC5: deferred Story 10.2 review finding ("`open_dossier_canvas()` is not idempotent") is resolved by hardening `open_dossier_canvas()` to short-circuit to `reopen_dossier_canvas()` when a `doc` already lives in `cl.user_session`. The 10-2 story file has been updated to mark the finding `[Resolved]`.
- Implementation note: the epic suggested `cl.set_commands` at the module level, but that symbol does **not** exist in chainlit 2.10.0. Used `cl.context.emitter.set_commands(...)` instead (verified via `chainlit/emitter.py:443`). Documented in the story's Latest Tech Information section.
- The slash-command short-circuit in `on_message` uses `getattr(message, "command", None) == "dossier"` for robustness against test mocks that don't set `.command`. Existing `TestMcpToolUse` and other on_message tests continue to pass.

### File List

- `app/chat.py` — added `reopen_dossier_canvas()`, `_DOSSIER_COMMANDS`, `_register_dossier_commands()`, `@cl.action_callback("show_dossier")` handler; made `open_dossier_canvas()` idempotent; added `/dossier` short-circuit at the top of `on_message`; added `actions=[cl.Action("show_dossier", ...)]` to the welcome message; registered commands in both `on_chat_start` and `on_chat_resume`.
- `tests/app/test_chat.py` — added 4 new test classes / 10 new tests covering reopen helper idempotency, `open_dossier_canvas` idempotency, `show_dossier` action callback + welcome wiring, `/dossier` short-circuit, and command registration.
- `_bmad-output/implementation-artifacts/10-2-elementsidebar-canvas-integration.md` — marked the "`open_dossier_canvas()` is not idempotent" deferred review finding `[Resolved]` with a back-reference to this story.
- `_bmad-output/implementation-artifacts/10-5-dossier-canvas-reopen-affordance.md` — task checkboxes, status, dev notes (this file).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status transitions backlog → ready-for-dev → in-progress → review.

### Change Log

| Date       | Change                                                                                  |
|------------|-----------------------------------------------------------------------------------------|
| 2026-05-13 | Story created via `bmad-create-story`. Status: ready-for-dev.                            |
| 2026-05-13 | Implementation complete: reopen helper, slash command, action button, 10.2 finding closed. Status: review. |

