---
id: ADR-0011
title: Deterministic CT103 context preflight before RLM enqueue
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/memory/preflight*.py"
    - "src/agent_control/session/prepare_dispatch.py"
    - "src/agent_shared/models/memory_preflight.py"
    - "src/agent_control/workflows/dispatch.py"
    - "src/agent_control/approval/dispatch_fix.py"
  symbols:
    - prepare_typed_rlm_dispatch
    - MemoryPreflight
    - ContextPacket
decision_type: architecture
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-08-20
agent_visibility:
  - review
  - developer
---

# Context

Typed sessions (ADR-0010) give CT103 a durable spine, but context for review/plan/fix/repair was assembled only as an ephemeral `context_pack.v1` without an auditable preflight decision, frozen SHA identity across artifacts, or a clear degrade path when optional evidence sources fail. V4.1.2 requires Stage A deterministic preflight before any optional 2070 recursive exploration.

# Decision

1. Every typed RLM root session (`review|plan|fix|repair`) runs CT103 `prepare_typed_rlm_dispatch` before enqueue.
2. Source SHA and `policy_source_sha` are frozen once on the job/session and must match across session, `memory_preflight.v1`, `context_pack.v1`, `context_packet.v1`, and the enqueued job.
3. Optional compilers (memory, graph, ADR, events, CI evidence) may degrade into a valid preflight; only schema, identity, or durable-persist failures prevent enqueue (`agent.memory_preflight_failed` then one session terminal).
4. `recursive_context_required` is advisory and never invokes or blocks on the 2070 controller in Slice 5.5a.
5. `context_packet.v1` is a thin digest/ref handoff; the worker prompt path continues to use `context_pack.v1`.

# Consequences

- Positive: auditable preflight on the session spine; identity invariant; idempotent artifacts; shared coordinator for review/plan/fix/repair.
- Negative: dispatch latency grows with evidence scans; repair path gets preflight without a full pack.
- Follow-up: 5.6 verification gate; 5.7 selective writeback; 8c conditional 2070 worker consuming `recursive_context_required`.
