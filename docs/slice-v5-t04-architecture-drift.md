# Slice V5 T04 — Architecture drift detector

**Status:** Done — deploy smoke PASS tip `a8c5373` (2026-07-20); combined DEPLOY_VERIFY owner = T03 dual-lane  
**Date:** 2026-07-20  
**Epic ticket:** T04  
**Deps:** T01 Done (`bdbdc99`)  
**ADR:** [0022-architecture-drift-detector.md](adr/0022-architecture-drift-detector.md)

## Goal

Detect drift between ADR-declared constraint edges (`scope.globs` / `scope.symbols` → `adr_constrains_*`) and Orbit graph edges; emit a report listing **missing** and **extra** edges. Fail-soft on CT103 (never block dispatch; default CLI exit 0).

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Missing | ADR declares edge absent from graph → listed in `missing_edges` | pass (unit + CT103) |
| Extra | Graph has ADR-kind edge not declared by ADR facts → `extra_edges` | pass (unit) |
| Fail-soft | Missing ADR dir / graph snapshot → `ok=true`, warnings, exit 0 | pass (unit + CT103) |
| CLI | `agentctl graph drift --repo …` prints report with both lists | pass |
| Strict opt-in | `--strict` exits non-zero when `drift=true` | pass (unit) |
| CT103 smoke | Drift report lists missing/extra; fail-soft | pass |

## Design

1. Compile ADR facts via `compile_adrs`.
2. Build expected edges with `extract_adr_constrain_edges` (same as snapshot indexer).
3. Load actual `adr_constrains_file` / `adr_constrains_symbol` from `GraphStore`.
4. Set-diff fingerprints `(kind, src, dst)` → `missing_edges` / `extra_edges`.
5. Tag report with `risk_tags: [architecture_drift]` when drift present; `fail_soft: true` always.

Non-ADR edge kinds are ignored. Catalog-only `adr_constrains_service` edges are out of scope for this compare (not produced by ADR front matter alone).

## CLI

```bash
agentctl graph drift --repo ai-sdlc-lab/agent-control-plane
agentctl graph drift --repo owner/name --local-path /path/to/checkout
agentctl graph drift --repo owner/name --adr-dir /path/to/docs/adr
agentctl graph drift --repo owner/name --strict   # opt-in hard fail
```

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T04 |
| Slice doc | `docs/slice-v5-t04-architecture-drift.md` |
| Tip SHA (expected) | `a8c5373` |
| Date (UTC) | 2026-07-20 |
| Operator | V5 slice coordinator (T04 lane) |
| Combined tip verify owner | T03 (dual-lane) |

### A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| test (`ci.yaml`) | pass | run #717 |
| deploy (CT103) | pass | run #719 |
| deploy-ct104 | pass | run #718 |

### B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `a8c5373` | yes |
| CT104 (`192.168.4.63`) | `a8c5373` | yes |

### C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | status `degraded` (model paths); redis/state ok |
| Required compose services up | ok | control-plane on tip |
| Unexpected write-token on CT104 | N/A | not re-probed this lane (T03 owns combined floor) |

### D. Slice smoke

| Step | Result | Evidence |
|------|--------|----------|
| Seed ADR-only edge → `missing_edges` listed | pass | `T04_DRIFT_REPORT_OK missing=2 extra=0` |
| Absent repo fail-soft exit 0 | pass | `T04_FAIL_SOFT_OK` |
| Report schema `adr_drift_report.v1` | pass | `missing_edges` + `extra_edges` keys |

### E. Regression floor

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Publish via CT103 `publish-broker` only | N/A (unchanged) |
| Risk 2 still gated | N/A (not exercised) |

```text
DEPLOY_VERIFY: PASS (T04 smoke + tip pin; combined dual-lane floor owned by T03)
tip: a8c5373
next_slice_unblocked: yes (T05 after T03 or T04; T03 may still be open)
blocker: none
```
