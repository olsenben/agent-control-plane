---
id: ADR-0024
title: SARIF findings attach as graph security evidence without Risk 2 expansion
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/graph/sarif_ingest.py"
    - "src/agent_control/graph/store.py"
    - "docs/slice-v5-t05-sarif-ingest.md"
  symbols:
    - ingest_sarif
    - SARIF_EDGE_KINDS
decision_type: architecture
enforcement: soft
risk_level: low
supersedes: []
superseded_by: []
review_after: 2026-08-20
agent_visibility:
  - review
  - developer
---

# Context

Orbit Phase 3 calls for Semgrep/SARIF → Finding nodes on the evidence graph. V5 T05 needs a bounded ingest path so operators can attach sample SARIF as durable evidence without enabling auto-remediation or changing Risk 2 dispatch.

# Decision

1. Add `ingest_sarif` that maps SARIF `runs[].results` to Orbit edges:
   - `finding_affects_file` (finding → file)
   - `tool_run_produced_finding` (tool_run → finding)
   - `tool_run_covers_repo` (tool_run → repo)
2. Persist via `GraphStore.append_edges` with `provenance=static_analysis`; idempotent re-ingest by content SHA.
3. Expose `agentctl graph sarif-ingest`; report always sets `risk_class_ceiling=1` and `blocks_risk2=false`.
4. Tag findings with `risk_tags: [security_finding]`; do **not** wire into `/agent fix` gates in this slice.

# Consequences

- Positive: security findings become queryable graph evidence alongside ADR/code edges.
- Negative: severity does not yet drive policy; incomplete SARIF dialects may under-extract.
- Follow-up: gated self-improvement (T06) or future security-review lane may consume these nodes.

# Related

- [slice-v5-t05-sarif-ingest.md](../slice-v5-t05-sarif-ingest.md)
- [graph-indexer.md](../graph-indexer.md) Phase 3
- ADR-0015 (Orbit provenance)
