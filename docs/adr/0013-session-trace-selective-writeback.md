---
id: ADR-0013
title: Selective memory writeback from typed session trace (5.7)
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/memory/session_writeback.py"
    - "src/agent_control/session/lifecycle.py"
    - "src/agent_control/results_ingest.py"
    - "src/agent_shared/models/memory.py"
  symbols:
    - admit_session_trace_memory
    - should_defer_ingest_writeback
    - MemoryRecord
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

Slice 4A writeback admitted review/plan memory at result ingest, before session terminals and verification claims existed. ADR-0012 added machine-recorded verification on the session spine. V4.1.2 DoD requires selective writeback that cites evidence and keeps epistemic status explicit, without conflating with 6E.2 CI-verified fix memory.

# Decision

1. For typed review/plan sessions, defer ingest-time `writeback_from_completed` and admit memory only after successful `session_finished` (post `verification_missing`).
2. Admission is CT103-deterministic: structured result required; verification claim required; stamp `session_id`, `epistemic_status`, `evidence_refs`, `admission_policy_version=session_trace_5.7.0`.
3. Fix/repair memory remains owned by 6E.2 (`ci_verified`); 5.7 does not admit on fix `session_finished`.
4. Emit `agent.memory_admitted` / `agent.memory_rejected` on the project ledger.
5. Legacy non-typed ingest keeps early writeback for compatibility.

# Consequences

- Positive: memory rows for typed sessions always carry verification evidence refs; ordering matches verification invariant; 6E.2 stays separate.
- Negative: operators querying memory immediately after worker complete (before ingest finalize) may see a short gap for typed sessions.
- Follow-up: T03 homelab memory-loop proof; adequacy profiles (T04).

# Related

- [slice-5.7-selective-writeback.md](../slice-5.7-selective-writeback.md)
- ADR-0012 (verification gate), ADR-0010 (typed sessions), ADR-0001 (CI truth)
