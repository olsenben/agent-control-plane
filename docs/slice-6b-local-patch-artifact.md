# Slice 6B — Local Patch Artifact (Fix Worker)

After Slice 6A approval, CT103 enqueues a CT104 fix job. CT104 produces **workspace-local patch artifacts** — `raw_patch.diff` always; `patch.diff` only after Slice 6C gate passes. No push, PR, or CI execution.

**Prerequisite:** [slice-6a-approval-plumbing.md](slice-6a-approval-plumbing.md)

**Progression:** 6A approval → **6B local patch** → 6C diff gate → 6D push/PR → 6E CT102 CI

## Scope boundary (6B vs 6C)

| Layer | 6B (this slice) | 6C (next) |
|-------|-----------------|-----------|
| Requested paths | Each `change.path` ∈ `allowed_files` | — |
| Post-apply | `git diff --name-only` → changed ⊆ allowed | closed-world diff gate |
| Artifacts | `raw_patch.diff` | promoted `patch.diff` on gate pass |
| Push/PR | **None** | **None** (6D) |

## Audit chain

```text
human.approval_granted
  → agent.fix_requested(approved)
  → agent.fix_authorized
  → agent.approval_consumed
  → agent.fix_enqueued
  → agent.run_completed
```

Approval is consumed **only** when Redis `enqueue_rlm_root` succeeds. Empty `allowed_files` blocks before enqueue (approval not consumed).

## CT103 enqueue

- `build_fix_rlm_job` in `agent_control/approval/dispatch_fix.py`
- Compact `FixAuthorizationBinding` on `RLMJob.fix_authorization` (not full memory blob)
- `compile_context_pack(..., command_kind="fix", changed_files=allowed_files)`
- Safety: `allow_repo_write=True`, `allow_push=False`, `allow_test_execution=False`

## CT104 apply

- Shared path validation: `agent_shared/patch_paths.py`
- `apply_fix_to_workspace` in `agent_workers/patch/apply.py`
- Artifacts: `fix_result.json`, `raw_patch.diff` (`patch.diff` after 6C gate)
- Apply/parse failures: `error.json`, Gitea failure comment, inbox ingest — **no memory writeback**

## Structured output

FixResult (`fix_result.v1`) via Slice 5 boundary: `fix_parser`, `fix_finalize`, `normalize_fix_dict`, `premerge`, `validate_or_repair(kind="fix")`.

Edit semantics:

| edit_kind | Rule |
|-----------|------|
| `replace` | Path exists in workspace and ∈ `allowed_files` |
| `create` | Path ∈ `allowed_files`; file must not exist |
| `append` | Path exists and ∈ `allowed_files` |

## Deploy order

1. **`MODEL_ROUTING_POLICY=fake`** — prove approval → enqueue → patch → ingest E2E
2. Official engine on one trivial allowed-file plan

## Homelab acceptance (strict)

On issue with review + plan chain:

1. Owner `/agent approve WI-xxxx`
2. Owner `/agent fix WI-xxxx` → `fix_authorized` + `approval_consumed` + `fix_enqueued` + new `run-*`
3. CT104 completes → Gitea fix comment + `fix_result.json` + `raw_patch.diff` + promoted `patch.diff`
4. `git diff --name-only` inside run workspace ⊆ `allowed_files` only
5. `git status` — only allowed files modified
6. **Remote unchanged:** no new Gitea PR; `main`/remote branches unchanged
7. `agentctl results ingest --inbox` → `command_kind=fix`
8. Approval consumed exactly once; second fix blocked
9. Empty plan file scope → blocked before enqueue
10. Induced apply failure → Gitea **failure** comment + inbox artifact

## Tests

| Test | Covers |
|------|--------|
| `test_patch_paths.py` | normalize + validate + protected prefixes |
| `test_fix_enqueue_6b.py` | enqueue + `fix_enqueued`; empty allowlist; no consume on failure |
| `test_fix_after_approval.py` | authorize without consume; handler enqueue |
| `test_fix_post_apply_diff_subset.py` | post-apply subset assert |
| `test_fix_failure_reports_inbox.py` | apply failure → inbox; no-push guard |
| `test_fake_fix_run.py` | fake E2E → raw_patch.diff + patch.diff + diff_gate_result.json + ingest |
| `test_fix_parser.py` | Slice 5 fix boundary |

## Fix MVP slice map

| Slice | Scope | CT104 writes? |
|-------|-------|---------------|
| 6A | Approval plumbing | No |
| **6B** | **Local patch artifact** | **Workspace only** |
| **6C** | Closed-world diff gate | No push |
| 6D | Branch push + PR | Agent branch |
| 6E | CT102 CI truth loop | Observe only |

## Homelab sign-off status (2026-06-22)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Fake E2E (approve → patch → ingest) | **Pass** | issue #8; `run-025ff111…`; approval consumed once |
| Official review + plan with real file | **Pass** | issue #9; review `README.md`; plan `WI-0009-cc26b3de` with `allowed_files: [README.md]` |
| Official fix local patch | **Fail** | issue #9; `run-2fc4eff…` parse failure (prose, not FixResult JSON); approval consumed |
| Strict checklist #10 (parse fail → Gitea + inbox) | **Gap** | `parse_failure.json` + `error.json` on CT104; report worker not reached |
| Pytest 6B suite | **Pass** | CI / local |

**Slice 6B code scope:** closed (implemented + unit/integration tests green).

**Strict homelab sign-off:** acceptable with issue #8 fake E2E; issue #9 adds official review/plan + enqueue/consume proof. A successful **fake** fix on `README.md` (issue #9 or #10) closes the remaining polish item without blocking 6C.

## Follow-up (tracked as dedicated slices)

Homelab pain points from 6B sign-off are now explicit roadmap slices. **6D branch push is blocked until 5.1 + 4C land.**

| Gap | Slice | Doc |
|-----|-------|-----|
| Ingest lag / plan lookup false negatives | **4C** | [slice-4c-result-ingest-automation.md](slice-4c-result-ingest-automation.md) |
| Official-engine prose / silent parse failures | **5.1** | [slice-5.1-engine-reliability.md](slice-5.1-engine-reliability.md) |
| Hollow plans look fixable | **5.2** | [slice-5.2-plan-quality-gate.md](slice-5.2-plan-quality-gate.md) |
| Bare review/plan leaves `Task:` empty on issues | **5.3** | [slice-5.3-issue-task-backfill.md](slice-5.3-issue-task-backfill.md) |
| Approval consumed on enqueue | **6C polish** | [slice-6c-closed-world-diff-gate.md](slice-6c-closed-world-diff-gate.md) — reservation lifecycle before 6D |

**Interim (homelab):** cron or manual ingest ([deploy.md](deploy.md#result-ingest-ct103)); `MODEL_ROUTING_POLICY=fake` for fix/6C acceptance runs.
