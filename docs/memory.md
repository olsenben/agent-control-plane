# Project memory (CT103)

Operational guide for trajectory memory. **Canonical schema:** [MEMORY_SCHEMA.md](MEMORY_SCHEMA.md).

## Three layers

```text
Memory  — what happened (this subsystem)
Graph   — what depends on what (graph-indexer.md)
CI      — what is broken (CT102)
```

## Design principles

1. **CT103 owns memory** — CT104 is stateless per run; writeback on ingest.
2. **Selective writeback** — high-signal fields only; full prompt/output in run artifacts linked by `run_id`.
3. **Uncertainty first-class** — rejected/uncertain hypotheses, confidence, staleness.
4. **Risk tags** — every memory record links to governance taxonomy ([THREAT_MODEL.md](THREAT_MODEL.md)).
5. **Memory-as-governance (later)** — block fix if file/failure mode has bad attempt history.

## Retrieval stack

| Layer | Technology |
|-------|------------|
| Audit trail | `agent-state` events + `risk_tags` |
| Trajectory memory | SQLite + FTS5 |
| Structure | Tree-sitter + cross-repo graph |
| Architecture | ADR compiler |

## 2070 memory worker

Memory specialist (RWKV, xLSTM, liquid SSM experiments): compress runs, failure fingerprints, retrieval hints — not primary patch author.

## Write / read paths

See [MEMORY_SCHEMA.md](MEMORY_SCHEMA.md).

## Review MVP acceptance

1. Selective `memory_record.v1` on review ingest
2. Includes blast_radius, risk_tags, rejected/uncertain hypotheses when applicable
3. Second command retrieves prior record
4. No full prompt in SQLite

Runbook: [RUNBOOK_REVIEW_MVP.md](RUNBOOK_REVIEW_MVP.md).
