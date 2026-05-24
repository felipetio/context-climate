# Sprint Change Proposal — Dossier Display Replan (On-Demand Canvas) + Epic 11 Re-scope

**Date:** 2026-05-23
**Author:** Felipe (via Correct Course workflow)
**Scope classification:** Moderate (backlog reorganization — new story, status changes, AC rewrites; no code revert)
**Status:** Approved

---

## 1. Issue Summary

Context Climate's dossier feature (Epics 10–13) shipped its **display mechanism** as an
always-on `cl.ElementSidebar` canvas that **auto-opened empty at chat start** (Story 10.2),
plus a reopen surface — `reopen_dossier_canvas()`, the `/dossier` slash command, and a
"Show dossier" welcome button (Story 10.5). This was rejected as poor UX and **removed in
PR #64** (`1969971`, −346 LOC).

The removal left the dossier feature **unreachable end-to-end**:

- `cl.user_session["doc"]` is **never created** (both `open_dossier_canvas` and
  `reopen_dossier_canvas` are gone), so `update_dossier_content()` no-ops (`doc is None`)
  and `_handle_apply_ops()` always returns `"Error: dossier canvas is not open"`. The
  editing engine survives as code but has **no surface to render into**.
- The phase gate (Story 11.3) is unbuilt, so `update_investigation_item` returns
  `phase_gate_reached: False` hardcoded — the phase never transitions out of
  `"investigating"`.

**Trigger type:** Failed approach requiring a different solution + strategic UX pivot.

**Target design:** the dossier should be displayed via an **on-demand canvas** —
reusing the surviving `Document.jsx` and `apply_ops`/`update_dossier_content` engine, but
created lazily and revealed via an explicit affordance **only when the session enters
dossier phase**. Never auto-opened empty at chat start.

**Evidence:** PR #64 commit message (states the file-based replan intent); `app/chat.py`
(confirms `doc` is never created post-#64, `_handle_apply_ops` guards on `doc is None`);
`update_investigation_item` returns `phase_gate_reached: False` hardcoded;
`deferred-work.md` flags the resume-shows-empty-doc gap.

## 2. Impact Analysis

| Area | Impact |
|---|---|
| **Epic 10** (Dossier Shell) | Stays `in-progress`. Stories 10.1/10.3/10.4 stand. Story 10.2 auto-open AC **superseded** (helpers survive). Story 10.5 **cancelled**. New **Story 10.6** added. |
| **Epic 11** (Investigation State Machine) | In scope. **11.1** (review) and **11.2** (done) are display-agnostic — unchanged. **11.3** and **11.4** ACs **rewritten** to drive the on-demand reveal and lazy doc creation. |
| **Epic 12 / 13** | No AC changes. They drive the document exclusively via `apply_ops`/`update_dossier_content`; only the *target* of those ops changes (sidebar element → lazily-created doc). No resequencing. |
| **PRD** | No direct conflict — the dossier display was never documented (FRs end at FR59; FR60–FR74 live inline in `epics.md`). Pre-existing doc gap noted as optional follow-up; not blocking. |
| **Architecture** | No conflict — `architecture.md` has zero dossier/ElementSidebar references (predates the pivot). Optional follow-up. |
| **Secondary artifacts** | `sprint-status.yaml` (story statuses), `project-context.md` (Epic 10 row staleness), code (`app/chat.py`, `Document.jsx`, `app/prompts.py`), tests. |

## 3. Recommended Approach

**Selected: Option 1 — Direct Adjustment.** Effort **Low–Medium**, Risk **Low**.

- **Option 2 (Rollback): rejected / N/A** — PR #64 already removed the bad code, and the
  `apply_ops` engine was *intentionally* retained for reuse. Rolling back would destroy
  reusable infrastructure.
- **Option 3 (MVP Review): N/A** — the dossier remains in MVP scope; this is a mechanism
  change, not a scope cut.

**Rationale:** Direct Adjustment reuses the surviving engine and `Document.jsx`, honors the
rejected-UX learning (no auto-open, no persistent reopen surface), and keeps the dossier
feature on track with minimal risk. The change is fundamentally about *when and how* the
canvas is created and revealed, not about rebuilding the editing layer.

## 4. Detailed Change Proposals

### Edit A — Epic 10 intro
Reframe from "Chainlit split-panel layout" to an **on-demand** canvas revealed only on
dossier-phase entry; add a replan note pointing to Story 10.6 and this proposal.

### Edit B — Story 10.2 (stays `done`)
Mark the "canvas opens immediately at `on_chat_start`" AC **superseded by Story 10.6**.
The surviving deliverables — `update_dossier_content()` and `dossier`/`investigation`
session-state initialization — remain in force.

### Edit C — Story 10.5 → **Cancelled**
Its entire deliverable (reopen affordance, `/dossier` command, "Show dossier" button) was
removed in PR #64 and is replaced by Story 10.6. Mirrors the 9.2/9.3 cancellation
precedent — code already reverted, nothing further to revert.

### Edit D — New **Story 10.6: On-Demand Dossier Canvas Reveal**
Provides: no canvas at chat start/resume (AC1); `ensure_dossier_doc()` lazy creation
(AC2); `reveal_dossier_canvas()` on-demand reveal (AC3); reveal triggered by an explicit
post-gate affordance — no auto-open, no `/dossier`, no persistent button (AC4); engine
reuse so `apply_ops`/`update_dossier_content` operate on the created doc (AC5); VPS manual
verification (AC6). Reuses `Document.jsx` unchanged.

### Edit E — Story 11.3 rewrite (Phase Gate Logic)
Gate now: flips `phase` to `"dossier"`, returns `phase_gate_reached: True` (replacing the
hardcoded `False` from 11.2), makes `propose_structure` available, **and posts the Story
10.6 reveal affordance** — the canvas is NOT auto-opened. Depends on Story 10.6.

### Edit F — Story 11.4 rewrite (propose_structure Tool)
`propose_structure` calls `ensure_dossier_doc()` (Story 10.6) to create the doc if absent,
generates the skeleton, sets content via `update_dossier_content()`, sets phase, returns
sections. The skeleton becomes visible when the journalist opens the canvas via the reveal
affordance — `propose_structure` does NOT force the sidebar open. Depends on Story 10.6.

### Edit G — `sprint-status.yaml`
`epic-10`: `10-5` `done → cancelled` (superseded by 10.6); add
`10-6-on-demand-dossier-canvas-reveal: backlog`; header note referencing this proposal.
`epic-11`: annotate `11-3`/`11-4` as ACs rewritten 2026-05-23.

### Edit H — `project-context.md`
Update the Epic 10 overview row: "canvas integration" → "on-demand canvas reveal".

## 5. Implementation Handoff

**Scope: Moderate** → Developer agent via the standard story cycle.

**Sequence:**
1. **Story 10.6** — On-Demand Dossier Canvas Reveal (re-establishes the display surface).
2. **Story 11.3** — Phase Gate Logic (rewritten; drives the reveal).
3. **Story 11.4** — propose_structure Tool (rewritten; populates the lazily-created doc).

**Unchanged / already complete:** Story 11.1 (in `review` — proceed to code review),
Story 11.2 (done). Stories 10.1/10.3/10.4 stand.

**Success criteria:** Fresh chat shows no panel; completing investigation items 1–5 posts
an "Open dossier" affordance; clicking reveals the populated skeleton; subsequent
`apply_ops` edits stream into the panel. Verified manually on the VPS deployment.

**Optional follow-ups (non-blocking):** back-port dossier FRs (FR60–FR74) and the dossier
architecture into `prd.md` / `architecture.md`; address dossier persistence across chat
resume (currently out of scope — `deferred-work.md`).
