# Slice T05 / 8a — Orbit-style code + SDLC/evidence graph edges

**Status:** Implemented — awaiting deploy-verify merge gate  
**Date:** 2026-07-20  
**Epic ticket:** T05  
**Plan:** V4 Orbit-style graph relationships + impl order item 8a  
**Builds on:** Review MVP graph-lite (`docs/graph-indexer.md`)  
**ADR:** [0015-orbit-graph-provenance.md](adr/0015-orbit-graph-provenance.md)

## Goal

Extend the CT103 graph toward an Orbit-inspired dual graph: code-structure edges plus SDLC/evidence relationships, every edge carrying provenance. Blast-radius stays fail-soft. `agentctl graph` surfaces new edge types and coverage.

## Acceptance (ledger smoke)

| Check | Expected |
|-------|----------|
| `agentctl graph edges` | Lists edges with `provenance` (`catalog` / `static_analysis` / `inferred` / `event` / …) |
| `agentctl graph coverage` | Edge-kind + provenance counts; honest `missing_graph_edges` / coverage gaps |
| `agentctl graph blast-radius` | Still fail-soft on missing snapshot; includes provenance summary |
| Snapshot | Emits Orbit kinds (`adr_constrains_*`, `test_covers_file`, `pipeline_verifies_repo`, `package_depends_on_package`, …) |

## Artifacts

| Artifact | Path |
|----------|------|
| Provenance helpers | `src/agent_control/graph/provenance.py` |
| Coverage / edges export | `src/agent_control/graph/coverage.py` |
| SDLC extractors | `src/agent_control/graph/extractors/sdlc_evidence.py` |
| Package deps | `src/agent_control/graph/extractors/packages.py` |
| Schema + store | `src/agent_control/graph/schema.py`, `store.py` |
| CLI | `agentctl graph edges`, `agentctl graph coverage` |
| Tests | `tests/test_graph_orbit_8a.py` |

## Edge kinds (8a)

**Code (existing + annotated):** `repo_contains_file`, `file_imports_file`, `service_owns_file`, …

**SDLC / evidence (new or Orbit-named):**

- `adr_constrains_file` / `adr_constrains_symbol` / `adr_constrains_service`
- `test_covers_file` (inferred heuristic)
- `pipeline_verifies_repo`
- `package_depends_on_package`
- `run_used_memory` / `run_queried_graph` (event; fail-soft when empty)

Every edge stores: `provenance`, `confidence`, `source_sha`, `extractor_version`, `last_verified_at`.

## Policy

- **Graph required ≠ graph is ground truth.** Coverage gaps are reported; they do not hard-fail blast-radius.
- Blast-radius remains fail-soft when snapshot/edges are missing.
- Event/memory evidence edges are optional; absence is a warning / coverage gap.

## Tests

```bash
.venv/bin/pytest tests/test_graph_orbit_8a.py tests/test_graph_blast_radius.py tests/test_graph_catalog.py tests/test_graph_cli.py -q
```

## Deploy verification

Pending merge of `epic/lane-graph-t05-t07` by deploy-verify owner (no CT103/CT104 tip pin from this lane).

## Follow-on

- T06 (8b): preflight consumes coverage / `missing_edges`
- T07 (8c): conditional 2070 recursive context
