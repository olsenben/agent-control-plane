# Slice V5 T05 — SARIF ingest (findings → graph/security nodes)

**Status:** Done — deploy verify PASS tip `60f30bb` (2026-07-20)  
**Date:** 2026-07-20  
**Epic ticket:** T05  
**Deps:** T03 or T04 Done (`5ca8d78`)  
**ADR:** [0024-sarif-security-evidence-ingest.md](adr/0024-sarif-security-evidence-ingest.md)

## Goal

Ingest a sample SARIF document and attach static-analysis findings as Orbit **security/evidence** graph nodes (finding → file, tool_run → finding). Risk 0/1 evidence path only — no Risk 2 gate expansion.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Parse | SARIF 2.x `runs[].results` → normalized findings | pass (unit + CT103) |
| Attach | Edges `finding_affects_file`, `tool_run_produced_finding`, `tool_run_covers_repo` with `provenance=static_analysis` | pass |
| Ceiling | Report `risk_class_ceiling=1`, `blocks_risk2=false` | pass |
| CLI | `agentctl graph sarif-ingest --repo … --file …` | pass |
| Smoke | Sample SARIF on CT103 attaches evidence nodes | pass `T05_SARIF_INGEST_OK` / `T05_EVIDENCE_NODES_OK` |

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

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T05 |
| Slice doc | `docs/slice-v5-t05-sarif-ingest.md` |
| Tip SHA (expected) | `60f30bb` |
| Date (UTC) | 2026-07-20 |
| Operator | V5 slice coordinator |

### A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| test (`ci.yaml`) | pass | run #729 |
| deploy (CT103) | pass | run #731 |
| deploy-ct104 | pass | run #730 |

### B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `60f30bb` | yes |
| CT104 (`192.168.4.63`) | `60f30bb` | yes |

### C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | status `degraded` (model_2070 unreachable); redis/state ok |
| Required compose services up | ok | control-plane on tip |
| Unexpected write-token on CT104 | absent | `CT104_NO_WRITE_TOKEN_OK` |

### D. Slice smoke

| Step | Result | Evidence |
|------|--------|----------|
| Sample SARIF ingest | pass | `T05_SARIF_INGEST_OK findings=2 edges=5` |
| Evidence nodes queryable | pass | `T05_EVIDENCE_NODES_OK count=2` `finding_affects_file` / `static_analysis` |
| Risk ceiling | pass | `risk_class_ceiling=1` `blocks_risk2=false` |
| `agentctl agentfacts check` | pass | ok; T05 limitation listed |

### E. Regression floor

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Publish via CT103 `publish-broker` only | pass / N/A (unchanged) |
| Risk 2 still gated (no SARIF→fix coupling) | pass |

```text
DEPLOY_VERIFY: PASS
tip: 60f30bb
next_slice_unblocked: yes
blocker: none
```
