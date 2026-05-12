# Sprint Change Proposal — Close Epic 9 (Dossier Pivot)

**Date:** 2026-05-07
**Author:** Felipe
**Scope classification:** Moderate (backlog reorganization, no code revert)
**Status:** Approved

---

## 1. Issue Summary

Context Climate has pivoted from a chat-only conversational interface to a journalist **dossier creation tool**. The new product direction is captured in Epics 10–13, which define the dossier authoring flow, dossier export, methodology surfacing, and verification UX.

This pivot changes the relevance of the two remaining backlog stories in Epic 9 (Data Provenance & Journalist Export). Both were scoped around per-message chat-UI affordances that no longer fit the product:

- Story 9.2 ("Copy with Data Sources") presumed individual chat responses are the export unit.
- Story 9.3 ("Source Verification Links") attached verification UX to the chat message.

Story 9.1 (server-side Data Sources block) is already shipped and provides the citation pipeline that Epic 12 will consume.

## 2. Impact Analysis

| Area | Impact |
|---|---|
| Epic 9 | Closed as **done**. Story 9.1 is the complete deliverable. |
| Story 9.2 | **Cancelled.** No story file, no code — nothing to revert. |
| Story 9.3 | **Cancelled in Epic 9.** Underlying need reassigned to Epic 12. No story file, no code. |
| Epics 10–13 | Unchanged in scope; Epic 12 now formally inherits the verification-link requirement. |
| Citation pipeline (`app/citations.py`) | **Preserved and reused** by Epic 12 (dossier Methodology rendering). No refactor needed at this time. |
| FRs (FR58, FR59) | FR58 (copy-with-citations) is supplanted by dossier export. FR59 (verification deep links) carries forward into Epic 12. Tracked in epics.md inline. |
| Architecture, UX | No revisions required for this course correction. Dossier-related changes already captured under Epics 10–13. |

## 3. Recommended Approach

**Direct adjustment via epic closure.** No rollback, no scope reduction beyond what the pivot already implies. The change is purely administrative: mark Epic 9 done, mark its two remaining backlog stories cancelled, and document the reassignment of their underlying need.

**Rationale:**
- Both cancelled stories had no implementation, no story file, and no dependent work — zero technical debt or revert cost.
- Story 9.1 stands on its own as a useful, shipped capability (deterministic in-chat provenance) and is independently valuable even though chat is no longer the primary export surface.
- Reassigning verification links to Epic 12 puts them on the artifact (the dossier) where journalists actually need them, instead of duplicating the affordance in the chat surface.

## 4. Detailed Change Proposals

### 4.1 `_bmad-output/implementation-artifacts/sprint-status.yaml`

- `last_updated`: `2026-04-23` → `2026-05-07` (with note referencing this proposal).
- Story-status legend: add `cancelled` entry.
- Epic 9 block:
  - `epic-9: in-progress` → `epic-9: done`
  - `9-2-copy-with-data-sources: backlog` → `9-2-copy-with-data-sources: cancelled  # superseded by dossier export (Epic 11)`
  - `9-3-source-verification-links: backlog` → `9-3-source-verification-links: cancelled  # deferred to Epic 12 dossier Methodology section`
- Inline comment block above Epic 9 expanded to record the closure rationale and link to this proposal.

### 4.2 `_bmad-output/planning-artifacts/epics.md`

- Epic 9 heading: append "— DONE (2026-05-07)" and add a status paragraph describing the closure, the supersession by Epics 10–13, and pipeline reuse by Epic 12.
- Story 9.2 heading: append "— CANCELLED (2026-05-07)" with a status paragraph naming Epic 11 as the replacement.
- Story 9.3 heading: append "— CANCELLED (2026-05-07)" with a status paragraph reassigning the verification-link need to Epic 12.
- Story 9.1, 9.2, 9.3 acceptance-criteria bodies are left intact for historical reference.

### 4.3 No code changes

Story 9.2 and 9.3 were never implemented. There is nothing to revert in `mcp_server/`, `app/`, or `tests/`.

## 5. Implementation Handoff

**Scope:** Moderate. No development handoff needed — changes are confined to BMAD planning artifacts.

- **Sprint status / epics.md updates** — applied as part of this proposal (this run).
- **Epic 12 author (next time the dossier Methodology story is drafted)** — incorporate the verification-link AC originally written under Story 9.3 (`https://data360.worldbank.org/en/indicator/{indicator_code}?database_id={database_id}`) and the document-source rule (no external link, show filename + upload date). The Story 9.3 body in epics.md is preserved for that future reference.
- **Retrospective:** Epic 9 retrospective remains `optional` in sprint-status. Recommend skipping a formal retro since the pre-redesign retro already covered the major lesson (LLM-driven citation markers were unreliable) and the Tier 1 redesign delivered.

## 6. Decision Record

| # | Decision | Rationale |
|---|---|---|
| 1 | **Story 9.2 (Copy with Data Sources): CANCELLED** | The dossier document (Epic 11) is now the primary export artifact, replacing per-message chat copying. Per-message copy is redundant with dossier export and would split journalist workflows across two surfaces. |
| 2 | **Story 9.3 (Source Verification Links): CANCELLED in Epic 9, reassigned to Epic 12** | Verification links belong on the dossier (the artifact a journalist publishes from), surfaced inline in the Methodology section, rather than as per-message chat UI. Epic 12 owns dossier Methodology rendering. |
| 3 | **Epic 9: DONE** | Story 9.1 is a complete, shipped, independently valuable deliverable. The citation pipeline (`extract_references`, `deduplicate_references`, server-appended Data Sources block) it built is reused by Epic 12, so the work continues to pay dividends in the new product direction. |

**Driver:** Pivot to journalist dossier creation tool, captured in Epics 10–13.

---

**Approved by:** Felipe (2026-05-07)
**Routes to:** No development handoff. Future Epic 12 story author should consult Story 9.3's preserved acceptance criteria when implementing dossier verification links.
