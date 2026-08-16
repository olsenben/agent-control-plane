# Handoff — coordinator-handoff-035

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 035 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T00.5 |
| Tip SHA (ACP) | code complete on top of `2532de7cf5098baa461e49b92e0d338c089cff45`; T00.5 commit SHA assigned at closeout |
| Epic | V10 Maintenance Evaluation & Economic Bake-off |
| `stopped_reason` | `deploy_pending` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-035.md
tickets_done: 1 / 12
next_ticket_id: T00.5 (deploy verification), then T01
blocker: none
stopped_reason: deploy_pending
```

## Slice outcome

- Goal: give the conditional recursive path an explicit, telemetry-provable C0/C1 controller arm without changing production behavior.
- Slice doc path: `docs/slice-v10-t005-recursive-controller.md`
- Deploy verify path / status: not yet run / `PENDING`
- CT103 tip / CT104 tip: unchanged from T00 (`4376ef417e29f14bf05d2fcee89c0ab2739f2ddb`) until this ticket is deployed

Code and tests are complete. T00.5 stays Running until CT103/CT104 deploy verification passes.

### Verified pre-change behavior

No production caller ever passed a `primary_model` into `run_conditional_recursive_context`, so every live recursive run resolved to `controller_mode=fallback_deterministic` with no model client constructed. The epic's stated assumption is confirmed; C1 previously did not exist in any form.

### What was implemented

- `controller_backend: deterministic | model` in `config/recursive_context.yaml`, with `RECURSIVE_CONTEXT_CONTROLLER_BACKEND` and `--controller-backend` overrides. Precedence is CLI → env → yaml → `deterministic`; unrecognized values resolve to `deterministic`.
- `agent_control/recursive_context/model_client.py` routes `call_primary_model` through `chat_completion_with_failover` at the `summarizer` gateway role, which maps to `MODEL_2070_*`.
- Additive `controller_*` telemetry fields on `recursive_context_result.v1`, projected onto the completion event, the trajectory `stop` record, and `agentctl rlm run` output.
- C1 route failures fail soft inside the worker: the run still yields a schema-valid result with `controller_model_invoked=false`, `controller_mode=fallback_deterministic`, and `controller_error_class` recorded. It does not fall into the prepare-dispatch failed-only path.
- `config/recursive_context.yaml` re-pinned in `docs/evals/V10_BASELINE.md` with an explicit T00.5 platform-freeze amendment.

## Evidence pointers (paths / IDs only)

- Slice doc: `docs/slice-v10-t005-recursive-controller.md`
- Baseline amendment: `docs/evals/V10_BASELINE.md`
- Tests: `tests/test_v10_t005_controller_backend.py`, `tests/test_recursive_context_8c.py`
- Implementation: `src/agent_control/recursive_context/{config,model_client,telemetry,worker}.py`, `src/agent_shared/models/recursive_context.py`, `src/agent_control/session/{events,prepare_dispatch}.py`, `src/agent_control/cli.py`
- Config: `config/recursive_context.yaml`, `.env.example`
- Prior handoff: `docs/handoff/coordinator-handoff-034.md`

## Decisions the next coordinator must honor

1. `deterministic` (C0) is the production default arm. C1 is opt-in per run or per experiment host; never enable it globally on CT103/CT104 production paths.
2. Gate G2 evidence is `controller_model_invoked=true` plus a resolved `controller_model_id`. A live 2070 host inventory is not evidence of a controller call, and `fallback_deterministic` must never be reported as a 2070 RLM run.
3. The C1 controller reaches the 2070 through the `summarizer` gateway role. The configured model remains `MODEL_2070_NAME=qwen2.5-coder:3b`; do not silently switch to the installed 7B model.
4. `config/recursive_context.yaml` SHA-256 is now `8258dc951f65aa04b8331293574ce3533fabf33a1798926c49468fad94ecc9c5` (was `d438a2ee…`). Cite the amended value in all later tickets.
5. The C1 prompt carries evidence references only, never file contents or secrets, and the controller retains no authority over policy, budgets, memory admission, verification, or publication.
6. `controller_gpu_seconds` is recorded only when the endpoint reports timing; it is `0.0` rather than estimated, which matters for T03 cost normalization.

## Next coordinator: first actions

1. Push the T00.5 commit. It is committed locally but not pushed, and it also carries the T00 follow-up that fills the final tagged SHA `2532de7cf5098baa461e49b92e0d338c089cff45` in `docs/evals/V10_BASELINE.md`.
2. Run CT103/CT104 deploy verification, confirm the default arm remains `deterministic` in the deployed runtime, then flip T00.5 to Done and record the deployed tip.
3. Prove C1 live once against the deployed 2070 with `--controller-backend model` and archive the resulting `controller_model_id` / token / wall-time telemetry as the G2 exhibit.
4. Begin T01 only after T00.5 is Done.

## Open risks (one line each)

- Live C1 has not yet been exercised against the real 2070 endpoint; only mocked-gateway proof exists so far.
- `MODEL_FALLBACK_ENABLED` plus configured `gpt-4.1` / `gpt-4o-mini` fallbacks mean a C1 arm could reach an external provider if 2070 egress policy is loosened; `controller_data_left_homelab` must be checked on every scored run.
- The shared working tree still holds unrelated pre-existing modifications; the T00.5 commit must be isolated to this ticket's files plus the T00 baseline follow-up.
- CT102 runner/version remains `PENDING_LIVE_CERT` / `DEEPER_EVAL`.
