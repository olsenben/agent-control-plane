# Slice T03 — V4.1.2 exit (sessions + selective writeback)

**Status:** Deploy verified 2026-07-20 (review→plan memory loop)  
**Epic ticket:** T03  
**Tip:** `d581fe0` / code `a7dd4c5`  
**Umbrella:** [slice-v412-typed-sessions.md](slice-v412-typed-sessions.md)

## Goal

Prove V4.1.2 DoD for typed sessions + preflight + verification + selective writeback on demo-app: queryable sessions and second-command memory retrieval.

## Evidence (2026-07-20)

| Step | Result |
|------|--------|
| CT104 git-credentials | Repaired (`%3a` → literal `:3000`); policy clone `CLONE_OK` |
| `/agent review` demo-app#2 | `sess-63968c4e…` / `run-9c8ff995…` finished |
| Ledger | `verification_missing` → `session_finished` → `memory_admitted` |
| Memory row | `mem-run-9c8ff995…` `epistemic_status=inferred` `admission_policy_version=session_trace_5.7.0` |
| `/agent plan` | `sess-57eaa725…` / `run-2a8ad7fa…` finished + `memory_admitted` |
| Prior memory | `context_pack.prior_memory[0]` cites review `session_id` + `run_id` + `epistemic_status=inferred` |

```text
DEPLOY_VERIFY: PASS
tip: a7dd4c5 (docs tip d581fe0)
next_slice_unblocked: yes
blocker: none
```

## Residual

- Bare `/agent fix` without a plan-scoped WI did not dispatch a new session in this exit window.
- Prior queryable fix sessions exist (e.g. 5.4b `sandbox_unavailable` / `human_approval_required`).
- Full fake-fix publish path remains covered by demo 6D/6F.2 + T09 non-demo expansion.

## Follow-on

- **T04** adequacy profile / scoped verification claims
- **T05+** Orbit graph / 2070 recursive context
