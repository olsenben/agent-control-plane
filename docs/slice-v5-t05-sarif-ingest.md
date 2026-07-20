# Slice V5 T05 — SARIF ingest (findings → graph/security nodes)

**Status:** In Progress  
**Date:** 2026-07-20  
**Epic ticket:** T05  
**Deps:** T03 or T04 Done (`5ca8d78`)  
**ADR:** [0024-sarif-security-evidence-ingest.md](adr/0024-sarif-security-evidence-ingest.md)

## Goal

Ingest a sample SARIF document and attach static-analysis findings as Orbit **security/evidence** graph nodes (finding → file, tool_run → finding). Risk 0/1 evidence path only — no Risk 2 gate expansion.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Parse | SARIF 2.x `runs[].results` → normalized findings | pending |
| Attach | Edges `finding_affects_file`, `tool_run_produced_finding`, `tool_run_covers_repo` with `provenance=static_analysis` | pending |
| Ceiling | Report `risk_class_ceiling=1`, `blocks_risk2=false` | pending |
| CLI | `agentctl graph sarif-ingest --repo … --file …` | pending |
| Smoke | Sample SARIF on CT103 attaches evidence nodes | pending |

## Design

1. Parse SARIF JSON (minimal 2.1.0 shape; no Semgrep runtime required).
2. Fingerprint findings via `partialFingerprints` or hash(ruleId|path|line|message).
3. Append evidence edges via `GraphStore.append_edges` (does not wipe snapshot).
4. Tag report with `risk_tags: [security_finding]` when findings present.
5. Explicitly refuse Risk 2 coupling: ingest never blocks/unblocks `/agent fix`.

## CLI

```bash
agentctl graph sarif-ingest \
  --repo ai-sdlc-lab/agent-control-plane \
  --file tests/fixtures/sample_t05.sarif.json
```

## Fixture

`tests/fixtures/sample_t05.sarif.json` — two Semgrep-shaped findings on ACP paths.

## Deploy verification

_(filled after CT103/CT104 smoke)_
