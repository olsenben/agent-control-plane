# Slice V6 T04 — LiteLLM gateway and bounded completion failover

**Status:** In Progress  
**Date:** 2026-07-21  
**Epic ticket:** T04  
**Deps:** T01 Done  

## Goal

Put a real model gateway path between CT103/CT104 and local/remote endpoints with shared attempt budgets, completion-time failover (not health-probe-only), data-egress policy, and observable route events. Deterministic context fallback stays in CT103 — not LiteLLM model lists.

## Acceptance

| Check | Expected |
|-------|----------|
| Attempt budget | `model_attempt_budget.v1` shared across infra/route/quality |
| Completion failover | Failed chat completion retries permitted fallback under budget |
| Egress | External route requires repo policy + role allowlist |
| CT104 | `MODEL_GATEWAY_BASE_URL` preferred; no external keys when gateway set |
| Events | `agent.model_route_*` / `agent.model_all_routes_failed` |
| Context policy | `deterministic_only` when controller unavailable |
| Chaos | Script proves fallback or visible all-routes-failed |

## Artifacts

| Path | Role |
|------|------|
| `src/agent_control/model_gateway.py` | Completion failover + context policy |
| `src/agent_control/model_egress.py` | Repo/role egress |
| `src/agent_control/model_route_events.py` | Ledger events |
| `src/agent_shared/models/model_attempt_budget.py` | Shared budget |
| `config/litellm.yaml` | Illustrative LiteLLM config |
| `docker-compose.yml` profile `model-gateway` | Optional litellm service |
| `tests/test_v6_t04_gateway.py` | Unit coverage |

## Deploy verification

Filled after DEPLOY_VERIFY gate.
