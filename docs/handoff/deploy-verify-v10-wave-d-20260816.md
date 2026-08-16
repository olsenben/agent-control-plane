# Deploy verification — V10 Wave D (2026-08-16)

## Identity

| Field | Value |
|-------|-------|
| Ticket ID | Wave D — scored H1 DEV A/B/C0/C1 |
| Slice doc | [boss-ledger-v10.md](boss-ledger-v10.md) |
| Runtime SHA | `9447c1c39948f9d41e58f28dd0fb65870e005d1f` (arm-aware eval-dispatch) |
| Tip SHA (pinned) | `c5ccafe4757afec26e9ff3c11498124ba4d196b7` (ADR-0034 on top of runtime) |
| Date (UTC) | 2026-08-16 |
| Operator | Wave D coordinator |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` green for tip | N/A | Local pytest + ruff on the Wave D surface; CT102 ruff drift is a carried finding |
| `deploy` (CT103) | N/A | Manual pin via WSL deploy key (same as Waves A–C) |
| `deploy-ct104` | N/A | Manual pin via WSL deploy key |

## B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `c5ccafe4757afec26e9ff3c11498124ba4d196b7` | yes |
| CT104 (`192.168.4.63`) | `c5ccafe4757afec26e9ff3c11498124ba4d196b7` | yes |

`config/recursive_context.yaml` still `8258dc95…`.

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/healthz` | ok | `{"status":"ok"}` 200 |
| CT103 `/readyz` | degraded | hangs on `model_2070` probe; `msi` `100.125.235.54` tailnet `offline` |
| Redis + compose | ok | redis healthy; control-plane, publish-broker, worker-state running |
| CT104 Gitea write tokens | absent | pre-existing external model API key still present; not treated as a new fail |

## D. Slice smoke

| Step | Result | Evidence |
|------|--------|----------|
| Fake-engine A vs B arm wiring | pass | A `retrieved=[]`; B `retrieved=['calc.py']` |
| Sessions | pass | `sess-eval-d73647946ea046838d948a62f38bd0a6`, `sess-eval-93b82e4308bb4c88bc7224dc11af77a2` |

## E. Regression floor

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Publish still via CT103 `publish-broker` only | pass |
| C1 still refuses external controller identities | pass (unit + ADR-0033/0034) |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: c5ccafe4757afec26e9ff3c11498124ba4d196b7
runtime: 9447c1c39948f9d41e58f28dd0fb65870e005d1f
next_slice_unblocked: yes
blocker: none
readyz_note: model_2070 probe times out while msi is offline; healthz/redis/state ok
```
