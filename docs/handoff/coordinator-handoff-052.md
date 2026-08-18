# Handoff — coordinator-handoff-052

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 052 |
| Date (UTC) | 2026-08-18 |
| Slice / wave | V10 pre-Wave-E — SWE-CI harness repair + H1 finalization |
| ACP SHA (local driver) | `56a72babe839e33806813c4544343f21b86a85d4` (no ACP image change; deploy N/A; prior pin `c5ccafe`) |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` working tree on `ea71edef4d7c76a6779df50f55e018882f947837` plus uncommitted 1.4.0 repair |
| Experiment version | `1.4.0-h1-sweci-repair` (parent `1.3.0-h1-dev-scored`) |
| Result set | `results/v10-h1-dev-scored-v3` digest `5db3c0f781b1e4a823bab6579478968fb0e8b1278d4eba4b1e4c2b46c6f4b5ae` |
| Canonical H1 | `results/v10-h1-dev-scored-v2` digest `13ba38d5fa72b38a73d65d36b2b334feb3ed4a50da1c379491dc969450247685` (unchanged) |
| Prior | [051](coordinator-handoff-051.md) |
| `stopped_reason` | `context_handoff` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-052.md
wave: pre-E SWE-CI repair
scored: yes (SWE-CI DEV only)
split: dev
result_set_digest: 5db3c0f781b1e4a823bab6579478968fb0e8b1278d4eba4b1e4c2b46c6f4b5ae
experiment_version: 1.4.0-h1-sweci-repair
slots_frozen: 96/96
canonical_h1a: UNDECIDED
canonical_h1b: FAIL
canonical_h1c: FAIL
h1_selected_local_strategy: local-deterministic
selection_status: operational_selection_not_hypothesis_pass
c1_invoked_v3: 0/24
harness_v3: 0
v2_digest_unchanged: yes
val_test_inspected: no
wave_e_started: no
deploy_verify: N/A
blocker: none
stopped_reason: context_handoff
```

## Outcome in one paragraph

SWE-CI `No module named 'swe_ci'` was a scored-driver import defect. The repair
subprocesses the Wave B interpreter; ACP `.venv` was not pip-installed. Create-only
v3 scored SWE-CI DEV only (96 slots). Valid v2 ARB was not rerun. Canonical
scientific H1 remains v2 ARB: H1a UNDECIDED, H1b FAIL, H1c FAIL. Operational
strategy is `local-deterministic` under the POST-WAVE-D PROSPECTIVE DOWNSTREAM
SELECTION RULE, labeled `operational_selection_not_hypothesis_pass`. Wave E is
ready to inherit that strategy and was not started.

## Frozen result sets

| Field | v2 (canonical ARB) | v3 (SWE-CI repair) |
|---|---|---|
| Directory | `results/v10-h1-dev-scored-v2` | `results/v10-h1-dev-scored-v3` |
| Digest | `13ba38d5…247685` | `5db3c0f7…c6f4b5ae` |
| Version | `1.3.0-h1-dev-scored` | `1.4.0-h1-sweci-repair` |
| Slots | 612 | 96 |
| Harness | 96 (SWE-CI) | 0 |
| Role | primary H1 | supporting only |

Composite: `maintenance-evals/results/v10-h1-dev-composite-v2-arb-v3-sweci.json`.
`pool_for_replacement_primary: false`.

## H1 answers

Canonical (v2 ARB, unchanged):

```text
H1a: UNDECIDED
H1b: FAIL
H1c: FAIL
```

Supporting SWE-CI (`v10-h1-dev-scored-v3-h1-decision-supporting.json`): H1a FAIL,
H1b FAIL, H1c UNDECIDED. The supporting H1c UNDECIDED is a ~2.6s wall-clock
difference with `controller_model_invoked=0/24`. It does not overturn canonical
H1c FAIL.

H1c evaluates the frozen conditional-controller policy. The controller was never
triggered under that policy. This does not prove that a forced or redesigned
controller could never help.

SWE-CI official_benchmark_pass is false on 96/96; v10 additional is true on
96/96; verified_success is 0/96.

## Operational selection

`results/v10-h1-dev-scored-v3-selected-strategy.json`

```text
h1_selected_local_strategy: local-deterministic
selection_status: operational_selection_not_hypothesis_pass
selection_rule_name: POST-WAVE-D PROSPECTIVE DOWNSTREAM SELECTION RULE
```

## Deploy verify

No ACP image/code change required for the isolated-verifier repair.
`deploy_verify: N/A`. Gate 6: CT104 `MODEL_*_EXTERNAL_API_KEY` removed from host
`.env` and all three workers (2026-08-17).

## Decisions the next coordinator must honor

1. Canonical H1 is v2 ARB. Do not rewrite UNDECIDED as PASS. Do not pool v3.
2. Wave E inherits `local-deterministic` as an operational pick, not an H1a PASS.
3. Do not inspect val/test. Do not start T08. Do not start Wave E in this handoff.
4. Do not overwrite `results/v10-h1-dev-scored-v2/**`.
5. Forced/redesigned C1 arms are DEEPER_EVAL only, never retrofitted as H1c.

## Next coordinator: first actions

1. Wave E: inherit `local-deterministic` for D/E/H.
2. Leave val/test sealed. Leave T08 WaitingHuman.

## Open risks (one line each)

- C1 invoked 0/24 on v3 and 0/153 on v2 ARB; H1c is the frozen conditional policy.
- SWE-CI official success is 0/96; coverage is restored, not a quality win.
- ACP local SHA `56a72bab` vs deployed pin `c5ccafe`; repair was eval-driver only.
- CT102 ruff drift, carried.
- `maintenance-evals` 1.4.0 repair is on the working tree; commit still pending.
