# Slice 6B — Local Patch Artifact (Fix Worker)

After Slice 6A approval, CT103 enqueues a CT104 fix job. CT104 produces **workspace-local patch artifacts only** — no push, PR, full 6C gate, or CI execution.

**Prerequisite:** [slice-6a-approval-plumbing.md](slice-6a-approval-plumbing.md)

**Progression:** 6A approval → **6B local patch** → 6C diff gate → 6D push/PR → 6E CT102 CI

## Scope boundary (6B vs 6C)

| Layer | 6B (this slice) | 6C (deferred) |
|-------|-----------------|---------------|
| Requested paths | Each `change.path` ∈ `allowed_files` | — |
| Post-apply | `git diff --name-only` → changed ⊆ allowed | — |
| Push/PR | **None** | — |
| Diff size limits | — | max lines/files |
| Protected config | `.gitea/`, `.agent/`, `docs/adr/` block | full closed-world policy |
| Secret scan | — | yes |
| Lockfile / generated files | — | yes |
| Blast-radius consistency | echoed only | enforced |
| Required tests | `ci_hints` echoed only | selected CI matrix |

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
- Artifacts: `fix_result.json`, `patch.diff`, `RLMResult.patch_path`
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
3. CT104 completes → Gitea fix comment + `fix_result.json` + `patch.diff`
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
| `test_fake_fix_run.py` | fake E2E → patch.diff + ingest |
| `test_fix_parser.py` | Slice 5 fix boundary |

## Fix MVP slice map

| Slice | Scope | CT104 writes? |
|-------|-------|---------------|
| 6A | Approval plumbing | No |
| **6B** | **Local patch artifact** | **Workspace only** |
| 6C | Closed-world diff gate | No push |
| 6D | Branch push + PR | Agent branch |
| 6E | CT102 CI truth loop | Observe only |
