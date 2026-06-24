# Slice 5.2 — Plan Quality Gate

**Status:** planned  
**Prerequisite:** [slice-5-structured-output-hardening.md](slice-5-structured-output-hardening.md) (complete)  
**Recommended before:** official-engine fix testing at scale; **before 6D**

## Thesis

Empty or hollow plans that parse successfully are a **plan validation problem**, not a fix-time problem. A plan with no scoped files must not produce an approval-ready `WI-*` section that looks fixable.

## Problem (observed)

Homelab issue #9: plan parsed with `(none)` steps/files → approve granted with `Allowed files: (none)` → fix blocked at enqueue. Confusing UX; wasted approval cycle when combined with consume-on-enqueue semantics.

## PlanQualityGate

Run after Slice 5 parse/normalize, before plan comment render and memory writeback.

| Check | Rule |
|-------|------|
| Steps | Non-empty for fixable plans |
| Scoped files | At least one path in `steps[].files` when plan recommends fix |
| Blast radius | Present (from premerge / context_pack) |
| Prior memory | `prior_memory_used` populated when `context_pack.prior_memory` was supplied |
| CI hints | Optional but preferred (warn, not block) |

### On failure

- Gitea comment: plan generated but **not fixable**; list missing items
- Suggested next command: `/agent plan` with explicit target files
- **Do not** emit approval-ready `WI-*` / `Allowed files` section for hollow plans
- Status: `plan_result.v1` with `fixable: false` or dedicated quality gate artifact

## Implementation

**Files (expected):**

- `src/agent_workers/rlm/plan_quality.py` — gate logic
- Wire in `plan_finalize.py` after validation, before comment render
- Tests: empty steps, no files, missing blast_radius when pack had data

## Acceptance criteria

1. Hollow plan → Gitea comment states not fixable; no `WI-*` approval block
2. Good plan → unchanged approval-ready output
3. `/agent approve` on hollow plan target blocked or warned at CT103 (if WI still emitted for audit, fix remains blocked)
4. Unit tests cover issue #9-shaped empty plan fixture

## Out of scope

- Re-plan automation
- Model prompt changes (see Slice 5.1 Phase 7)

## Related

- [slice-5.1-engine-reliability.md](slice-5.1-engine-reliability.md)
- [slice-6a-approval-plumbing.md](slice-6a-approval-plumbing.md)
- [POLICY_GATES.md](POLICY_GATES.md)
