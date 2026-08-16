# Handoff — coordinator-handoff-035

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 035 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T00.5 |
| Tip SHA (ACP) | Baseline `2532de7cf5098baa461e49b92e0d338c089cff45` (`eval-baseline-2026-08`); T00.5 commit pending |
| Epic | V10 Maintenance Evaluation & Economic Bake-off |
| `stopped_reason` | `ticket_code_complete_deploy_pending` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-035.md
ticket: T00.5
status: code done (deploy pending)
tests: 902 passed
ruff: All checks passed!
blocker: none
next_ticket_id: T01 (after T00.5 deploy verification)
stopped_reason: ticket_code_complete_deploy_pending
```

## Slice outcome

- Goal completed (code): the recursive-context worker can now actually reach the
  live 2070 controller, and every run records which arm executed.
- Slice doc path: `docs/slice-v10-t005-recursive-controller.md`
- Deploy verify path / status: not yet run / `pending`
- CT103 tip / CT104 tip: unchanged from T00 (`4376ef4` deployed); T00.5 not deployed

Before this slice the C0 and C1 arms were the same arm. No production caller ever
supplied a `primary_model`, so `call_primary_model` always returned the
deterministic stub and every result recorded `fallback_deterministic`. A C0-vs-C1
comparison run on that code would have compared C0 against itself.

T00.5 adds a `controller_backend` selector (`deterministic` | `model`), a live
controller client over `chat_completion_with_failover` at the `summarizer` role
that maps to `MODEL_2070_*`, and the telemetry needed to prove which arm ran.

## Decisions the next coordinator must honor

1. **The production default is unchanged.** `config/recursive_context.yaml` pins
   `controller_backend: deterministic`. Resolution order is caller override, then
   `RECURSIVE_CONTEXT_CONTROLLER_BACKEND`, then the yaml pin; an unrecognised
   value resolves to `deterministic` rather than raising, so no typo can switch
   production onto a live model. Do not flip the yaml pin to select C1 — use the
   env variable or `--controller-backend` per run.
2. **The platform freeze was amended, not broken.** The yaml change re-pinned
   `config/recursive_context.yaml` to
   `8258dc951f65aa04b8331293574ce3533fabf33a1798926c49468fad94ecc9c5` in
   `docs/evals/V10_BASELINE.md`, superseding the T00 pin
   `d438a2eea3c907a05cfa4e2c3b06fc4e2809e67d309805cb7ade7bdbf2d70034`. One
   additive key; no budget, allowlist, or capability value changed. Later tickets
   must cite the amended SHA.
3. **Only telemetry proves an arm, never inventory.** A run counts as C1 only when
   `controller_model_invoked=true` with a resolved `controller_model_id`. The
   presence of a model on the 2070 host is not evidence. `controller_model_id` is
   read back from the endpoint response rather than hardcoded, so if the host is
   serving something other than `qwen2.5-coder:3b` the artifact will say so.
4. **C1 failures degrade the arm, not the artifact.** Gateway exceptions, empty
   completions, and input-token exhaustion fail soft inside the worker to
   `controller_mode="fallback_deterministic"` with
   `controller_model_invoked=false` and `controller_error_class` set. A run that
   fails soft is not a C1 observation and must not be scored as one.
5. **Recursion stays conditional.** `recursive_context_required=false` returns the
   skip result before any client is constructed, in both arms. Do not make
   recursion always-on to increase C1 sample size; change the preflight thresholds
   deliberately and re-freeze if that is ever needed.
6. **The authority boundary is untouched.** The controller receives the question
   plus evidence references only, never file contents or secrets, and has no
   authority over policy, budgets, credentials, verification, or publication.
   `allow_repo_write` / `allow_network` / `allow_secret_paths` remain false in both
   arms.
7. **Watch for paid fallback contamination.** `chat_completion_with_failover` can
   fail over past the local GPU routes. C1 runs must record
   `controller_provider` and `controller_data_left_homelab`; any run where the
   controller was answered by an external provider is not a local-2070
   observation.

## Evidence pointers (paths / IDs only)

- Slice doc: `docs/slice-v10-t005-recursive-controller.md`
- Baseline amendment: `docs/evals/V10_BASELINE.md` (Recursive-context budgets)
- Tests: `tests/test_v10_t005_controller_backend.py` (12 T00.5 cases)
- Controller client: `src/agent_control/recursive_context/model_client.py`
- Arm resolution: `src/agent_control/recursive_context/config.py` (`resolve_controller_backend`)
- Telemetry projection: `src/agent_control/recursive_context/telemetry.py`
- Worker wiring: `src/agent_control/recursive_context/worker.py`
- Artifact schema: `src/agent_shared/models/recursive_context.py`
- Dispatch/event/CLI surfaces: `src/agent_control/session/prepare_dispatch.py`, `src/agent_control/session/events.py`, `src/agent_control/cli.py`
- Prior handoff: `docs/handoff/coordinator-handoff-034.md`
- ADR candidates: none new; ADR-0016 (conditional recursive-context worker) remains the governing decision and is extended, not replaced

## Verification performed

- `ruff check .` — `All checks passed!`
- `pytest -q` — 902 passed
- Targeted: `tests/test_v10_t005_controller_backend.py` + `tests/test_recursive_context_8c.py` — 19 passed

The C0/C1 separation is proven against a mocked gateway, not a live endpoint.
`test_c0_and_c1_differ_only_by_backend` feeds a single `MemoryPreflight` to both
arms and asserts identical question, invocation reasons, subcall sequence, and
budgets, leaving the backend and `controller_model_invoked` as the only
difference.

## Next coordinator: first actions

1. Commit the T00.5 code + docs, then deploy-verify CT103/CT104 and record the
   result as `docs/handoff/deploy-verify-v10-t005-<date>.md`.
2. Capture one live C1 run against the real 2070 endpoint
   (`RECURSIVE_CONTEXT_CONTROLLER_BACKEND=model`, or
   `agentctl rlm run --controller-backend model`) and record the resolved
   `controller_model_id`, token counts, and non-zero `controller_gpu_seconds`.
   Until that exists, C1 is proven only in test.
3. Flip T00.5 to Done only after both of the above, then begin T01.

## Open risks (one line each)

- C1 is proven against a mocked gateway; the live 2070 path is unexercised until deploy verification.
- `controller_gpu_seconds` depends on the endpoint reporting `eval_duration`; a gateway that strips timings will report `0.0` without that being an error.
- Failover can reach external providers, so C1 runs need `controller_provider` checked before being scored as local.
- The shared working tree still carries unrelated pre-existing changes; isolate the T00.5 file set when committing.
- CT102 runner/version remains `PENDING_LIVE_CERT` / `DEEPER_EVAL` from T00.
