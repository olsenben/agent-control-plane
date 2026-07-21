# Slice V6 T02 — Session comment projection

**Status:** In Progress  
**Epic ticket:** T02  
**Deps:** T01 Done (`ae4f5e4`)

## Goal

Versioned single-writer Gitea session status comment: Queued through terminal states via PATCH upsert with sequence guards.

## Acceptance

| Check | Expected |
|-------|----------|
| Session fields | `session_comment_id`, `session_comment_version`, `last_rendered_event_sequence`, `last_rendered_status` |
| Stale guard | Lower sequence or regressive status cannot overwrite |
| Dispatch | Creates queued comment after enqueue |
| Terminal | `finalize_session` updates same comment |
| Invocation rejected | Separate comment path (no session) |

## Artifacts

- `src/agent_control/observe/comment_projection.py`
- `GiteaClient.patch_issue_comment`
- `tests/test_v6_t02_comment_projection.py`
