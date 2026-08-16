# Handoff — coordinator-handoff-050

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 050 |
| Date (UTC) | 2026-08-16 |
| Slice / wave | V10 Wave D — scored H1 DEV A/B/C0/C1 |
| ACP deployed SHA | `c5ccafe4757afec26e9ff3c11498124ba4d196b7` (runtime `9447c1c`; ADR-0034) |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` @ `ca8e14806a614a4ab28aac8fc9c642c65d3b871d` (local-only) |
| Experiment version | `1.3.0-h1-dev-scored` |
| Prior | [049](coordinator-handoff-049.md) (C1 proof PASS); [047](coordinator-handoff-047.md) (official bindings) |
| `stopped_reason` | `WaitingHuman` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-050.md
wave: D
scored: no
split: dev
result_set_digest: none
experiment_version: 1.3.0-h1-dev-scored
h1a: unclaimed
h1b: unclaimed
h1c: unclaimed
arms_valid: none
contamination: none
val_test_inspected: no
maintenance_evals_sha: ca8e14806a614a4ab28aac8fc9c642c65d3b871d
acp_changed: no
deploy_verify: PASS
blocker: 2070 msi offline again; C1 cannot be scored against qwen2.5-coder:7b
stopped_reason: WaitingHuman
```

## Outcome in one paragraph

Wave D did not freeze a scored DEV batch and did not apply the H1 procedure.
A prior in-wave attempt ran 28/612 slots into
`results/v10-h1-dev-scored-v1.staging.jsonl` without `rg` and with `msi`
unreachable; those slots are audit-only and must not be resumed or interpreted.
The scored harness is now ready under experiment version `1.3.0-h1-dev-scored`
(new version because C1 identity is `:7b` and official bindings are `1.1.0`).
The 2070 is offline again (`last seen ~1h`, curl timeout from CT103), so a
valid C1 arm cannot start. H1a/H1b/H1c remain unclaimed. Wave E was not started.

## Why v1 is not a result set

| Check | v1 staging (28 slots) |
|---|---|
| Frozen directory | no (`freeze.json` never written) |
| `rg` on PATH | no — B/C0/C1 FTS returned `retrieved_files=[]` |
| C1 live invoke | 0/7 — `msi` down; skip_reason `deterministic_preflight_sufficient` |
| Official ARB metrics | empty (`no_gold` skip on abstention-counterfactual) |
| Resume into v2 | forbidden (would pool a broken harness with a fixed one) |

Create-only note: `maintenance-evals/results/v10-h1-dev-scored-v1.INVALID.md`.

## What is ready for the resume

- Manifest `v10-context-ablation` → `1.3.0-h1-dev-scored`; controller `qwen2.5-coder:7b`
- Official bindings unchanged: `arb-adapter-1.1.0` / `swe-ci-adapter-1.1.0`
- Driver `scripts/run_context_ablation_scored.py` (DEV index only; refuses val/test)
- Pre-registered decision `src/maintenance_evals/h1_decision.py` (apply only after freeze)
- User-local `rg` at `~/.local/bin/rg` (14.1.1); driver refuses to start without it
- Driver refuses to start unless `MODEL_2070_BASE_URL` serves `qwen2.5-coder:7b`
- Next create-only directory: `results/v10-h1-dev-scored-v2`
- Launcher: `scripts/_v10_wave_d_run_scored.sh` (3080 on localhost `:11434`; C1 never there)
- DEV plan: 43 ARB + 8 SWE-CI × 3 repeats × 4 arms = **612** slots
- ACP runtime already deployed: arm-aware eval-dispatch (ADR-0034)

## Deploy verify

Prior Wave D pin remains live. Rechecked this wave:

| Host | Tip | 2070 |
|---|---|---|
| CT103 | `c5ccafe4757afec26e9ff3c11498124ba4d196b7` | `MODEL_2070_NAME=qwen2.5-coder:7b`; `/api/tags` timeout |
| CT104 | `c5ccafe4757afec26e9ff3c11498124ba4d196b7` | unchanged |

`/healthz` ok. `/readyz` degraded: `model_2070` unreachable; `model_3080` ok at
`http://100.107.20.28:11434`. Record:
[deploy-verify-v10-wave-d-20260816.md](deploy-verify-v10-wave-d-20260816.md) —
**PASS** on the arm-wiring smoke; 2070 liveness is a separate C1 gate.

No ACP source change this coordinator turn. `acp_changed: no`.

## H1 answers (procedure not applied)

The complete DEV batch was not frozen. The pre-registered procedure was not
run. Verbatim:

```text
H1a: unclaimed
H1b: unclaimed
H1c: unclaimed
```

Do not treat the 28 v1 slots as A→B / B→C0 / C0→C1 evidence.

## Decisions the next coordinator must honor

1. **Do not freeze or interpret v1 staging.** Start `v10-h1-dev-scored-v2`.
2. **Do not start until `msi` `100.125.235.54:11434` serves `qwen2.5-coder:7b`.**
   Repeat the 049 proof fields on the first C1 invoke. Do not route C1 to the
   3080 (`127.0.0.1:11434` / `buttholecentral`).
3. **WSL cannot dial msi.** Use the CT103 tunnel (`127.0.0.1:11435`) or run
   C1-reaching calls from CT103. The launcher prefers `:11435` when present.
4. **`rg` must be on PATH** before any B/C0/C1 slot. Without it, B equals A.
5. Freeze the complete 612-slot DEV batch before `decide_h1`. Then answer
   H1a/H1b/H1c only. Do not write `h1_selected_local_strategy` (Wave E).
6. Do not inspect val/test. Do not tune between arms. Do not fix evaluated-agent
   failures. Do not rerun only failures and pool them. Do not start T08.

## Next coordinator: first actions

1. Human: power on `msi` / 2070 Ollama until CT103 `/api/tags` lists only
   `qwen2.5-coder:7b` (digest `dae161e2…`).
2. `wsl bash maintenance-evals/scripts/_v10_wave_d_2070_tunnel.sh` if scoring
   from WSL.
3. `wsl bash maintenance-evals/scripts/_v10_wave_d_run_scored.sh` → v2.
4. After freeze: `python scripts/run_context_ablation_scored.py --decide-only`
   on the frozen v2 directory. Write H1a/H1b/H1c verbatim. Stop.

## Open risks (one line each)

- 2070 dropped offline after Wave C retry PASS; H1c cannot be scored until it returns.
- CT104 still holds an external model API key (C1 must not use it; Wave C boundary still enforced).
- CT102 ruff drift, carried, untouched.
- 612 slots at ~40–60 s plus SWE-CI pytest is a multi-hour batch; do not interpret a partial.
- ARB DEV includes 13 abstention samples; official `eval-trajectories` skips `no_gold` and V10 additional fails those slots by design.
