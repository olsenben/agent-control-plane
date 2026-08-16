# Deploy verification — V10 Wave C (C1 local-only boundary)

| Field | Value |
|---|---|
| Date (UTC) | 2026-08-16 |
| Deployed tip | `027ad9f06328f9b55f217b042d14c2fcb2beb25d` |
| Previous deployed tip | `657a445d38e0b2a32970c7b6169e598883b33d06` (Wave A) |
| CT103 tip | `027ad9f06328f9b55f217b042d14c2fcb2beb25d` |
| CT104 tip | `027ad9f06328f9b55f217b042d14c2fcb2beb25d` |
| Status | **PASS** (one carried pre-existing deviation, unchanged from Wave A) |
| Scored | no |
| Paid calls | 0 |

## What was deployed

Two commits, both confined to the C1 controller's trust boundary and telemetry:

| SHA | Change |
|---|---|
| `0951e56` | C1 controller is local-only by construction; absent endpoint timings are `null`, not `0.0` |
| `027ad9f` | `controller_model_id` prefers what the endpoint reports and records its provenance |

`config/recursive_context.yaml` is untouched — CT103 still hashes to
`8258dc951f65aa04b8331293574ce3533fabf33a1798926c49468fad94ecc9c5`, the T00.5
pin. No freeze amendment was needed.

## Checks

| Check | Result | Evidence |
|---|---|---|
| CT103 tip matches intended SHA | pass | `CT103_TIP=027ad9f…` |
| CT104 tip matches intended SHA | pass | `CT104_TIP=027ad9f…` |
| `config/recursive_context.yaml` hash | unchanged | `8258dc95…` |
| `docker-compose.yml` hash | unchanged | `021d8b9d…` |
| CT103 services | running | `control-plane`, `publish-broker`, `redis`, `worker-state` |
| CT104 workers | running | `worker-ci-repair`, `worker-report`, `worker-rlm-root` |
| CT103 `/healthz` | `{"status":"ok"}` HTTP 200 | — |
| CT103 `/readyz` | `degraded`, HTTP 200 — same class as Wave A | degradation cause is the unreachable 2070, tracked below |
| `agentctl eval dispatch` still works | pass | `V10_WAVE_A_EVAL_DISPATCH_OK`, `agent_execution=True`, fake engine |
| Wave C symbols live in CT103 container | pass | `controller_gpu_seconds` default `None`; `controller_local_only_enforced` and `controller_model_id_source` present; `model_reported` in `chat_completion` |
| Wave C symbols live in a CT104 worker | pass | `endpoint_is_homelab` accepts `100.125.235.54`, refuses `api.openai.com` |
| Guard classification on tailnet CGNAT | pass | `endpoint_is_homelab('http://100.125.235.54:11434') == True` |
| Guard classification on OpenAI | pass | `endpoint_is_homelab('https://api.openai.com/v1') == False` |
| Live negative control, CT103 | pass | forced OpenAI-only candidate refused, 0 external HTTP attempts |
| Live negative control, CT104 worker | pass | forced OpenAI-only candidate refused, 0 external HTTP attempts |
| Gates + lint on the committed surface | pass | 920 tests, `ruff check .` clean |

## Carried deviation (pre-existing, not introduced by Wave C)

The deploy-verify script's CT104 credential floor still exits non-zero:

```text
FAIL_CREDENTIAL /agent-control-plane-worker-ci-repair-1
MODEL_2070_EXTERNAL_API_KEY=<set:164chars>
MODEL_3080_EXTERNAL_API_KEY=<set:164chars>
```

All three CT104 workers carry the same 164-character provider key. This is
byte-identical to the deviation Wave A recorded in
[deploy-verify-v10-wave-a-eval-dispatch-20260816.md](deploy-verify-v10-wave-a-eval-dispatch-20260816.md);
CT104's `.env` is dated 2026-07-21 and was not touched by this wave. Wave C makes
that key unusable by the C1 controller — the live negative control on CT104
proves it — but the key itself is still present and is still open human gate 6.

## Overall

`DEPLOY_VERIFY: PASS` for `027ad9f`, with the CT104 credential-floor deviation
carried forward unchanged.
