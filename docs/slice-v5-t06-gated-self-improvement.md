# Slice V5 T06 — Gated self-improvement (workflow/prompt proposals as PRs only)

**Status:** Done — deploy verify PASS tip `7b01adc` (2026-07-20)  
**Date:** 2026-07-20  
**Epic ticket:** T06  
**Deps:** T02 + T03 Done (`f2b8ce9` / `5ca8d78`)  
**ADR:** [0025-gated-self-improvement-prs.md](adr/0025-gated-self-improvement-prs.md)

## Goal

Agent may propose prompt / workflow / agent-policy changes **only as Gitea PRs** (CT103 Contents API + `open_or_find_pr`). Writing those gated paths into a live deploy root (`/opt/ai-sdlc-lab/agent-control-plane`) is **denied** (no in-prod self-edit).

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Classify | Workflows, `.agent/**`, RLM prompts → gated | pass (unit) |
| In-prod deny | Gated write targeting `/opt/.../agent-control-plane` → deny `in_prod_self_edit_denied` | pass `T06_IN_PROD_DENY_OK` |
| Propose PR | `agentctl self-improve propose` opens `agent/self-improve-*` PR | pass PR #31 |
| Non-gated | Propose `README.md` / `src/**` → deny | pass (unit) |
| AgentFacts | `agentctl agentfacts check` after card re-sign | pass |

## Design

1. **Gated globs** (PR-only channel): `.gitea/workflows/**`, `.github/workflows/**`, `.agent/**`, `**/prompts.py` (incl. RLM prompts).
2. **In-prod gate**: `evaluate_in_prod_self_edit` denies gated paths when target is a production deploy root or `.agent-control-plane-live` marker.
3. **Propose**: create `agent/self-improve-*` branch from `main`, Contents API create/update, open PR via existing `open_or_find_pr` (same CT103 write authority as publish-broker).
4. Closed-world `always_denied` for workflows on `/agent fix` remains; this lane is the explicit escape hatch **as PR only**.

## CLI

```bash
agentctl self-improve classify --paths .gitea/workflows/ci.yaml,src/x.py
agentctl self-improve check-in-prod \
  --target /opt/ai-sdlc-lab/agent-control-plane \
  --paths .agent/self_improve/PROPOSALS.md
agentctl self-improve propose --repo ai-sdlc-lab/agent-control-plane --note v5-t06-smoke
```

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T06 |
| Slice doc | `docs/slice-v5-t06-gated-self-improvement.md` |
| Tip SHA (expected) | `7b01adc` |
| Date (UTC) | 2026-07-20 |
| Operator | V5 slice coordinator |

### A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| test (`ci.yaml`) | pass | run #742 |
| deploy (CT103) | pass | run #744 |
| deploy-ct104 | pass | run #743 |

### B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `7b01adc` | yes |
| CT104 (`192.168.4.63`) | `7b01adc` | yes |

### C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | status `degraded` (model_2070 unreachable); redis/state ok |
| Required compose services up | ok | control-plane on tip |
| Unexpected write-token on CT104 | absent | `CT104_NO_WRITE_TOKEN_OK` |

### D. Slice smoke

| Step | Result | Evidence |
|------|--------|----------|
| In-prod self-edit deny | pass | `T06_IN_PROD_DENY_OK` reason=`in_prod_self_edit_denied` |
| Propose PR for gated path | pass | `T06_PROPOSE_PR_OK` PR #31 `agent/self-improve-ba27f1b88df2` |
| Live checkout not mutated | pass | `T06_LIVE_CHECKOUT_CLEAN` probe path absent on `/opt/...` |
| `agentctl agentfacts check` | pass | ok; T06 limitation listed |

### E. Regression floor

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Publish via CT103 only (Contents API / open_or_find_pr) | pass |
| Risk 2 still gated (no self-improve → auto-merge) | pass |

```text
DEPLOY_VERIFY: PASS
tip: 7b01adc
next_slice_unblocked: yes
blocker: none
```
