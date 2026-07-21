# QA V6 wave 2 — patch bundle

**Date:** 2026-07-21  
**Against tip:** `61a0e7e` (+ wave1 working tree)  
**Unified diff:** [qa-v6-wave2.patch](qa-v6-wave2.patch)

## Purpose

Close residual QA failures F-06–F-12 after wave-1 sign-off harden.

## Included fixes

| Failure | Change |
|---------|--------|
| F-12 | `AgentEvent.ledger_sequence` allocated on append; projection sorts by it |
| F-08 | `GiteaClient._patch` + status-aware `GiteaHttpError`; 404→successor; 429/5xx no sequence advance |
| F-07 | `model_attempt_budget_store.py` durable reserve; `budget_exhausted` control decision; gateway uses reserve when `state_root` set |
| F-06 | `nl_invocation_wire.py` + `jobs/state.py` clarification skip + handoff stub with run_id |
| F-10 | `register_pending_ci` projects `waiting_for_ci` |
| F-11 | `policy_source_sha` on `WorkItemApproval` / binding; evaluate_fix_request equality |
| F-09 | DUR-09 projection rebuild test in `test_qa_v6_wave2.py` |
| F-04 residual | `gitea_client.user_has_repo_permission` fail-closed on API errors |

## Apply / verify

```bash
cd ai-sdlc-lab/agent-control-plane
.venv/bin/ruff check .
.venv/bin/pytest -q tests/test_qa_v6_wave2.py \
  tests/test_v6_t01_trace.py tests/test_v6_t02_comment_projection.py \
  tests/test_v6_t03_observatory.py tests/test_v6_t04_gateway.py \
  tests/test_v6_t05_authorization.py tests/test_v6_t06_injection_shadow.py \
  tests/test_v6_t07_nl_invocation.py tests/test_v6_t08_eval_export.py
```

## Remaining thin gaps

- Full DUR-01–08 upgrade/restart matrix (homelab)
- Comment projection timeout reconcile (GET body hash) — retryable path only
- Full N01–N08 approval pytest matrix with mocked plan store
- Observatory OAuth (shared token is the wave1 gate)
