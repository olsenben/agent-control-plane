# Spike 1 decision record: official RLM library (`rlms`)

Date: 2026-06-10  
Status: candidate — keep with constraints  
Scope: read-only `/agent inspect` and `/agent explain` only

## Library

| Field | Value |
|-------|-------|
| PyPI package | `rlms` 0.1.2 |
| Import name | `rlm` (`from rlm import RLM`) |
| Upstream | https://github.com/alexzhang13/rlm |
| License | Check upstream repo before production deploy (MIT expected) |

## Install footprint

| Item | Assessment |
|------|------------|
| Dependencies | Heavy: `openai`, `anthropic`, `google-genai`, `portkey-ai`, `rich`, `pytest` pulled transitively |
| Container impact | Prebuild worker image with `pip install '.[rlm]'`; do not install at runtime |
| Runtime memory | REPL path higher than single-shot chat; cap `max_depth=0`, `max_iterations<=3` for homelab |
| CPU | Moderate during REPL iterations |

## Model compatibility

| Endpoint | Support |
|----------|---------|
| Ollama `/v1` on 3080 | Supported via `RLM(backend='openai', backend_kwargs={base_url, model_name, api_key})` |
| vLLM OpenAI-compatible | Same path |
| CT103 model router | Uses `resolve_role_primary('rlm')` → `MODEL_3080_*` |

When `rlms` is not installed, `OfficialRLMEngine` uses OpenAI-compatible single-shot chat (`rlm/completion.py`) and records a warning in `result.json`.

## Sandbox behavior

| Mode | Spike 1 stance |
|------|----------------|
| `rlms` default `environment='local'` | Uses Python REPL — acceptable only for read-only spike with `max_depth=0` and tight iteration cap |
| Production write/verify | Do not use local REPL; require isolated sandbox backend (Step F) |
| Network | Model endpoint only; no extra outbound calls in single-shot path |

## Logging integration

- Normalized events remain in `session_events.jsonl` (`model_call_started/completed` from `FlowRunner`)
- Engine-specific trace appended to `rlm_trace.jsonl` via `rlm/trace.py`
- Raw `rlms` trajectory metadata appended as separate trace lines when present
- Tool-specific logs do not replace `session_events.jsonl`

## Policy bypass risks

| Risk | Mitigation |
|------|------------|
| REPL executes arbitrary Python | Spike 1: `max_depth=0`, read-only kinds only, no write tools registered |
| Repo secrets in context | Context broker exclusions + redaction before artifacts/comments |
| Direct Gitea calls | Forbidden — engine returns `RLMResult` only |
| Repo selecting backend | Blocked — `execution_strategy` is platform-owned (V1) |

## Resource / ops checklist

- [ ] License verified on worker image build
- [ ] Image size budget recorded after `.[rlm]` install
- [ ] Internet not required at runtime if model endpoint is LAN/Tailscale
- [ ] GPU lane concurrency remains 1 per tier

## Keep / drop recommendation

**Keep as candidate** for read-only inspect/explain with:

1. Platform `execution_strategy` selecting `official_rlm` only when explicitly configured (`MODEL_ROUTING_POLICY=official`)
2. `FakeRLMEngine` remains default Step C gate (`MODEL_ROUTING_POLICY=fake`)
3. `MinimalLocalRLMEngine` remains first-class fallback when official library or endpoints are awkward
4. Prebuilt worker images only — no dynamic install during runs

**Do not adopt** `rlms` local REPL for write/verify flows until isolated sandbox exists.

## Next evaluation (Spike 2+)

- Compare official `rlms` REPL path vs `MinimalLocalRLMEngine` single-shot on 3080/2070 latency and quality
- Measure container size with and without `.[rlm]`
- If REPL overhead is unjustified for read-only, prefer single-shot under `OfficialRLMEngine` or shift default fallback to `MinimalLocalRLMEngine`
