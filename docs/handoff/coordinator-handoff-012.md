# Coordinator handoff 012 — V6 T04

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 012 |
| Date (UTC) | 2026-07-21 |
| Slice / ticket ID | T04 |
| Tip SHA (ACP) | d5e4e93 |
| Epic | V6 observable sessions |
| `stopped_reason` | context_handoff |

## Compact return

```text
handoff_path: docs/handoff/coordinator-handoff-012.md
tickets_done: 4 / 8
next_ticket_id: T05
blocker: none
stopped_reason: context_handoff
```

## Slice outcome

- Goal completed: completion failover under shared attempt budget, egress policy, model route events, optional LiteLLM compose profile, CT104 gateway-only routing.
- Slice doc: docs/slice-v6-t04-model-gateway.md
- Deploy verify: pass (`V6_T04_SMOKE_OK`)
- CT103/CT104 tip: d5e4e93

## Next coordinator

1. Implement T05 authorization_decision.v1 with separate predicates + pre-publish recheck.
2. Commit trailers Invoked-By / Agent-Run / Agent-Session.
