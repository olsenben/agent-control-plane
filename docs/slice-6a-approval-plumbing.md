# Slice 6A — Risk 2 Approval + Dispatch Plumbing

CT103-only approval plumbing: scoped plan-revision handles, idempotent ledger events, Gitea block/confirm comments, owner-only authorization. **No CT104 writes, no patch generation, no branch push.**

## Approval handle vs durable WorkItem

| Term | Slice 6A | Future |
|------|----------|--------|
| `approval_target_id` | `WI-0004-dc0b71eb` — plan-scoped handle for one plan run | `WI-0004` durable epic WorkItem |
| `plan_alias` | `PLAN-run-dc0b71eb` — immutable plan revision alias | Same |
| `approval_id` | Hash-bound grant tying target + plan run + hashes | Approval of durable WI + plan revision |

A Slice 6A approval **must not** apply to a revised plan on the same issue. New plan run → new `approval_target_id` → new approval.

Derivation at plan completion:

- `approval_target_id = WI-{issue:04d}-{plan_run_id[-8:]}`
- `plan_alias = PLAN-run-{plan_run_id[-8:]}`

Both are accepted for `/agent approve` and `/agent fix`.

## Hash rules

| Hash | Source | Exclusions |
|------|--------|------------|
| `plan_hash` | Finalized `PlanResult` after Slice 5 normalization | `recommended_next_command`, `prior_memory_used`, `approval_target_id`, `plan_alias` |
| `blast_radius_hash` | `context_pack.blast_radius` (CT103-owned) | Canonical JSON sort |

## Allowed files

Structured only — from `plan_result.steps[].files`. Empty scope: approval may be granted (dry-run marker); patch generation blocked until 6B replan.

## Ledger events

| Event | When |
|-------|------|
| `agent.fix_requested` | Every scoped `/agent fix` (`policy_decision`: blocked \| approved) |
| `human.approval_granted` | Owner approve success (full `WorkItemApproval`) |
| `human.approval_rejected` | Owner reject success |
| `agent.fix_authorized` | Approved fix; `worker_enqueued=false` until enqueue succeeds |
| `agent.approval_consumed` | Approval consumed on successful Redis enqueue (Slice 6B) |
| `agent.fix_enqueued` | CT104 job enqueued (`dispatch_target=rlm-root`) |

See [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md) for the full 6B audit chain.

## Idempotency

Deterministic event IDs:

```text
deterministic_event_id(
  source="ct103",
  delivery_id="{comment_id}:{command_kind}:{project}:{issue_id}:{approval_target}",
  event_type="human.approval_granted",
)
```

Webhook retries: `append_event` `created=False` skips duplicate side effects.

## Authorization

- `/agent approve` and `/agent reject`: **owner only** — comment author matches repo namespace segment (`owner/repo`) **or** is listed in `GITEA_APPROVER_LOGINS` on CT103
- Non-owner fix: may emit `fix_requested(blocked)`; execution not authorized
- Approval consumed **only** on successful Redis enqueue (Slice 6B); see [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md)

## CLI

```bash
agentctl approvals list --repo owner/repo --issue 4
agentctl approvals show WI-0004-dc0b71eb --repo owner/repo
agentctl approvals grant --repo owner/repo --issue 4 --approval-target WI-0004-dc0b71eb --approver owner
```

## Homelab acceptance checklist

On `agent-control-plane` after review + plan on an issue:

**Timing:** On a newly opened issue, wait a few seconds before the first `/agent` command. Comments posted immediately after issue creation may not enqueue CT104; re-post once if no response within ~30s.

1. `/agent fix WI-xxxx` without approval → blocked comment + `fix_requested(blocked)`
2. Owner `/agent approve WI-xxxx` → one `human.approval_granted`
3. Owner `/agent fix WI-xxxx` → `fix_authorized` + `approval_consumed` + `fix_enqueued` (Slice 6B)
4. Repeat fix with same approval → blocked (consumed)
5. Non-owner `/agent approve` → rejected comment; no approval file
6. Replay same approve comment webhook → no duplicate approval event
7. Ledger chain: `review → plan → fix_requested(blocked) → approval_granted → fix_requested(approved) → fix_authorized`

Homelab sign-off: issue #6 (initial, CLI grant workaround); issue #7 retest (full Gitea approve path after `GITEA_APPROVER_LOGINS`).

Verify with:

```bash
agentctl approvals list --repo ai-sdlc-lab/agent-control-plane --issue 7
agentctl approvals show WI-0007-68922c7f --repo ai-sdlc-lab/agent-control-plane
```

## Fix MVP slice map

| Slice | Scope | CT104 writes? |
|-------|-------|---------------|
| **6A** | Approval plumbing + `fix_authorized` | No |
| **6B** | Local patch artifact | Workspace only — [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md) |
| 6C | Closed-world diff gate | No push |
| 6D | Branch push + PR | Agent branch |
| 6E | CT102 CI truth loop | Observe only |
