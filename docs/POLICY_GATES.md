# Policy gates (minimum viable governance)

Proportional AI governance embedded in the workflow — not bolted-on bureaucracy. Aligns with MIT CISR minimum viable governance: auditable trails of prompts, outputs, and human decisions as platform-level controls.

See [AGENT_CARD.md](AGENT_CARD.md) for the product summary.

## Risk classes

| Class | Commands | Repo access | Auto-run | Memory write | Gitea comment | Approval |
|-------|----------|-------------|----------|--------------|---------------|----------|
| **Risk 0** | `inspect`, `explain` | Read-only clone | Yes | No | Yes | None |
| **Risk 1** | `review`, `plan` | Read-only clone | Yes | Selective | Yes | None |
| **Risk 2** | `fix` | Agent branch only | No | Yes | Yes | **Required before dispatch** |
| **Risk 3** | `deploy`, `migrate`, `secrets`, … | Blocked | No | No | No | One-off human override + manual verification |

Risk class is declared in `.agent/flows.yml` per flow and enforced in CT103 `dispatch.py` before enqueue.

## Gate evaluation order

```text
1. Webhook guard (HMAC, allowlist, dedupe)
2. Command intent parse + risk class lookup
3. Public surface restriction (if enabled)
4. Policy gate: command allowed for repo/project?
5. Human approval check (Risk 2+)
6. Memory-as-governance check (later): bad history on file/failure mode?
7. Graph gate (Fix MVP): plan names affected components + required CI checks?
8. Dispatch enqueue to CT104
9. CT104 closed-world diff gate (Slice 6C) — after local patch apply
```

Write-capable commands **fail closed** if any gate fails.

## Risk 0 — inspect / explain

```yaml
repo_access: read_only
auto_run: true
allowed_side_effects:
  - gitea_comment
  - session_artifacts
  - event_ledger_append
blocked:
  - git_push
  - memory_writeback
  - branch_create
```

## Risk 1 — review / plan

```yaml
repo_access: read_only
auto_run: true
required_outputs:
  - structured_findings
  - confidence
  - risk_tags
  - suggested_next_action
  - rejected_or_uncertain_hypotheses
allowed_side_effects:
  - gitea_comment
  - selective_memory_writeback
  - graph_consultation_required  # CT103 must attach blast-radius for review
blocked:
  - git_push
  - file_write
```

Review findings are **hypotheses**, not verified truth.

## Risk 2 — fix

Slice **6B+6C** (current): After approval, CT103 enqueues CT104 fix worker. CT104 applies workspace-local changes, runs closed-world diff gate, writes `raw_patch.diff` and promotes `patch.diff` only on gate pass. See [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md) and [slice-6c-closed-world-diff-gate.md](slice-6c-closed-world-diff-gate.md). Slice 6A: [slice-6a-approval-plumbing.md](slice-6a-approval-plumbing.md).

```yaml
repo_access: branch_write_only
auto_run: false
human_approval_event: human.approval_granted
fix_authorized_event: agent.fix_authorized   # before enqueue
fix_enqueued_event: agent.fix_enqueued       # CT104 job created (6B)
required_before_dispatch:
  - prior_review_or_plan_memory
  - blast_radius_acknowledged
  - owner_approval_on_plan_scoped_target   # WI-{issue}-{run_suffix} or PLAN-run-{suffix}
  - sandbox_available                      # 6B+
allowed_side_effects:
  - agent_branch_push
  - gitea_comment
  - pr_open
  - memory_writeback
blocked:
  - push_to_protected_main
  - workflow_file_edit_without_hitl
  - adr_modification_without_hitl
```

Success means: branch, diff, logs, test output, **CT102 CI status** — not model self-assessment.

## Risk 3 — deploy / migrate / secrets

```yaml
default: blocked
override: explicit_one_off_human_approval
required:
  - manual_verification
  - ct102_ci
  - audit_event_with_risk_tags
```

## Verification invariant (MIT Sloan)

No model output is considered true until validated by:

1. **Deterministic checks** — schema validation, closed-world diff gate, policy rules
2. **Tests** — repo unit/integration tests
3. **CT102 CI** — authoritative; model self-review is not a substitute
4. **Human approval** — where risk class requires it

Using AI to check AI without independent verification creates false confidence when both share assumptions.

## Event audit fields

Every CT103 event should carry (target):

```yaml
risk_class: 0|1|2|3
risk_tags: [string]          # see THREAT_MODEL.md
policy_decision: allow|deny|pending_approval
approval_id: string | null
graph_consulted: bool
memory_retrieved: bool
run_id: string
```

## Agent identity (AgentFacts-lite, target)

Before A2A/MCP as protocol glue, enforce capability discipline:

```yaml
agent_identity:
  name: worker-review
  host: CT104
  commands_allowed: [review, explain]
  repo_access: read_only
  can_write_memory: true
  can_write_repo: false
  can_comment_gitea: true
  model_endpoint: 3080-qwen
  signed_by: CT103
```

Future: CT103-signed capability manifest per worker role. See §0.5 in V4 plan.

## Related docs

- [THREAT_MODEL.md](THREAT_MODEL.md) — risk tag taxonomy
- [security.md](security.md) — prompt injection, public surface
- [AGENT_CARD.md](AGENT_CARD.md) — transparency card
