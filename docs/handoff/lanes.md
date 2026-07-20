# Parallel lanes — disjoint scopes

Exception to “one Cursor mutator on `main` tip.” Use **separate git worktrees + branches**. Only the **deploy-verify owner** pins CT103/CT104 tips.

| Lane | Branch | Worktree | Owns | Must not |
|------|--------|----------|------|----------|
| **Graph** | `epic/lane-graph-t05-t07` | `ai-sdlc-lab/agent-control-plane-lane-graph` | T05 → T06 → T07 (serial inside lane) | Touch identity/ack/Gitea comment formatters for invoker; push to `main`; SSH deploy CT103/CT104 |
| **Identity** | `epic/lane-identity-t10` | `ai-sdlc-lab/agent-control-plane-lane-identity` | T10 only | Graph / preflight / 2070 / recursive_context; push to `main`; **any** CT103/CT104 deploy or tip pin |
| **Deploy-verify owner** | — (this boss / parent chat) | `agent-control-plane` on `main` | Merge order; tip pins; `DEPLOY_VERIFY`; ledger Done | Parallel tip races |

Base tip for both lanes: `5908ca0` (T04 signed off).

## Merge + deploy order

```text
1. Graph lane opens PR(s) for T05 (then T06, then T07) — never force-push main.
2. Deploy-verify owner merges graph PR → waits CT102 → pins CT103+CT104 → DEPLOY_VERIFY PASS
   → marks ticket Done → signals graph lane to continue next ticket.
3. Identity lane opens PR for T10 only. Hold merge until graph lane tip for current wave is green
   (at least T05 deploy PASS; prefer after T07 if identity PR lands later).
4. Deploy-verify owner merges identity PR → single tip pin → DEPLOY_VERIFY → T10 Done.
```

Never let identity auto-deploy or race a tip pin while graph is mid-deploy.

## File / concern split (avoid thrash)

| Area | Graph lane | Identity lane |
|------|------------|---------------|
| `src/agent_control/graph/**` | yes | no |
| Preflight / `recursive_context*` / 2070 tools | yes | no |
| Gitea comment ack formatters, session `acting_identity` / `invoked_by` | no | yes |
| `docs/slice-*-8*.md`, T05–T07 slice docs | yes | no |
| `docs/slice-*-t10*` / ack identity docs | no | yes |
| `docs/handoff/boss-ledger.md` | propose only | propose only |
| SSH / docker tip pin | **owner only** | **forbidden** |

## Agent return (each lane)

```text
lane: graph | identity
ticket_id: Txx
branch: epic/…
pr_url: … | pending
stopped_reason: ticket_ready_for_merge | deploy_gate_pending | blocker | context_handoff
blocker: none | <one line>
```
