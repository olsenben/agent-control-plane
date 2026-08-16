# V10 T00.5 — experimental live 2070 recursive-controller hook (C0/C1)

**Ticket:** V10 T00.5 · **Deps:** T00 (platform baseline freeze) · **Scope:** `agent-control-plane` only

## Goal

Make the already-scaffolded conditional recursive path runnable in two explicit,
telemetry-provable evaluation arms without changing production behavior:

```text
controller_backend = deterministic   # C0 — existing read-only fallback plan
controller_backend = model           # C1 — live configured 2070 controller call
```

Gate G2 requires that C0 is never mislabeled as a 2070 RLM run, and that C1 is
only claimed when a model call actually happened.

## Verified pre-change behavior

`prepare_typed_rlm_dispatch` called `run_conditional_recursive_context` without a
`primary_model`, and no other production caller supplied one. The
`call_primary_model` tool therefore always took its deterministic branch and every
live run ended as `controller_mode=fallback_deterministic`. The V10 epic's
"current-build assumption" is confirmed: the recursive path was scaffolded but had
no live controller client at all.

## What changed

| Area | Change |
|------|--------|
| `config/recursive_context.yaml` | New `controller_backend: deterministic` key. Budgets, tool allowlist, and capability flags unchanged. |
| `agent_control/config.py` | New `RECURSIVE_CONTEXT_CONTROLLER_BACKEND` setting; empty defers to yaml. |
| `agent_control/recursive_context/config.py` | `resolve_controller_backend()` (override → env → yaml → `deterministic`) and `controller_roles()`. |
| `agent_control/recursive_context/model_client.py` | New. Builds a `call_primary_model` implementation routed through `chat_completion_with_failover` and records `ControllerTelemetry`. |
| `agent_control/recursive_context/telemetry.py` | New. Flat G2 telemetry projection for events and CLI output. |
| `agent_control/recursive_context/worker.py` | Resolves the arm, builds the controller only on the true path under C1, records telemetry, fails soft. |
| `agent_shared/models/recursive_context.py` | Additive `controller_*` fields on `recursive_context_result.v1`, all defaulted. |
| `agent_control/session/events.py` | `agent.recursive_context_completed` carries the controller telemetry block. |
| `agent_control/session/prepare_dispatch.py` | Passes the env-selected arm through and emits telemetry. |
| `agent_control/cli.py` | `agentctl rlm inspect|run --controller-backend deterministic|model`. |

## Arm selection

Precedence, highest first:

1. explicit caller/CLI `--controller-backend`
2. `RECURSIVE_CONTEXT_CONTROLLER_BACKEND`
3. `config/recursive_context.yaml: recursive_context.controller_backend`
4. `deterministic`

Any unrecognized value resolves to `deterministic`, so the production arm cannot be
switched on by a typo or a stale environment string.

## Behavior contract

```text
recursive_context_required = false
    -> return skipped recursive_context_result.v1
    -> no controller client is constructed, in either arm

recursive_context_required = true, backend = deterministic
    -> existing allowlisted read-only tool plan
    -> controller_model_invoked = false, controller_mode = fallback_deterministic

recursive_context_required = true, backend = model
    -> same typed read-only tool plan and same CT103 budgets
    -> call_primary_model routed to the `summarizer` gateway role (MODEL_2070_*)
    -> controller_model_invoked = true, controller_mode = model_2070
    -> on any route failure: deterministic summary, controller_model_invoked = false,
       controller_mode = fallback_deterministic, controller_error_class recorded,
       and a valid recursive_context_result.v1 is still produced
```

The C1 prompt carries the focused question and evidence *references* only. No file
contents, secrets, or policy text are sent, and the controller has no authority over
policy, budgets, verification, publication, memory admission, or canonical state.

## Telemetry (gate G2)

`controller_telemetry_payload()` projects these onto the artifact, the
`agent.recursive_context_completed` event, the trajectory `stop` record, and
`agentctl rlm run` output:

`recursive_context_required`, `recursive_context_invoked`, `controller_backend`,
`controller_mode`, `controller_model_invoked`, `controller_role`,
`controller_role_label`, `controller_model_id`, `controller_provider`,
`controller_attempts`, `controller_prompt_tokens`, `controller_completion_tokens`,
`controller_wall_seconds`, `controller_gpu_seconds`,
`controller_data_left_homelab`, `controller_error_class`, `invocation_reasons`,
`stop_reason`.

`controller_gpu_seconds` is populated only when the endpoint reports timing (for
example Ollama `eval_duration`); it is `0.0` otherwise rather than estimated.
Controller token counts are also mirrored into `budget_used.input_tokens` /
`budget_used.output_tokens`.

## Non-goals honored

- Recursion is still conditional; nothing made it always-on.
- No recurrent/SSM controller was added.
- The authority boundary is unchanged: CT103 still owns deterministic preflight,
  `recursive_context_required`, budgets, policy, canonical state, memory admission,
  verification, and publication.
- Default production behavior is byte-identical to the T00 baseline arm.

## Tests

`tests/test_v10_t005_controller_backend.py`:

- yaml default is `deterministic`; override → env → yaml precedence; invalid value falls back.
- `recursive_context_required=false` makes no model call even with the C1 env set.
- C0 on a qualifying task: no gateway call, `controller_model_invoked=false`.
- C1 on the same preflight object: one gateway call at role `summarizer`, model id,
  token counts, and GPU seconds recorded.
- C0 vs C1 on the identical preflight differ only by arm (same question, reasons,
  tool sequence, and budgets).
- C1 route exhaustion fails soft to a schema-valid result with the error class recorded.
- Both arms remain read-only and evidence-citing.
- `prepare_typed_rlm_dispatch` defaults to C0 and honors the C1 env override, with the
  telemetry present on the emitted event.

## Baseline impact

`config/recursive_context.yaml` was re-pinned in `docs/evals/V10_BASELINE.md` from
`d438a2ee…` to `8258dc95…` with an explicit T00.5 platform-freeze amendment note.

## Operating the arms

```bash
# C0 (production default, no env needed)
agentctl rlm run --repo owner/repo --run-id RUN --session-id SESS

# C1 for a single experiment run
agentctl rlm run --repo owner/repo --run-id RUN --session-id SESS --controller-backend model

# C1 for a whole dispatch path (experiment host only)
RECURSIVE_CONTEXT_CONTROLLER_BACKEND=model
```
