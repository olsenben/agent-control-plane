# Slice T05 / 8a — Orbit-style code + SDLC/evidence graph edges

**Status:** Done — deploy verified  
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

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T05 |
| Tip SHA | `8a5e5a776936fc95eb78ca2b9a68f39ed032bd4b` (`8a5e5a7`) |
| PR | [#25](https://git.ham-sup-lo.com/ai-sdlc-lab/agent-control-plane/pulls/25) merged to main |
| Verdict | **DEPLOY_VERIFY: PASS** |

| Check | Result |
|-------|--------|
| CT102 Actions for tip | pass (hosts pinned after success) |
| CT103 tip | `8a5e5a7` |
| CT104 tip | `8a5e5a7` |
| `/readyz` | degraded (model_2070 LAN timeout; redis/state ok) — non-blocking for T05 |
| `agentctl graph edges` / `coverage` | pass — provenance fields present; coverage reports `missing_graph_edges` honestly |
| Blast-radius fail-soft | unchanged contract |

Note: live snapshot still shows pre-reindex catalog gaps for some Orbit kinds; T06 preflight should consume those gaps.

## Follow-on

- T06 (8b): preflight consumes coverage / `missing_edges`
- T07 (8c): conditional 2070 recursive context
