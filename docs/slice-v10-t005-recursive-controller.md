# V10 T00.5 — live 2070 recursive-controller hook and C0/C1 proof

**Ticket:** V10 T00.5 (`C0/C1 controller_backend truth`)
**Gate:** G2 (C0/C1 telemetry truth). Also touches G3 (platform freeze) via a re-pin.
**Status:** code done; CT103/CT104 deploy verification pending.

## Problem

V10's context ablation compares a deterministic controller arm (C0) against a live
2070-model controller arm (C1). Before T00.5 the arms were indistinguishable in
practice: `run_conditional_recursive_context` accepted a `primary_model` callable,
but no production caller ever passed one, so the `call_primary_model` tool always
returned the deterministic stub and every run recorded
`controller_mode="fallback_deterministic"`. There was no way to select an arm, and
no artifact field that could prove whether a controller model had actually run.
Any C0-vs-C1 comparison made on that basis would have compared C0 against C0.

## What changed

### 1. Arm selector with a production-safe default

`config/recursive_context.yaml` gains one additive key, `controller_backend`,
pinned to `deterministic`. Resolution order is caller override, then the
`RECURSIVE_CONTEXT_CONTROLLER_BACKEND` environment variable, then the yaml pin,
implemented in `resolve_controller_backend`. An unrecognised value resolves to
`deterministic` rather than raising, so a typo in an experiment harness can never
silently switch the production arm to a live model.

Selection surfaces:

- environment: `RECURSIVE_CONTEXT_CONTROLLER_BACKEND=model`
- CLI: `agentctl rlm run --controller-backend model` and `agentctl rlm inspect --controller-backend model`
- `prepare_typed_rlm_dispatch` reads `settings.recursive_context_controller_backend` and passes it through; empty means "defer to yaml".

### 2. Live controller client

`recursive_context/model_client.py` builds the `call_primary_model` implementation
for the C1 arm on top of `chat_completion_with_failover`, using the gateway role
from `primary_model_role` (`summarizer`, which maps to the `MODEL_2070_*`
endpoint) with `controller_role: gpu-2070` retained as the policy label. The live
model identifier is not hardcoded; it is read back from the endpoint response and
recorded as `controller_model_id` (currently `qwen2.5-coder:3b` per the frozen
baseline).

The controller stays inside the existing authority boundary. Its system prompt
grants it no authority over policy, budgets, credentials, verification,
publication, or repository state, and its user prompt carries the focused question
plus evidence *references* only — never file contents or secrets. The read-only
tool belt, the deterministic tool plan, and the budget ceilings are unchanged, so
C1 differs from C0 in exactly one respect: whether the `call_primary_model` step
reaches the 2070 controller.

### 3. Fail-soft inside the worker

Any exception from the gateway, an empty completion, or an exhausted input-token
budget degrades to the deterministic summary inside the worker. The run still
produces a valid `recursive_context_result.v1` with
`controller_mode="fallback_deterministic"`, `controller_model_invoked=false`, and
`controller_error_class` naming the failure. It does not escape into
`prepare_dispatch`'s failed-only path, so a cold or unreachable 2070 host degrades
the arm rather than losing the artifact.

### 4. Telemetry that can settle the C0/C1 question

`RecursiveContextResult` gains additive, defaulted fields:
`controller_backend`, `controller_model_invoked`, `controller_role`,
`controller_role_label`, `controller_model_id`, `controller_provider`,
`controller_attempts`, `controller_prompt_tokens`, `controller_completion_tokens`,
`controller_wall_seconds`, `controller_gpu_seconds`,
`controller_data_left_homelab`, and `controller_error_class`. Token counts also
flow into `budget_used.input_tokens` / `output_tokens`. GPU time is taken from the
endpoint's own timings (Ollama reports `eval_duration` in nanoseconds) and stays
`0.0` when the endpoint does not report it.

`controller_telemetry_payload` projects the gate-G2 fields
(`recursive_context_required`, `recursive_context_invoked`, `controller_backend`,
`controller_model_invoked`, `controller_role`, `controller_model_id`,
`invocation_reasons`, tokens, wall/GPU seconds, `stop_reason`) onto the
`agent.recursive_context_completed` event and the `rlm run` CLI output.

Every new field is optional with a default, so artifacts written before this
slice still validate. Stored results are reused rather than recomputed when a
session already has one, so the added fields cannot raise
`ArtifactConflictError` on an existing session.

### 5. Platform-freeze amendment

Adding the yaml key changed the file SHA, so `docs/evals/V10_BASELINE.md` re-pins
`config/recursive_context.yaml` to
`8258dc951f65aa04b8331293574ce3533fabf33a1798926c49468fad94ecc9c5` and records the
amendment against the T00 pin. No budget, allowlist, or capability value changed.

## What did not change

Recursion is still conditional, not always-on: `recursive_context_required=false`
returns the skip result before any client is constructed, in both arms. No
state-space or recurrent model was introduced. The authority boundary, the tool
allowlist, and `allow_repo_write` / `allow_network` / `allow_secret_paths=false`
are untouched. With no override present, production selects C0 and behaves exactly
as it did before this slice.

## Proof (`tests/test_v10_t005_controller_backend.py`)

| Claim | Test |
|-------|------|
| yaml default is `deterministic` | `test_yaml_default_is_deterministic` |
| override beats env beats yaml; bad value falls back | `test_backend_precedence_override_then_env_then_yaml` |
| `required=false` makes no model call even under C1 | `test_required_false_makes_no_model_call_even_under_c1` |
| C0 never invokes the controller model | `test_c0_arm_never_invokes_controller_model` |
| C1 invokes the configured 2070 role and records id/tokens/GPU time | `test_c1_arm_invokes_configured_2070_controller` |
| prompt carries evidence references only | `test_c1_prompt_carries_only_evidence_references` |
| same qualifying task, arms differ only by backend | `test_c0_and_c1_differ_only_by_backend` |
| C1 model failure fails soft to a valid artifact | `test_c1_model_failure_fails_soft_to_valid_result` |
| both arms stay read-only | `test_controller_stays_read_only_in_both_arms` |
| gate-G2 payload exposes the required fields | `test_telemetry_payload_exposes_gate_g2_fields` |
| dispatch defaults to C0 and emits telemetry | `test_prepare_dispatch_defaults_to_c0_and_records_telemetry` |
| dispatch honours the C1 env override | `test_prepare_dispatch_honours_c1_env_override` |

`test_c0_and_c1_differ_only_by_backend` is the load-bearing one: it feeds a single
`MemoryPreflight` to both arms and asserts identical question, invocation reasons,
subcall sequence, and budgets, with `(deterministic, False)` versus
`(model, True)` as the only difference.

Suite: 902 passed. `ruff check .` exits 0.

## Follow-ups

- Deploy-verify on CT103/CT104 and capture a live C1 run against the real 2070
  endpoint, recording the resolved `controller_model_id` and non-zero GPU seconds.
  Until that evidence exists, C1 is proven only against a mocked gateway.
- T05 must record the arm per run and must not mix arms within a block.
