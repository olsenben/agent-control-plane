# Slice 6E — CT102 CI Truth Loop (6E.1 observe/aggregate + 6E.2 verified memory)

**Status:** implemented + homelab signed off (2026-07-14)  
**Prerequisite:** [slice-6d-branch-push-pr.md](slice-6d-branch-push-pr.md) (`pr_opened_pending_ci` + immutable `head_commit_sha`)  
**Host:** CT102 (Gitea Actions) observed by CT103  
**Homelab:** issue #19 / [PR #20](https://git.ham-sup-lo.com/ai-sdlc-lab/agent-control-plane/pulls/20) / fix `run-cf4c2b2e…` @ `ef22f721…` → verdict=`verified`, memory `ci_verified`, comment `rev1`

## Thesis

```text
CT102 executes workflows
Gitea records workflow-run state
Webhook notifies CT103 that state may have changed
CT103 verifies via Gitea Actions API (authoritative)
Reducer derives aggregate verdict
Memory only after verdict=verified (6E.2)
```

Preserved invariants:

- Agent does **not** merge.
- Memory withheld until CI **verified**.
- Exact `head_commit_sha` from 6D is the primary correlation key.
- Webhook is a **signal**; Gitea Actions API is **authoritative state**.

**Limitation:** Gitea PR workflows use the PR head ref (agent branch commit), not a merge-preview into latest base. 6E verifies the agent branch SHA from 6D.

## Scope split

| Slice | In | Out |
|-------|----|-----|
| **6E.1** | Pending index, exact-SHA correlate, API confirm, multi-workflow aggregate, append-only events, reconciler, comments/CLI | Memory writeback |
| **6E.2** | Verified-only memory upsert, operator UX, AGENT_CARD | CI observation logic |

---

## Phase 0 — Payload contract (Gitea 1.26)

Captured field contract for correlation (sandbox / docs spike). Live capture on homelab should re-validate these names against a real `workflow_run` delivery.

### Webhook `X-Gitea-Event: workflow_run`

| Field path | Use |
|------------|-----|
| `repository.full_name` | Repo allow-list + pending index key |
| `workflow_run.id` | `workflow_run_id` |
| `workflow_run.run_attempt` / `attempt` | Attempt (rerun semantics) |
| `workflow_run.status` | `completed` / `in_progress` / … |
| `workflow_run.conclusion` | `success` / `failure` / `cancelled` / … |
| `workflow_run.head_sha` | **Primary correlation SHA** |
| `workflow_run.path` / `workflow_path` | Workflow identity (prefer over display name) |
| `workflow_run.workflow_id` | Stable workflow id when present |
| `workflow_run.name` / `display_title` | Display only (collision-prone) |
| `workflow_run.pull_requests[].number` | Supporting evidence only |
| `X-Gitea-Delivery` | Webhook delivery idempotency |

v1 processes **terminal** runs only (`status=completed` or non-empty `conclusion`). `gitea.workflow_started` is ignored for observation.

### Actions API (authoritative)

```text
GET /api/v1/repos/{owner}/{repo}/actions/runs/{run}
GET /api/v1/repos/{owner}/{repo}/actions/runs?head_sha={sha}&limit=50
```

Response fields mirrored: `id`, `head_sha`, `status`, `conclusion`, `run_attempt`, `path`, `name`, `workflow_id`.

**If API contradicts webhook → trust API.**

---

## 6E.1 — Observation, correlation, aggregate

### Correlation

- **Primary key:** `repository` + exact `head_commit_sha`
- PR number is supporting / disambiguation only
- Exact PR + **wrong SHA** → no correlate
- Same SHA in another repo → no correlate
- New commit on same agent PR → older pending **superseded**

### Aggregate model

`CiVerificationResult` (`ci_verification_result.v1`):

- `verdict`: `pending` | `verified` | `failing` | `superseded` | `expired`
- `required_workflows` from CI matrix / `FIX_CI_REPO_DEFAULT_WORKFLOW`
- `observations[]` with normalized conclusion (unknown → fail closed)

**Verdict rules:**

- `verified` only when **every** required workflow has success for the **exact** expected SHA
- `failing` when any required workflow’s **latest** terminal attempt failed / cancelled / timed_out / unknown
- Empty matrix → repo-default workflow **or** remain `pending` with `empty_required_matrix` — **never** “any green docker-ci counts”

**Rerun:** `pending → failing → verified`. A newer successful attempt for the same required workflow + exact SHA may replace an older failed attempt. Do **not** terminal-resolve pending on first failure.

### Append-only events

- Original `agent.run_completed` stays immutable with `fix_status=pr_opened_pending_ci`
- Later: `agent.fix_ci_observed`, `agent.fix_ci_verdict_changed`
- **Never** patch historical run-completed payloads

### Artifacts

```text
ci/
  observation-<workflow_run_id>-attempt-<n>.json   # immutable
  verification-current.json                       # atomic reducer snapshot
```

### Security

1. Webhook signature/secret verification  
2. Repository allow-list  
3. Event-type validation  
4. API confirmation with trusted Gitea credentials  

### Feature flags (CT103)

| Env | Default | Purpose |
|-----|---------|---------|
| `FIX_CI_OBSERVE_ENABLED` | `false` | Master switch for 6E.1 |
| `FIX_CI_REQUIRE_MATRIX_MATCH` | `true` | Enforce required_workflows from matrix / repo default |
| `FIX_CI_REPO_DEFAULT_WORKFLOW` | `.gitea/workflows/ci.yaml` | Default when matrix empty |

### CLI

```bash
agentctl fix pending-ci --repo owner/repo
agentctl fix ci-status --run-id run-xxx --repo owner/repo
agentctl fix ci-reconcile --repo owner/repo
```

### Reconciliation

Startup / periodic / CLI `ci-reconcile` polls Actions API for pending records (webhook-only finalization is rejected).

---

## 6E.2 — Verified memory + operator UX

- Memory upsert **only** when reducer verdict = `verified`
- `memory_quality=ci_verified`
- Idempotent by `fix_run_id + head_commit_sha`
- No memory while `failing` / `pending` / `superseded`
- Comments include hidden marker `<!-- agent-ci-status:{fix_run_id}:rev{n} -->`
- Comment failure must **not** roll back ledger events

---

## Implementation map

| Piece | Path |
|-------|------|
| Models | `src/agent_shared/models/ci.py` |
| Pending index | `src/agent_control/ci/pending.py` |
| Aggregate | `src/agent_control/ci/aggregate.py` |
| Observe + API | `src/agent_control/ci/observe.py` |
| Events | `src/agent_control/ci/events.py` |
| Artifacts | `src/agent_control/ci/artifacts.py` |
| Reconcile | `src/agent_control/ci/reconcile.py` |
| Memory | `src/agent_control/ci/memory.py` |
| Register on ingest | `src/agent_control/results_ingest.py` |
| State worker hook | `src/agent_control/jobs/state.py` |
| Gitea Actions client | `GiteaClient.get_workflow_run` / `list_workflow_runs` |

## Homelab acceptance (2026-07-14)

| Gate | Result |
|------|--------|
| `FIX_CI_OBSERVE_ENABLED=true` on CT103 | Pass |
| Pending index (backfill for pre-6E PR #20) | Pass — exact SHA `ef22f721…` |
| `ci-reconcile` Actions API confirm | Pass — runs 449/450 success |
| Path match (`ci.yaml@refs/…` ↔ `.gitea/workflows/ci.yaml`) | Pass after path-normalize fix |
| Verdict `verified` / `missing_workflows=[]` | Pass |
| Comment `<!-- agent-ci-status:…:rev1 -->` on issue #19 | Pass |
| Memory `memory_quality=ci_verified` | Pass — `mem-run-cf4c2b2e…-ef22f72179c7` |
| Append-only `agent.fix_ci_*`; run_completed still `pr_opened_pending_ci` | Pass |
| Agent did not merge | Pass |

**Next:** Slice **6F.1** failure evidence is implemented in-tree (flag off by default). Enable `FIX_CI_FAILURE_EVIDENCE_ENABLED` after live jobs/logs contract probe. **6F.2** repair stays gated on sandbox attestation + `repair_allowed`. See [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md). Alternate hardening: official-engine 6D+6E once-through; land remaining 5.2 harden WIP on a separate branch.

## Related

- [slice-6d-branch-push-pr.md](slice-6d-branch-push-pr.md)
- [architecture.md](architecture.md)
- [POLICY_GATES.md](POLICY_GATES.md)
- [AGENT_CARD.md](AGENT_CARD.md)
