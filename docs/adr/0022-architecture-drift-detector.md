---
id: ADR-0022
title: Architecture drift detector compares ADR facts to graph edges fail-soft
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/graph/adr_drift.py"
    - "docs/slice-v5-t04-architecture-drift.md"
  symbols:
    - detect_adr_drift
    - ADR_DRIFT_EDGE_KINDS
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

Orbit graph edges (`adr_constrains_*`) are derived from ADR scope at snapshot time, but ADR edits and stale graphs can diverge silently. V5 T04 needs an operator-visible drift report without treating graph output as policy authority or blocking CT103 dispatch.

# Decision

1. Add `detect_adr_drift` that diffs ADR-compiled expected constraint edges against graph-store `adr_constrains_file` / `adr_constrains_symbol` edges.
2. Expose `agentctl graph drift` reporting `missing_edges` and `extra_edges`; default exit 0 (fail-soft). Optional `--strict` for CI gates.
3. Tag drift reports with `risk_tags: [architecture_drift]`; never raise into fix/review dispatch paths.

# Consequences

- Positive: operators can see ADR↔graph divergence; threat model tag is actionable.
- Negative: glob patterns and catalog `adr_constrains_service` edges are not fully covered by this compare.
- Follow-up: SARIF / gated self-improvement may consume drift reports later.

# Related

- [slice-v5-t04-architecture-drift.md](../slice-v5-t04-architecture-drift.md)
- ADR-0015 (Orbit provenance; blast-radius fail-soft)
