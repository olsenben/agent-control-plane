# V10 Wave C — C1 controller local-only boundary and timing truth

Scope: the contamination path and the telemetry-truth defects that stood between
a C1 run and an auditable "the real 2070 answered this" claim. The evaluated C1
behaviour is unchanged: same role, same prompt, same budgets, same sampling,
same recursion trigger, same fail-soft semantics.

## Why this was needed

`build_controller_model_fn` calls `chat_completion_with_failover`, which walks a
candidate route list. On CT103 and CT104 the 2070 tier is configured with an
external fallback:

```text
MODEL_2070_BASE_URL          = http://100.125.235.54:11434   (msi, RTX 2070)
MODEL_2070_FALLBACK_BASE_URL = https://api.openai.com/v1
MODEL_2070_FALLBACK_NAME     = gpt-4o-mini
MODEL_2070_FALLBACK_API_KEY  = <set>
MODEL_FALLBACK_ENABLED       = true
```

Whether that fallback is reachable depended entirely on
`REPO_EXTERNAL_MODEL_POLICY`, which is currently empty and therefore fails
closed. That is a config coincidence, not a boundary. One allowlist entry, and a
C1 run with the 2070 down would have been answered by `gpt-4o-mini` — the exact
contamination the V10 C0/C1 comparison cannot survive.

## What changed

### 1. The C1 controller is local-only by construction

`_local_only_complete` wraps the completion call and is passed to the failover
chain as `complete_fn`. Every route the chain offers is checked *before* a
request is sent:

- `provider` must be `gpu`
- the endpoint host must be loopback, RFC1918/link-local, `100.64.0.0/10`
  (tailnet CGNAT), a bare hostname, or a `.ts.net` / `.local` / `.lan` /
  `.internal` name

Anything else raises `ControllerEgressRefused`, which the failover chain records
as a route failure and the worker turns into the existing fail-soft
`fallback_deterministic` result. No request is ever sent to the refused route,
so no prompt reaches an external provider even in bytes.

The provider label alone is not trusted; the host is checked too, so relabelling
an OpenAI endpoint as `gpu` does not get past the guard.

Refusals are counted in `controller_external_routes_refused` and set
`controller_error_class = external_route_refused`.

### 2. Absent endpoint timings are null, never a measured zero

`_gpu_seconds` returned `0.0` when the endpoint reported no timings, which is
indistinguishable from a GPU call that took no time. It now returns `None`, and
`controller_gpu_seconds` is `float | None` with a default of `None`. Every
metric that the endpoint did not report is named in
`controller_missing_fields`. `maintenance-evals` already treats `None` as
missing (`nonnegativeNumberOrNull` in `maintenance_eval_result.v1.json`), so
this flows through to the eval record without a schema change there.

This matters for the 2070: Ollama exposes `eval_duration` on `/api/generate`
but not through the OpenAI-compatible `/v1/chat/completions` route ACP uses, so
a real C1 call is expected to report `controller_gpu_seconds: null` plus
`controller_missing_fields: ["controller_gpu_seconds"]`.

### 3. The boundary that was enforced is recorded

New telemetry on `recursive_context_result.v1`, all additive with defaults:

| Field | Meaning |
|---|---|
| `controller_local_only_enforced` | the guard was installed for this run |
| `controller_external_routes_refused` | how many non-homelab routes were blocked |
| `controller_route_class` | `direct_local` (ACP dials the GPU) or `gateway_indirect` |
| `controller_endpoint_base_url` | the endpoint actually contacted |
| `controller_missing_fields` | metrics the endpoint did not report |

`gateway_indirect` means a proxy sits in front of the GPUs and can egress
without ACP observing it, so `controller_data_left_homelab` is added to
`controller_missing_fields` rather than being asserted as `false`. CT103 has no
gateway configured, so live runs are `direct_local`.

## What did not change

- `config/recursive_context.yaml` is untouched; the T00.5 pin
  `8258dc951f65aa04b8331293574ce3533fabf33a1798926c49468fad94ecc9c5` still
  holds and the platform freeze needs no further amendment.
- The production default is still `controller_backend: deterministic`.
- Prompt, role (`summarizer` -> `MODEL_2070_*`), budgets, sampling, recursion
  trigger thresholds, tool policy, and the read-only authority boundary are
  identical.
- With the current CT103 config the observable behaviour is byte-identical,
  because `REPO_EXTERNAL_MODEL_POLICY` already denied every external route. The
  guard removes the dependence on that env var, it does not change today's
  routing.

## Tests

`tests/test_v10_t005_controller_backend.py` (24 cases, 5 new):

- `test_endpoint_is_homelab_classifies_routes` — tailnet, RFC1918, loopback,
  MagicDNS, compose service name accepted; `api.openai.com` and
  `api.anthropic.com` refused.
- `test_c1_refuses_external_route_and_never_sends_the_request` — reproduces the
  contamination scenario end to end with the *real* gateway: 2070 base URL
  blanked, OpenAI fallback configured with a key, `REPO_EXTERNAL_MODEL_POLICY=*`.
  `chat_completion` is replaced with a function that fails the test if called.
  The run refuses, fails soft, and still returns a citable artifact.
- `test_c1_missing_endpoint_timing_is_null_not_zero`
- `test_c1_records_the_boundary_it_enforced`
- `test_local_only_guard_passes_homelab_and_blocks_external`
