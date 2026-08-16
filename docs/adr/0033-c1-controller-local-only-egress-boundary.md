---
id: ADR-0033
title: Enforce a local-only egress boundary for the C1 recursive controller
status: proposed
date: 2026-08-16
owners:
  - platform
scope:
  globs:
    - "src/agent_control/recursive_context/**"
    - "src/agent_workers/rlm/completion.py"
    - "src/agent_shared/models/recursive_context.py"
  symbols:
    - endpoint_is_homelab
    - ControllerEgressRefused
decision_type: security
enforcement: hard
risk_level: high
supersedes: []
superseded_by: []
review_after: 2026-11-16
agent_visibility:
  - review
  - developer
---

# Context

ADR-0016 introduced the conditional recursive-context worker; V10 T00.5 added
the `controller_backend` selector so the C1 arm routes `call_primary_model`
through `chat_completion_with_failover` at the `summarizer` role, which maps to
`MODEL_2070_*`.

That failover chain is shared infrastructure. It walks a candidate route list
and, when the local GPU route fails, may reach an external provider. On both
CT103 and CT104 the 2070 tier is configured with an OpenAI fallback
(`gpt-4o-mini`, a live 164-character key) and `MODEL_FALLBACK_ENABLED=true`.
The only thing preventing that route from being used was an empty
`REPO_EXTERNAL_MODEL_POLICY`, which makes `evaluate_external_egress` fail
closed.

That is a configuration coincidence, not a boundary. A single allowlist entry
would have turned a "local 2070" C1 observation into an OpenAI observation. The
V10 C0/C1 comparison cannot survive that, and neither can the homelab trust
boundary (gate G1) or C0/C1 telemetry truth (gate G2). V10 Wave C found the 2070
host offline, which is precisely the condition under which the fallback would
have fired.

The related telemetry could not be trusted either. Absent endpoint timings were
recorded as `0.0`, indistinguishable from a measured zero, and
`controller_model_id` echoed the configured `MODEL_2070_NAME` rather than the
model the endpoint said it served.

# Decision

The C1 recursive controller enforces its own egress boundary rather than
inheriting whatever the shared failover chain permits.

1. `_local_only_complete` is passed to `chat_completion_with_failover` as
   `complete_fn`. It inspects every candidate route *before* a request is sent
   and raises `ControllerEgressRefused` unless the provider is `gpu` **and**
   `endpoint_is_homelab(base_url)` holds — loopback, RFC1918, link-local,
   `100.64.0.0/10` tailnet CGNAT, a bare hostname, or a `.ts.net` / `.local` /
   `.lan` / `.internal` name. The provider label alone is not trusted.
2. A refusal is a route failure, so the existing fail-soft path returns a valid
   `recursive_context_result.v1` with `controller_mode=fallback_deterministic`.
   Refusals are counted in `controller_external_routes_refused` and set
   `controller_error_class=external_route_refused`.
3. `controller_gpu_seconds` is nullable. Metrics the endpoint did not report are
   named in `controller_missing_fields` rather than defaulted to zero.
4. `chat_completion` additionally returns `model_reported`. The controller
   prefers it and records `controller_model_id_source` as `endpoint_reported`,
   `configured`, or `planned_not_invoked`.
5. `controller_route_class` distinguishes `direct_local` from
   `gateway_indirect`. Behind a proxy the trust boundary is not observable from
   ACP, so `controller_data_left_homelab` is reported as missing rather than
   asserted false.

This is deliberately scoped to the C1 controller. Other roles keep the shared
failover semantics; the recursive controller is the one path whose output is
evidence in a local-vs-frontier comparison.

# Consequences

Positive:

- A C1 observation is local by construction, not by configuration. The boundary
  no longer depends on `REPO_EXTERNAL_MODEL_POLICY`, `MODEL_FALLBACK_ENABLED`,
  or which host the run happens to land on.
- Refusal happens before the request is built, so no prompt bytes reach an
  external provider and no paid call can be incurred from this path.
- Downstream evaluation records distinguish "measured zero" from "not reported",
  which `maintenance-evals` already models as `nonnegativeNumberOrNull`.
- Verified live on both CT103 and CT104 with a negative control that forces an
  OpenAI-only candidate list: refused, zero external HTTP attempts.

Negative / accepted trade-offs:

- When the 2070 is down, C1 degrades to deterministic instead of degrading to a
  frontier model. For evaluation that is correct; for a future production use of
  the recursive controller it means less availability, and that path would need
  its own explicit decision.
- The homelab host classification is heuristic. A private-range address is
  assumed to be homelab, which is true for this topology but would not survive a
  VPN into a third-party network.
- `gateway_indirect` is recorded but not blocked. A LiteLLM cutover in front of
  the GPUs would reopen the question of who can egress.

Follow-up:

- `MODEL_2070_NAME` differed between CT103 (`qwen2.5-coder:3b`) and CT104
  (`qwen2.5-coder:7b`) for the same endpoint. Wave C retry (2026-08-16) froze
  both hosts to `qwen2.5-coder:7b` (digest `dae161e2…`) after ACP-host
  `/api/tags` showed `:3b` absent on `msi`. Identity freeze is outside this
  ADR's decision; record:
  [v10-wave-c-2070-identity-freeze-amendment.md](../handoff/v10-wave-c-2070-identity-freeze-amendment.md).
- If the recursive controller is ever fronted by a gateway, decide whether
  `gateway_indirect` should be refused outright rather than flagged.
