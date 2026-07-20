---
id: ADR-0015
title: Orbit dual-graph edges carry provenance; blast-radius stays fail-soft
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/graph/**"
    - "docs/slice-8a-orbit-graph.md"
  symbols:
    - GraphStore
    - export_coverage_json
    - EXTRACTOR_VERSION
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

Review MVP graph-lite indexed code/catalog edges without provenance or SDLC/evidence relationships. V4 calls for an Orbit-inspired dual graph where every artifact records `edge_provenance`, coverage, and honest missing edges — without treating graph output as policy authority.

# Decision

1. Extend SQLite graph schema with per-edge `provenance` / `source_sha` / `extractor_version` / `last_verified_at` and per-repo snapshot metadata (migrated in place).
2. Emit Orbit-style SDLC/evidence kinds (`adr_constrains_*`, `test_covers_file`, `pipeline_verifies_repo`, `package_depends_on_package`, optional `run_*` event edges) alongside existing code edges.
3. Expose `agentctl graph edges` and `agentctl graph coverage`; enrich blast-radius JSON with provenance summaries.
4. Keep blast-radius **fail-soft**: missing snapshots or edges populate `missing_graph_edges` / coverage gaps and never hard-fail dispatch.

# Consequences

- Positive: operators and preflight (T06) can see which edge kinds exist and why; graph queries are evidence with provenance.
- Negative: inferred edges (`test_covers_file`) are low-confidence; event edges may be empty until memory/events are populated.
- Follow-up: T06 consumes coverage in deterministic preflight; T11 may expose read-only MCP queries.

# Related

- [slice-8a-orbit-graph.md](../slice-8a-orbit-graph.md)
- [graph-indexer.md](../graph-indexer.md)
