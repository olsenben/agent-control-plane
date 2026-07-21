# Slice V6 T01 — Trace, provenance, and observation contract

**Status:** Done — deploy verify PASS tip `ae4f5e4` (2026-07-21)  
**Epic ticket:** T01  
**Deps:** —

## Goal

Establish `trace_id`, context provenance labels, `control_decision.v1` ledger events, nonblocking OTel helpers, and `observation_projection.v1` read model from durable ledger artifacts.

## Acceptance

| Check | Expected |
|-------|----------|
| `trace_id` on new sessions | 32-hex W3C-compatible id |
| Provenance on context pack | Each source has `trust_class` |
| Control decisions | `agent.control_decision` in ledger |
| OTel down | Sessions complete; telemetry no-op |
| Projection | Monotonic `sequence`; backward compat without `trace_id` |
| CLI | `agentctl trace show --run-id …` |

## Artifacts

| Artifact | Path |
|----------|------|
| Trace helpers | `src/agent_control/telemetry/` |
| Observation | `src/agent_control/observe/` |
| Models | `src/agent_shared/models/trust.py`, `control_decision.py`, `observation_projection.py` |
| Tests | `tests/test_v6_t01_trace.py` |

## Deploy verification

Filled after DEPLOY_VERIFY gate.
