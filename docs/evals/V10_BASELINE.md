# V10 platform baseline

**Status:** `LIVE_CERTIFIED` (trust boundary and deployed runtime; final tagged documentation SHA pending commit)  
**Recorded (UTC):** 2026-08-16  
**Scope:** V10 T00 platform freeze; no agent behavior change

This document records the repository-known and live-certified platform baseline. The final documentation/tag SHA and unknown CT102 runner version remain explicit follow-ups; they do not change the certified trust boundary.

## Identity

| Field | Frozen value |
|-------|--------------|
| `baseline_tag` | `eval-baseline-2026-08` (create after the T00 documentation commit) |
| Live-deployed agent-control-plane Git SHA (CT103 and CT104) | `4376ef417e29f14bf05d2fcee89c0ab2739f2ddb` |
| Observatory contract source pin | `fba0846624fc5dfbdf762b06391d181ef9ce7beb` (V9 completed tip) |
| Final tagged agent-control-plane Git SHA | `PENDING_COMMIT` |
| CT103 `control-plane` image ID | `sha256:f743c713baa1c756dda4adf330e5908ee6fbad92cb47118fdc51945b6763226a` |
| CT103 `publish-broker` image ID | `sha256:99185d42d19e97f30b3d614a147b928a6d00172563b3316a58e73705b475bdcc` |
| CT103 `worker-state` image ID | `sha256:987fe2ba4b5710a6aa07c2b89a5935fd7721e6e7f196a165602b0b93516ec179` |
| CT104 `worker-rlm-root` image ID | `sha256:f5ffb5996abd0a46c50baebb9a64867dacba099c4bdce433db226982141b7b65` |
| CT104 `worker-report` image ID | `sha256:6eb011a7b6a2e80e00c05972860698255b93e2e3a61ba7a93eff97e3c04271f8` |
| CT104 `worker-ci-repair` image ID | `sha256:ec61dbbde7af00fe69fc84d1b8641d8a8c96544db37537401806953f475ace3f` |
| CT102 runner/version | `PENDING_LIVE_CERT` (`DEEPER_EVAL`: inventory before scored evaluation) |
| Date/time of live certification | 2026-08-16 UTC |

## Models and inference runtime

| Field | Frozen value |
|-------|--------------|
| `MODEL_ROUTING_POLICY` | `official` |
| `MODEL_3080_NAME` / Qwen patch-author identifier | `qwen2.5-coder:14b` |
| Qwen quantization | `Q4_K_M` |
| `MODEL_2070_NAME` / configured controller identifier | `qwen2.5-coder:3b` |
| Additional model available on 2070 host | `qwen2.5-coder:7b` (available, not the configured `MODEL_2070_NAME`) |
| Ollama 3080 version | `0.24.0` |
| Ollama 2070 version | `0.24.0` |
| Configured fallbacks | `gpt-4.1` / `gpt-4o-mini` |
| LiteLLM role aliases | `primary-generator` / `ollama-3080-qwen`; `context-controller` / `ollama-2070-controller` |
| LiteLLM config file SHA-256 | `e39938abf73805ca141252d8c663b65b4b545e93533f562aedd81f8534614fd7` |

## Recursive-context budgets

`config/recursive_context.yaml` file SHA-256: `d438a2eea3c907a05cfa4e2c3b06fc4e2809e67d309805cb7ade7bdbf2d70034`.

| Budget | Frozen value |
|--------|--------------|
| Invocation | conditional |
| Controller role | `gpu-2070` |
| Primary model role | `summarizer` |
| Maximum depth / subcalls | 2 / 6 |
| Maximum graph queries / memory records | 20 / 24 |
| Maximum wall time | 180 seconds |
| Maximum prompt tokens per subcall | 8,192 |
| Maximum total input / output tokens | 60,000 / 12,000 |
| Output maximum | 16,000 characters |
| Repository write / network / secret paths | false / false / false |

The CI-grounded recursive Qwen loop remains bounded by `max_plan_iterations=2`, `max_patch_iterations=3`, `max_ci_repair_iterations=3`, `max_selected_evidence_refs=24`, and `max_selected_chars=12000`. Its config file SHA-256 is `b59afc88c38e7a37acd1a47ec2af69bc1c1589e420f12893c561690095c9b7dd`.

## Policy, registry, and verification

| Field | Frozen value |
|-------|--------------|
| Central command-registry hash (`command_registry_hash.v1`) | `9fe074e04811d9eab61f61320be2a1a857dabf5892a2f2ae66a3366224ed75a5` |
| `config/command_registry.yaml` file SHA-256 | `b8bd01f176610d20c52227d3f9de30b38ca7295af4cd8f2236a9a478e396ba06` |
| ACP `tool_policy.v2` effective command-policy hash | `fe698437e6ab94e7d26e9fde5bfc44bf7c88c57d12d7df347f1d251fe9a6e996` |
| `.agent/policies/tools.yaml` file SHA-256 | `777dc0f675293c58c5cebc13bd8578beb406a01089321cbd387e69a8208bf44a` |
| SRT sandbox policy hash | `5de9f107fc05367e849f893c815efd18` |
| Verification profile/version | `adequacy_profiles.v1`; profiles `risk0_read_only`, `risk1_hypothesis`, `risk2_fix_ci` |
| `config/adequacy_profiles.yaml` file SHA-256 | `5bf4c69fadc70419c08fd531028ed06d8e6f7e009972406b3ca889c6b8f37d49` |
| Observatory projection version | `observation_projection.v1` at V9 tip `fba0846624fc5dfbdf762b06391d181ef9ce7beb` |
| Observatory event version | `observe_event.v1` |

The frozen repository hashes above are the T00 policy/config pins. Per-repository effective policy hashes are task inputs and must be recorded per run rather than generalized from this ACP self-policy.

## Trust-boundary freeze

- CT103 is the sole Gitea mutation authority. `GITEA_BOT_TOKEN` is present there as expected, `FIX_REMOTE_PUBLISH_ENABLED=true`, and `publish-broker` independently validates immutable CT104 patch bundles before branch/PR/comment mutation.
- CT104 has no `GITEA_BOT_TOKEN` or `GITEA_AGENT_TOKEN` in `worker-rlm-root`, `worker-report`, or `worker-ci-repair`; production startup fails closed if either is present. Read-only clone/fetch credentials are permitted.
- The CT104 sandbox receives no persistent platform, model, state, or Gitea credentials.
- CT102 supplies independent CI evidence and has no agent-bot/control-plane write token.
- Model hosts provide inference only and do not execute repositories.
- CT103 `/readyz` was `ready`; Redis and state checks were `ok`.

## Known limitations

- The final tagged SHA cannot be known before these documentation changes are committed; create `eval-baseline-2026-08` from that docs-only commit without changing agent behavior.
- CT102 runner/version remains `PENDING_LIVE_CERT` and is a `DEEPER_EVAL` inventory item before scored evaluation.
- The live 2070 configuration is `MODEL_2070_NAME=qwen2.5-coder:3b`, not the previously assumed 7B model. T00.5 must use the configured `MODEL_2070_NAME`; the installed 7B model is not the baseline controller unless a later frozen change explicitly selects it.
- T00 does not prove or change the T00.5 `controller_backend` behavior. The live model inventory is not evidence that a recursive-controller call occurred.
- External model health also reports OpenAI URLs, and configured fallbacks are `gpt-4.1` / `gpt-4o-mini`; evaluation arms must prevent unintended external routing and record any paid fallback use.
- Verification claims remain scoped to machine-recorded evidence and the named adequacy profile; they are not universal correctness claims.
