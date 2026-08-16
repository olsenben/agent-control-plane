# Handoff — coordinator-handoff-049

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 049 |
| Date (UTC) | 2026-08-16 |
| Slice / wave | V10 Wave C retry — prove live C1 against the real 2070 |
| ACP deployed SHA | `027ad9f06328f9b55f217b042d14c2fcb2beb25d` (CT103 + CT104; unchanged) |
| ACP docs tip | docs-only seal of this retry (identity freeze + evidence); no runtime change |
| Epic | V10 Maintenance Evaluation & Economic Bake-off |
| Prior handoffs | [048](coordinator-handoff-048.md) (FAIL, 2070 offline) |
| `stopped_reason` | `context_handoff` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-049.md
wave: C
c1_proof: PASS
controller_backend: model
controller_model_invoked: true
controller_model_id: qwen2.5-coder:7b
controller_model_id_source: endpoint_reported
controller_provider: gpu
controller_data_left_homelab: false
frozen_2070_name: qwen2.5-coder:7b
contamination: none
evidence_path: docs/evidence/v10-wave-c/c1-live-smoke-049-qwen7b.json
acp_changed: no
deploy_verify: N/A
scored: no
blocker: none
stopped_reason: context_handoff
```

## Outcome in one paragraph

The 2070 is back, both ACP hosts can reach it, and a non-scored C1 smoke on
the deployed tip produced a live observation: `controller_model_invoked=true`,
the endpoint reported `qwen2.5-coder:7b`, the provider was `gpu`, and no
bytes left the homelab. CT103 was aligned from the T00 name `:3b` to `:7b`
so both hosts request the same model. Handoff 048 and
`c1-live-smoke-027ad9f.json` are left intact as the offline FAIL. Wave D
(scored H1) was not started. H1c remains unclaimed.

## ACP-host liveness (authoritative; not the human localhost curl)

Human resume curled `http://127.0.0.1:11434` on `benol@buttholecentral`.
That host is the **3080** (`100.107.20.28`). The configured C1 URL is `msi`
(`http://100.125.235.54:11434`). Tags from CT103 and CT104 against that URL:

| Endpoint | Models |
|---|---|
| `msi` `100.125.235.54:11434` (C1) | `qwen2.5-coder:7b` only, digest `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`, Q4_K_M, 7.6B |
| `buttholecentral` `100.107.20.28:11434` (3080) | `qwen2.5-coder:14b`, `qwen2.5-coder:7b`, `llama3:latest` — matches the human localhost list |

`msi` is `active` on the tailnet from CT103. CT103 `/readyz` is `ready` and
`model_2070` is `ok`. `:3b` is absent on both endpoints.

Boss freeze stands: C1 identity is `qwen2.5-coder:7b`. Do not select `:14b`.
Do not keep `:3b`.

## Host alignment (env-only)

| Host | Before | After |
|---|---|---|
| CT103 | `MODEL_2070_NAME=qwen2.5-coder:3b` | `qwen2.5-coder:7b` (`.env` edit + recreate `control-plane`, no rebuild) |
| CT104 | `MODEL_2070_NAME=qwen2.5-coder:7b` | unchanged |

Both request `http://100.125.235.54:11434`. ACP source and image SHA
unchanged. `config/recursive_context.yaml` still `8258dc95…`.

## What the live run recorded

Create-only file
`docs/evidence/v10-wave-c/c1-live-smoke-049-qwen7b.json` (does not overwrite
`c1-live-smoke-027ad9f.json`), taken inside the CT103 `control-plane`
container on the deployed SHA after the env alignment:

| Field | Value | Reading |
|---|---|---|
| `controller_backend` | `model` | C1 arm, not C0 |
| `controller_model_invoked` | `true` | **this is a C1 observation** |
| `controller_model_id` | `qwen2.5-coder:7b` | `controller_model_id_source: endpoint_reported` |
| `controller_provider` | `gpu` | local provider |
| `controller_data_left_homelab` | `false` | enforced |
| `controller_route_class` | `direct_local` | ACP dialled the GPU; no proxy |
| `controller_endpoint_base_url` | `http://100.125.235.54:11434` | the real 2070 |
| `controller_local_only_enforced` | `true` | guard armed |
| `controller_external_routes_refused` | `0` | no external route offered |
| `controller_prompt_tokens` / `controller_completion_tokens` | 160 / 110 | endpoint returned usage |
| `controller_gpu_seconds` | `null` | not a fake `0.0`; listed in `missing_fields` |
| `controller_error_class` | `""` | no route failure |
| `controller_mode` | `model_2070` | not deterministic fallback |
| `candidate_routes` | one: `gpu` / `qwen2.5-coder:7b` / `100.125.235.54` | only local route |
| `endpoint_probe` | `reachable`, HTTP 200, models=`["qwen2.5-coder:7b"]` | independent liveness |
| `scored` | `false` | no hypothesis claimed |

Wall time 11.6 s. Not answered by `gpt-4.1`, `gpt-4o-mini`, or any external
fallback.

## Freeze amendment

T00 / T04 recorded `:3b`. That history is kept. The Wave C retry amends the
current frozen C1 identity to `:7b` because `:3b` cannot be served.

- [v10-wave-c-2070-identity-freeze-amendment.md](v10-wave-c-2070-identity-freeze-amendment.md)
- [V10_BASELINE.md](../evals/V10_BASELINE.md) amendment note
- [v10-experiment-freeze.md](v10-experiment-freeze.md) amendment log

No new experiment version: no scored C1 result exists to invalidate. No
change to prompts, recursive trigger, budgets, tool policy, sampling,
verification, or Qwen patch-author identity (`MODEL_3080_NAME=qwen2.5-coder:14b`).

## Contamination: none

One candidate route, local GPU, homelab URL. External fallback remains
configured (`gpt-4o-mini`, key set, `MODEL_FALLBACK_ENABLED=true`) and remains
blocked by the Wave C local-only guard (proven in 048; not re-run this retry).
Zero paid calls.

## Evidence

| Path | Contents |
|---|---|
| `docs/evidence/v10-wave-c/c1-live-smoke-049-qwen7b.json` | live C1 PASS on aligned `:7b` |
| `docs/evidence/v10-wave-c/c1-live-smoke-027ad9f.json` | 048 FAIL — left intact |
| `docs/evidence/v10-wave-c/2070-availability-20260816-retry.md` | ACP-host tags, tailnet, alignment |
| `docs/evidence/v10-wave-c/2070-availability-20260816.md` | 048 offline record — left intact |
| `docs/handoff/v10-wave-c-2070-identity-freeze-amendment.md` | identity freeze |

Repro: `scripts/_v10_wc_retry_probe.sh`, `scripts/_v10_wc_align_2070_name.sh`,
`scripts/_v10_wc_tags_compare.sh`, `scripts/_v10_wc_c1_live_run.sh`.

## Verification performed

- ACP-host `/api/tags` on configured 2070 URL from CT103 and CT104
- CT103 `.env` + container `MODEL_2070_NAME=qwen2.5-coder:7b`; CT104 confirmed
- CT103 `/healthz` ok; `/readyz` `ready`, `model_2070` ok
- Live C1 smoke create-only
- 0 paid API calls, 0 scored runs, 0 hypotheses claimed
- ACP `ruff check .` on the committed surface (docs/scripts only)

`DEPLOY_VERIFY: N/A` — no ACP source or image change. Host env recreate only.

## Next coordinator: first actions

1. Wave D (scored H1) may start only when the boss opens it. This wave did not.
2. Any scored C1 batch must request `qwen2.5-coder:7b` from
   `http://100.125.235.54:11434` on **both** hosts and must repeat the 049
   proof fields (`endpoint_reported`, `gpu`, `data_left_homelab=false`).
3. Do not treat 048's `qwen2.5-coder:3b` / `planned_not_invoked` as a live
   observation.
4. Human gates still open: frontier identity/price (H2), CT104 provider key
   present on all three workers (gate 6).

## Open risks (one line each)

- H1c is proven live but still unclaimed until a scored C1 batch runs.
- The CT104 provider key is still present on all three workers (open human gate 6).
- `controller_gpu_seconds` remains unreported on Ollama `/v1/chat/completions`; keep it `null`.
- CT102 CI red on unpinned-ruff drift, carried from Wave A, untouched.
- A future LiteLLM cutover would make `controller_route_class=gateway_indirect` and reopen the egress question (ADR-0033).
