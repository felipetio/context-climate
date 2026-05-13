# Deferred Work

## Deferred from: code review of 10-5-dossier-canvas-reopen-affordance (2026-05-13)

- **`on_chat_start` missing `-> None` return type annotation** (`app/chat.py:466`) — pre-existing issue not introduced by this story.
- **Reopen shows empty doc on resumed session** (`app/chat.py:425-429`) — `on_chat_resume` seeds doc with empty state; `/dossier` after resume shows an empty document. Explicitly out-of-scope for Story 10.5. Future story should replace `open_dossier_canvas()` in `on_chat_resume` with `reopen_dossier_canvas()` and repopulate props from persisted thread state.
- **`_register_dossier_commands` failure swallowed silently** (`app/chat.py:510-513`) — consistent with existing project pattern; acceptable for now but could be improved with a user-facing fallback if the slash command is critical.
