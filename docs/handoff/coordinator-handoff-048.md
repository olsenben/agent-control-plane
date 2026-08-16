# Handoff — coordinator-handoff-048

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 048 |
| Date (UTC) | 2026-08-16 |
| Slice / wave | V10 Wave C — prove live C1 against the real 2070 |
| ACP tip / deployed SHA | `027ad9f06328f9b55f217b042d14c2fcb2beb25d` (CT103 + CT104) |
| Epic | V10 Maintenance Evaluation & Economic Bake-off |
| Prior handoffs | [046](coordinator-handoff-046.md), [047](coordinator-handoff-047.md) |
| `stopped_reason` | `blocker` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-048.md
wave: C
c1_proof: FAIL
controller_backend: model
controller_model_invoked: false
controller_model_id: qwen2.5-coder:3b (source=planned_not_invoked — NOT an observation)
controller_provider: (none — no route answered)
controller_data_left_homelab: false
contamination: none
evidence_path: docs/evidence/v10-wave-c/
acp_changed: yes
deploy_verify: PASS
scored: no
blocker: the real 2070 host `msi` (100.125.235.54) has been offline since ~12h before this wave; no live C1 observation is obtainable until a human powers it back on
stopped_reason: blocker
```

## Outcome in one paragraph

The live C1 smoke ran against the real configured 2070 endpoint on the deployed
tip and produced an auditable observation — but the observation is that the
2070 is not there. `msi` (`100.125.235.54`, the RTX 2070 host) shows `offline,
last seen 12h ago` in `tailscale status` from both CT103 and CT104, `tailscale
ping` gets no reply, and a LAN sweep of `192.168.4.0/24` finds no other host
serving `:11434`. So `controller_model_invoked` is `false` and H1c stays
unclaimed. What the wave *did* settle is the thing that would have made the
eventual observation worthless: the C1 controller can no longer be answered by
an external provider, and it no longer reports metrics it did not measure. Both
are now proven live on both hosts, not just in tests.

## What the live run actually recorded

`docs/evidence/v10-wave-c/c1-live-smoke-027ad9f.json`, taken inside the CT103
`control-plane` container on the deployed SHA:

| Field | Value | Reading |
|---|---|---|
| `controller_backend` | `model` | the C1 arm ran, not C0 |
| `controller_model_invoked` | `false` | **not a C1 observation** |
| `controller_model_id` | `qwen2.5-coder:3b` | `controller_model_id_source: planned_not_invoked` — the route we would have used, not a served model |
| `controller_provider` | `""` | nothing answered |
| `controller_data_left_homelab` | `false` | enforced, not merely reported |
| `controller_route_class` | `direct_local` | ACP dialled the GPU itself; no proxy in the path |
| `controller_endpoint_base_url` | `http://100.125.235.54:11434` | the real 2070, not a stand-in |
| `controller_local_only_enforced` | `true` | the guard was armed for this run |
| `controller_external_routes_refused` | `0` | no external route was even offered |
| `controller_gpu_seconds` | `null` | not a fake `0.0` |
| `controller_missing_fields` | `["controller_completion_tokens","controller_gpu_seconds","controller_prompt_tokens"]` | honest about what was not measured |
| `controller_error_class` | `ModelRouteExhausted` | after a 135 s connect timeout |
| `candidate_routes` | one entry: `gpu` / `qwen2.5-coder:3b` / `100.125.235.54` | the only route in play was local |
| `endpoint_probe` | `unreachable`, `ConnectTimeout` | independent liveness read, same conclusion |
| `scored` | `false` | no hypothesis claimed |

An earlier attempt on `0951e56` is kept at
`c1-live-smoke-attempt-1.json` and agrees on every field; it predates the
model-id provenance fix.

## Contamination: none, and now structurally impossible

The wave brief was right to be suspicious. The 2070 tier is configured with an
OpenAI fallback on **both** hosts:

```text
MODEL_2070_FALLBACK_BASE_URL = https://api.openai.com/v1
MODEL_2070_FALLBACK_NAME     = gpt-4o-mini
MODEL_2070_FALLBACK_API_KEY  = <set, 164 chars>
MODEL_FALLBACK_ENABLED       = true
```

With the 2070 down, that is exactly the situation where a C1 run silently
becomes a `gpt-4o-mini` run. It did not happen, but only because
`REPO_EXTERNAL_MODEL_POLICY` is empty and `evaluate_external_egress` fails
closed. That is a config coincidence, not a boundary — one allowlist entry would
have flipped it.

The C1 controller is now local-only by construction. `_local_only_complete`
inspects every route the failover chain offers *before* a request is sent and
refuses anything that is not a homelab GPU endpoint (provider `gpu` **and** a
loopback / RFC1918 / `100.64.0.0/10` / `.ts.net` host). The provider label alone
is not trusted.

A live negative control proves it on the hosts that hold the key
(`docs/evidence/v10-wave-c/c1-negative-control-027ad9f.json`): the 2070 primary
is blanked and `REPO_EXTERNAL_MODEL_POLICY=*` so the OpenAI fallback is the only
candidate, with two safety nets (the key blanked in-process, and `httpx.post`
replaced by a tripwire that raises on any non-homelab URL).

| Host | Forced candidate | Result |
|---|---|---|
| `agentcontrol` (CT103) | `fallback` / `gpt-4o-mini` / `api.openai.com` | refused; `external_route_refused`; `external_http_attempts: []` |
| `agentworker` (CT104) | `fallback` / `gpt-4o-mini` / `api.openai.com` | refused; `external_route_refused`; `external_http_attempts: []` |

Zero external HTTP attempts on either host. The CT104 key is still present and
is still open human gate 6, but it can no longer answer a C1 call.

## New finding the next coordinator must not skip

**CT103 and CT104 disagree about what the 2070 is.**

| Host | `MODEL_2070_NAME` | `MODEL_2070_BASE_URL` | `.env` dated |
|---|---|---|---|
| CT103 `agentcontrol` | `qwen2.5-coder:3b` | `http://100.125.235.54:11434` | 2026-08-03 |
| CT104 `agentworker` | `qwen2.5-coder:7b` | `http://100.125.235.54:11434` | 2026-07-21 |

Same endpoint, two different requested models. This surfaced because the CT104
negative control reported `controller_model_id: qwen2.5-coder:7b`. It was not
introduced by this wave and it was not visible before, because nothing had ever
asked either host what it would send.

Consequences:

- "the real 2070 model" is not a single frozen identity today, so a C1 batch
  split across hosts would not be a comparable arm (gate G7).
- Whichever value is correct, the other host's V10 baseline record is wrong.
- This is deliberately **not fixed here**: `MODEL_2070_NAME` is the C1 evaluated
  identity, and the wave brief forbids changing it. It needs a human decision
  and a re-freeze, not a coordinator edit.

## ACP changes (contamination-path + telemetry truth only)

Slice doc: `docs/slice-v10-wave-c-c1-local-only.md`.

| SHA | Change |
|---|---|
| `0951e56` | local-only route guard; `controller_gpu_seconds` nullable; `controller_missing_fields`; `controller_local_only_enforced` / `controller_external_routes_refused` / `controller_route_class` / `controller_endpoint_base_url` |
| `027ad9f` | `chat_completion` also returns `model_reported`; controller prefers it; `controller_model_id_source` |

What did **not** change: `config/recursive_context.yaml` (still
`8258dc95…`, no freeze amendment), the `deterministic` production default, the
controller prompt, the `summarizer` -> `MODEL_2070_*` role, budgets, sampling,
recursion trigger thresholds, tool policy, the read-only authority boundary, and
Qwen patch-author identity. With CT103's current config the routing behaviour is
byte-identical; the guard removes the dependence on `REPO_EXTERNAL_MODEL_POLICY`
rather than changing today's routes.

One earlier claim is corrected: handoff 035 decision 3 said
`controller_model_id` was "read back from the endpoint response rather than
hardcoded". It was not — `chat_completion` returned `endpoint.model or
data.get("model")`, so the configured name always won and a 2070 serving
something else would still have been recorded as `qwen2.5-coder:3b`. That is now
true rather than merely intended, and `controller_model_id_source` says which
case a reader is looking at.

## Evidence

| Path | Contents |
|---|---|
| `docs/evidence/v10-wave-c/c1-live-smoke-027ad9f.json` | live C1 observation on the deployed tip |
| `docs/evidence/v10-wave-c/c1-live-smoke-attempt-1.json` | first attempt on `0951e56`, same conclusion |
| `docs/evidence/v10-wave-c/c1-negative-control-027ad9f.json` | CT103 + CT104 refusal proof, zero external HTTP |
| `docs/evidence/v10-wave-c/2070-availability-20260816.md` | tailnet status, ping, LAN sweep |
| `docs/handoff/deploy-verify-v10-wave-c-20260816.md` | deploy verification |
| `docs/slice-v10-wave-c-c1-local-only.md` | what changed and why |

Repro scripts: `scripts/_v10_wc_c1_live_smoke.py`, `scripts/_v10_wc_c1_live_run.sh`,
`scripts/_v10_wc_negative_control.py`, `scripts/_v10_wc_negative_run.sh`,
`scripts/_v10_wc_health.sh`, `scripts/_v10_wc_model_divergence.sh`.

## Verification performed

- `ruff check .` — `All checks passed!`
- `pytest -q` — 920 passed (8 new Wave C cases in
  `tests/test_v10_t005_controller_backend.py`)
- Deploy verify — `PASS` on `027ad9f`, CT103 + CT104 (see the deploy doc; the
  CT104 credential-floor deviation is Wave A's, carried unchanged)
- Live smoke + live negative control on both hosts
- 0 paid API calls, 0 scored runs, 0 hypotheses claimed

## Next coordinator: first actions

1. **Do not retry the C1 proof until a human confirms `msi` is powered on and
   `tailscale status` shows it active.** Re-running against a dead host just
   costs 135 s per attempt and produces the same artifact.
2. When it is up, re-run `scripts/_v10_wc_c1_live_run.sh <out.json>` unchanged.
   The observation counts as a C1 proof only if all of:
   `controller_model_invoked=true`, `controller_model_id_source=endpoint_reported`,
   `controller_provider=gpu`, `controller_data_left_homelab=false`,
   `controller_route_class=direct_local`, and `controller_external_routes_refused=0`.
   Expect `controller_gpu_seconds: null` — Ollama exposes `eval_duration` on
   `/api/generate` but not on the OpenAI-compatible `/v1/chat/completions` route
   ACP uses, so that metric belongs in `missing_fields`, not in the artifact as a
   number.
3. Resolve the `MODEL_2070_NAME` divergence before any C1 batch is scored.
4. Wave D (scored H1) remains unstarted, per the wave brief.

## Open risks (one line each)

- H1c cannot be claimed while the 2070 host is off; every downstream C1 claim inherits that.
- CT103 says the 2070 serves `qwen2.5-coder:3b`, CT104 says `:7b`; one of them is wrong and no C1 arm is comparable until that is decided.
- The CT104 provider key is still present on all three workers (open human gate 6); Wave C blocks it from C1 but not from anything else.
- `controller_route_class=gateway_indirect` would make `controller_data_left_homelab` unprovable from ACP's side; no gateway is configured today, but a future LiteLLM cutover reopens the boundary question.
- CT102 CI red on unpinned-ruff drift, carried from Wave A, untouched.
