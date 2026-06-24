# Slice 6C — Closed-World Diff Gate

After Slice 6B local patch apply, CT104 runs a **deterministic closed-world diff gate** before promoting `patch.diff`. No push, PR, or CT102 dispatch.

**Prerequisite:** [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md)

**Progression:** 6A approval → 6B local patch → **6C diff gate** → 6D push/PR → 6E CT102 CI

## Core boundary

| Slice | Proves |
|-------|--------|
| 6B | Model can produce a local patch artifact |
| **6C** | Patch is still inside the approved, policy-compliant world |
| 6D | Push branch / PR (later) |
| 6E | CT102 CI truth (later) |

## Policy layering (6B vs 6C)

```text
6B apply-time path guard:
  - path traversal / absolute paths / workspace escape
  - hard block .gitea/, .agent/, docs/adr/ (PROTECTED_PREFIXES)
  - per-change path ∈ allowed_files
  - post-apply git diff ⊆ allowed_files

6C diff gate:
  - evaluates policy for patches that made it through apply
  - content-level checks (secrets, test weakening, size limits)
  - requires_elevated_approval paths, lockfiles, generated state
  - blast-radius / plan-scope consistency
  - untracked file detection (git ls-files --others)
```

Some `always_denied` paths never reach 6C because 6B blocks them first — intentional (safety over unified violation messaging).

## Scope boundary (6C vs 6D)

| Layer | 6C (this slice) | 6D (deferred) |
|-------|-----------------|---------------|
| Gate | Post-apply closed-world policy | Re-check before push |
| Artifacts | `raw_patch.diff`, promoted `patch.diff`, `diff_gate_result.json` | agent branch |
| Push/PR | **None** | agent branch + PR |
| CI | matrix echo only (`dispatch: deferred_6e`) | CT102 dispatch (6E) |

## Flow

```text
apply_fix_to_workspace
  → write raw_patch.diff
  → collect changed_files (tracked diff ∪ untracked)
  → run_closed_world_diff_gate
  → write diff_gate_result.json
  → if pass: promote raw_patch.diff → patch.diff
  → if fail: error.json; no patch.diff
  → report queue → inbox ingest (pass or fail)
```

Implementation: `agent_workers/gates/runner.py` wired from `agent_workers/flows/runner.py` after `POST_APPLY_DIFF_ASSERT`.

## Artifact semantics

| Artifact | When |
|----------|------|
| `raw_patch.diff` | Always after apply (operator debug on failure) |
| `patch.diff` | Only if gate passes |
| `diff_gate_result.json` | Always — full audit payload |
| `error.json` | Gate fail — `stage: diff_gate`, `violations[]` |

On gate fail: Gitea comment and downstream artifacts must not treat the patch as approved. `raw_patch.diff` remains for inspection.

## Policy source

1. Repo: `.agent/policies/closed_world.yaml`
2. Platform fallback: `agent_workers/config/platform_default/closed_world.yml`
3. Generated paths merged from `.agent/project.yaml` `state.generated_files`

Canonical key: `requires_elevated_approval` (Risk 2 approval does **not** cover dependency manifests, workflows, lockfiles, ADRs, generated state). Legacy alias: `requires_human_approval`.

## Gate checks (collect all violations)

1. Diff size limits (`max_files_changed`, `max_diff_lines`)
2. `always_denied` paths
3. `requires_elevated_approval` paths — fail even if ∈ `allowed_files`
4. Out-of-scope paths (includes untracked outside allowlist)
5. Lockfile / dependency manifest edits
6. Generated-state edits
7. Secret scan — **added lines only**; pattern-based (no entropy)
8. Test deletion / weakening — `test_weakening_detected`
9. Blast-radius hash + graph drift (skip graph rules when `missing_graph_edges` only)
10. Plan scope drift — **warning** by default (`plan_scope_drift`)
11. CI matrix echo — `selected_ci_matrix` with `dispatch: deferred_6e`

## Session events

- `raw_patch_written`
- `diff_gate_started` / `diff_gate_passed` / `diff_gate_failed`

## Ingest on gate failure

```text
no memory_record.v1 writeback (fix excluded from memory mapper)
yes error.json + diff_gate_result.json + raw_patch.diff
yes agent.run_completed with status=failed, policy_decision=deny, diff_gate_* fields
yes Gitea failure comment (violation codes only, secrets redacted)
```

## Homelab acceptance (strict)

1. Gate pass → `patch.diff` + `diff_gate_result.json` + CI matrix echo
2. Session events include `diff_gate_passed`
3. Induced secret → `diff_gate_failed`; no `patch.diff`; `raw_patch.diff` exists
4. `pyproject.toml` in `allowed_files` → `elevated_approval_required`
5. Oversize diff → blocked
6. `blast_radius_hash` tamper → `blast_radius_hash_mismatch`
7. Remote unchanged — no branch, no PR
8. Ingest pass → `command_kind=fix`, gate metadata present
9. Failed gate: no `patch.diff`, `raw_patch.diff` for inspection
10. Untracked file outside `allowed_files` → blocked
11. Gitea failure comment: violation codes only, no secret literals
12. `diff_gate_result.json`: policy sources, approval IDs, blast-radius hashes
13. Gate fail ingested as `agent.run_completed` with `policy_decision=deny`
14. Deploy: `MODEL_ROUTING_POLICY=fake` E2E first

## Tests

| Test | Covers |
|------|--------|
| `test_closed_world_policy.py` | glob matching, YAML load, platform fallback |
| `test_diff_gate_policy_alias.py` | `requires_human_approval` alias |
| `test_diff_gate_policy_source_audit.py` | policy sources in result |
| `test_diff_gate.py` | each violation type |
| `test_diff_gate_blast_radius.py` | hash, ci_hints, test drift, graph skip |
| `test_diff_gate_ci_matrix.py` | matrix echo + selection_source |
| `test_diff_gate_plan_scope.py` | warning vs hard fail |
| `test_diff_gate_untracked_files.py` | untracked detection |
| `test_diff_gate_artifact_promotion.py` | raw vs promoted patch |
| `test_diff_gate_redacts_secret_in_comment.py` | comment redaction |
| `test_fake_fix_run.py` | fake E2E with gate |
| `test_fix_failure_reports_inbox.py` | gate fail → inbox deny |

## Fix MVP slice map

| Slice | Scope | CT104 writes? |
|-------|-------|---------------|
| 6A | Approval plumbing | No |
| 6B | Local patch artifact | Workspace only |
| **6C** | **Closed-world diff gate** | **Workspace only** |
| 6D | Branch push + PR | Agent branch |
| 6E | CT102 CI truth loop | Observe only |

## Related

- [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md)
- [POLICY_GATES.md](POLICY_GATES.md)
- [THREAT_MODEL.md](THREAT_MODEL.md) — `secret_exposure` tag
