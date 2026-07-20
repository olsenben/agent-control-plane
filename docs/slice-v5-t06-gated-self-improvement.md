# Slice V5 T06 — Gated self-improvement (workflow/prompt proposals as PRs only)

**Status:** In Progress  
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
| In-prod deny | Gated write targeting `/opt/.../agent-control-plane` → deny `in_prod_self_edit_denied` | pending deploy |
| Propose PR | `agentctl self-improve propose` opens `agent/self-improve-*` PR | pending deploy |
| Non-gated | Propose `README.md` / `src/**` → deny | pass (unit) |
| AgentFacts | `agentctl agentfacts check` after card re-sign | pending deploy |

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

## Deploy verification (pending)

Fill after tip pin + CT103/CT104 smoke.
