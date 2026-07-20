# Slice 5.5a — Deterministic Context Preflight

**Status:** Implemented — pending homelab sign-off  
**Date:** 2026-07-20  
**Umbrella:** [slice-v412-typed-sessions.md](slice-v412-typed-sessions.md) PR-S3  
**Builds on:** [slice-5.4-typed-sessions.md](slice-5.4-typed-sessions.md), [slice-5.4b-session-failure-taxonomy.md](slice-5.4b-session-failure-taxonomy.md)

## Goal

Every typed RLM root session for `/agent review|plan|fix|repair` gets a mandatory CT103 `memory_preflight.v1` at a **frozen** source + policy SHA before enqueue. Optional evidence compilers may degrade; only identity, schema, or durable-persist failures block enqueue. The recursive-context flag is advisory — **no 2070 invoke** in this slice.

## Pipeline (locked)

```text
ResolvedDispatchSubject (frozen SHAs)
  -> AgentSession
  -> MemoryPreflight (durable) + agent.memory_preflight_created
  -> ContextPack (worker prompt path)
  -> ContextPacket (thin handoff) + agent.context_packet_created
  -> complete RLMJob
  -> identity invariant check
  -> enqueue once
```

Coordinator: `prepare_typed_rlm_dispatch` in `session/prepare_dispatch.py`. Call sites supply command inputs only.

## Artifacts

| Artifact | Path |
|----------|------|
| Preflight | `sessions/{session_id}/memory_preflight.json` |
| Packet | `sessions/{session_id}/context_packet.json` |
| Session refs | `AgentSession.memory_preflight` / `.context_packet` (`SessionArtifactRef`) |

`context_packet.v1` is a thin handoff (digests, SHAs, source index). The worker continues to use `context_pack.v1`.

## Degraded vs fatal

| Class | Behavior |
|-------|----------|
| Component failure (memory/graph/ADR/events/CI) | `status=degraded`, dispatch continues |
| Persist / schema / identity mismatch | `agent.memory_preflight_failed` → one session terminal; **no enqueue** |

`recursive_context_required=true` never blocks enqueue in 5.5a.

## Heuristic (count-based only)

Inputs: `prior_memory_count`, `distinct_prior_root_causes`, `missing_graph_edge_count`.  
No pack-budget circularity. Empty `invocation_reasons` when false; `skip_reason=deterministic_preflight_sufficient`.

## CLI

```text
agentctl session show --session-id sess-… --repo owner/repo [--json]
```

Includes `memory_preflight_summary` and `context_packet_summary` when present.

## Tests

`tests/test_memory_preflight.py` — identity, moving branch, degrade, fatal persist, idempotency, event order, review/plan/fix contract, bounds, no-2070.

## Naming

V4 plan “Slice 6E memory lane” ≠ CT102 CI Slice 6E ([slice-6e-ct102-ci-truth-loop.md](slice-6e-ct102-ci-truth-loop.md)).

## Follow-on

- **5.6** — verification evidence gate  
- **5.7** — selective writeback  
- **8c** — conditional 2070 recursive worker (consumes `recursive_context_required`)
