# Slice 6D.1 — Hollow Artifact Guardrails

Stop treating schema-valid but semantically empty plan/fix artifacts as successful runs. Adds quality gates, quality-triggered model fallback, patch gates before publish, state-aware publish preflight, task-aware fake planner file scope, and honest 6D issue comments.

**Prerequisite:** [slice-5.2-plan-quality-gate.md](slice-5.2-plan-quality-gate.md), [slice-6d-branch-push-pr.md](slice-6d-branch-push-pr.md)

**Deferred to 6D.2:** per-command `model_policy` bundle, `MODEL_ROUTING_POLICY_PLAN` / `_FIX` env split.

## Problem

Homelab failure mode: valid-but-useless model output (`steps: []`, empty fix) reached `status: completed` and attempted 6D publish (branch push failed or author identity missing).

Slice 5.2 blocked **approval** on hollow plans at CT103, but the official engine still returned `completed` until this slice.

## Terminal statuses

| `terminal_status` | Meaning |
|-------------------|---------|
| `failed_quality_gate` | Valid JSON but empty/useless plan, fix, or patch |
| `failed_publish_precheck` | Useful patch but ops not ready (identity, empty tree, etc.) |

Existing `failed_gate`, `failed_publish`, `failed_parse` unchanged.

## Quality gates

| Stage | Module | Checks |
|-------|--------|--------|
| Plan/fix (engine) | `agent_workers/rlm/output_quality.py` | Actionable steps + scoped files; fix changes with content |
| Patch (runner) | same | `patch.diff` non-empty, parses, working tree intersects `allowed_files` |
| Publish | `agent_workers/publish/preflight.py` | Workspace mode: identity, `git diff --check`, scope — **not** `git apply --check` post-apply |

On failure the worker writes `quality_gate_result.json` (mirrors `diff_gate_result.json`).

## Quality-triggered fallback

`official_engine` plan/fix paths use `run_quality_gated_attempts`:

1. GPU (`MODEL_3080_*`)
2. GPU retry with stricter suffix
3. External (`MODEL_EXTERNAL_ROLES=rlm` + `MODEL_3080_EXTERNAL_*`) via `agent_workers/rlm/model_routing.py`

Worker code does **not** import new `agent_control` routing helpers.

If all attempts are hollow → `status=failed`, `terminal_status=failed_quality_gate`.

## Runner order (fix + publish)

```text
apply_fix_to_workspace → raw_patch.diff
→ run_closed_world_diff_gate → patch.diff
→ evaluate_patch_artifact
→ run_publish_preflight (when publish enabled)
→ publish_fix_branch_and_pr
```

Empty `patch.diff` blocks `_attempt_remote_publish`.

## Fake planner file scope

`task_scope.extract_explicit_files_from_task` parses patterns like `files must be ["README.md"]` and `Update README.md`. Fake engine uses `pick_plan_step_files` instead of defaulting to pseudo-sources (`gitea_issue`).

## Honest 6D comments

`format_fix_started(..., remote_publish_enabled: bool)` — pure formatter in `gitea_comments.py`; caller passes `fix_remote_publish_enabled(settings)` from `handlers.py`.

## Git worker identity

`config/git-worker.gitconfig` includes `[user]` name/email; mounted as `/root/.gitconfig` in CT104 compose.

## Homelab bridge (until 6D.2)

| Host | Role | Config |
|------|------|--------|
| **CT103** | Enqueue | `MODEL_ROUTING_POLICY=official` for plan; `fake` before fix enqueue; `FIX_REMOTE_PUBLISH_ENABLED=true` |
| **CT104** | Execute | `MODEL_EXTERNAL_ROLES=rlm` + `MODEL_3080_EXTERNAL_*`; git identity via gitconfig mount |

Planning **execution** runs on CT104 — external endpoint config belongs on **CT104** `.env`.

## Deploy order

1. CT104 (engine, runner, preflight, gitconfig)
2. CT103 (`gitea_comments` only)
3. Homelab: enable external fallback on CT104; replan issue #18

## Tests

```bash
pytest -q tests/test_output_quality_gate.py tests/test_fix_quality_gate.py \
  tests/test_quality_fallback.py tests/test_runner_quality_gate.py \
  tests/test_publish_preflight.py tests/test_fake_plan_run.py tests/test_gitea_comments.py
```
