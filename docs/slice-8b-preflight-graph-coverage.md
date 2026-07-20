# Slice T06 / 8b — Preflight consumes graph coverage / missing_edges

**Status:** Implemented — awaiting deploy-verify merge gate  
**Date:** 2026-07-20  
**Epic ticket:** T06  
**Plan:** V4 impl order item 8b  
**Builds on:** [slice-5.5-deterministic-preflight.md](slice-5.5-deterministic-preflight.md), [slice-8a-orbit-graph.md](slice-8a-orbit-graph.md)

## Goal

Deterministic CT103 `memory_preflight.v1` includes Orbit graph coverage (edge kinds, provenance, index freshness) and merges coverage / blast `missing_graph_edges` into the recursive-context heuristic.

## Acceptance (ledger smoke)

| Check | Expected |
|-------|----------|
| Preflight JSON `graph_coverage` | Includes `edge_kinds`, `provenance_counts`, `files_indexed`, `edge_count`, `extractor_version` |
| Preflight JSON `missing_graph_edges` | Union of blast-radius gaps + Orbit coverage gaps |
| `heuristic_inputs.missing_graph_edge_count` | Equals `len(missing_graph_edges)` |
| Threshold | `>= THRESHOLD_MISSING_GRAPH_EDGES` → `graph_coverage_insufficient` in `invocation_reasons` |
| Fail-soft | Coverage export failure degrades, does not abort preflight |

## Artifacts

| Artifact | Path |
|----------|------|
| Compiler | `src/agent_control/memory/preflight.py` |
| Model | `src/agent_shared/models/memory_preflight.py` (`COMPILER_VERSION=…/8b`) |
| Coverage source | `src/agent_control/graph/coverage.py` (`export_coverage_json`) |
| Tests | `tests/test_preflight_graph_coverage_8b.py` |

## Behavior

```text
blast_radius missing_edges
  ∪ export_coverage_json().missing_graph_edges
  → preflight.missing_graph_edges
  → heuristic.missing_graph_edge_count
  → decide_recursive_context (advisory; 2070 still 8c)
```

`graph_queries` gains a `coverage` entry alongside `blast_radius`. Citations include `graph:coverage`.

## Tests

```bash
.venv/bin/pytest tests/test_preflight_graph_coverage_8b.py tests/test_memory_preflight.py -q
```

## Deploy verification

Pending merge of `epic/lane-graph-t05-t07` by deploy-verify owner (no CT103/CT104 tip pin from this lane).

## Follow-on

- T07 (8c): conditional 2070 recursive context worker consumes `recursive_context_required`
