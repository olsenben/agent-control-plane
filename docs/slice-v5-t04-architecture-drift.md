# Slice V5 T04 — Architecture drift detector

**Status:** In Progress  
**Date:** 2026-07-20  
**Epic ticket:** T04  
**Deps:** T01 Done (`bdbdc99`)  
**ADR:** [0022-architecture-drift-detector.md](adr/0022-architecture-drift-detector.md)

## Goal

Detect drift between ADR-declared constraint edges (`scope.globs` / `scope.symbols` → `adr_constrains_*`) and Orbit graph edges; emit a report listing **missing** and **extra** edges. Fail-soft on CT103 (never block dispatch; default CLI exit 0).

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Missing | ADR declares edge absent from graph → listed in `missing_edges` | pending (unit) |
| Extra | Graph has ADR-kind edge not declared by ADR facts → `extra_edges` | pending (unit) |
| Fail-soft | Missing ADR dir / graph snapshot → `ok=true`, warnings, exit 0 | pending |
| CLI | `agentctl graph drift --repo …` prints report with both lists | pending |
| Strict opt-in | `--strict` exits non-zero when `drift=true` | pending (unit) |
| CT103 smoke | Drift report lists missing/extra; fail-soft | pending |

## Design

1. Compile ADR facts via `compile_adrs`.
2. Build expected edges with `extract_adr_constrain_edges` (same as snapshot indexer).
3. Load actual `adr_constrains_file` / `adr_constrains_symbol` from `GraphStore`.
4. Set-diff fingerprints `(kind, src, dst)` → `missing_edges` / `extra_edges`.
5. Tag report with `risk_tags: [architecture_drift]` when drift present; `fail_soft: true` always.

Non-ADR edge kinds are ignored. Catalog-only `adr_constrains_service` is out of scope for this compare (not produced by ADR front matter alone).

## CLI

```bash
agentctl graph drift --repo ai-sdlc-lab/agent-control-plane
agentctl graph drift --repo owner/name --local-path /path/to/checkout
agentctl graph drift --repo owner/name --adr-dir /path/to/docs/adr
agentctl graph drift --repo owner/name --strict   # opt-in hard fail
```

## Deploy verification

_(fill after CT103 smoke)_
