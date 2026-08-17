# Handoff — coordinator-handoff-051

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 051 |
| Date (UTC) | 2026-08-17 |
| Slice / wave | V10 Wave D — scored H1 DEV A/B/C0/C1 freeze + decide-only |
| ACP deployed SHA | `c5ccafe4757afec26e9ff3c11498124ba4d196b7` (runtime `9447c1c`; ADR-0034); no runtime change this turn |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` @ `ea71edef4d7c76a6779df50f55e018882f947837` (local-only) |
| Experiment version | `1.3.0-h1-dev-scored` |
| Result set | `results/v10-h1-dev-scored-v2` digest `13ba38d5fa72b38a73d65d36b2b334feb3ed4a50da1c379491dc969450247685` |
| Prior | [050](coordinator-handoff-050.md) (v1 invalid; v2 not yet frozen) |
| `stopped_reason` | `context_handoff` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-051.md
wave: D
scored: yes
split: dev
result_set_digest: 13ba38d5fa72b38a73d65d36b2b334feb3ed4a50da1c379491dc969450247685
experiment_version: 1.3.0-h1-dev-scored
slots_frozen: 612/612
h1a: UNDECIDED
h1b: FAIL
h1c: FAIL
arms_valid: A,B,C0,C1
contamination: none
val_test_inspected: no
v1_interpreted: no
second_batch_started: no
maintenance_evals_sha: ea71edef4d7c76a6779df50f55e018882f947837
acp_changed: no
deploy_verify: N/A
blocker: none
stopped_reason: context_handoff
```

## Outcome in one paragraph

Wave D froze the create-only scored DEV batch `v10-h1-dev-scored-v2` at 612/612
and applied the pre-registered `decide_h1` procedure with `--decide-only`.
H1a is **UNDECIDED** (8pp success threshold met on ARB, Holm does not survive).
H1b is **FAIL**. H1c is **FAIL**. Arms A/B/C0/C1 are valid. Contamination is
none. `h1_selected_local_strategy` was not written. Val/test were not
inspected. v1 was not interpreted. A second scored batch was not started.
Wave E and T08 were not started.

## Frozen result set

| Field | Value |
|---|---|
| Directory | `maintenance-evals/results/v10-h1-dev-scored-v2` |
| `freeze.json` | `slot_count=612`, `scored=true`, `experiment_version=1.3.0-h1-dev-scored` |
| `result_set_sha256` | `13ba38d5fa72b38a73d65d36b2b334feb3ed4a50da1c379491dc969450247685` |
| `raw_results_sha256` | `c830c8a29e6a9d3dafee22dd717acd8982e61bc9485a6135b8d245a582faa5f7` |
| `execution_order_sha256` | `da717c2a1b68d5145cc3fdef658f0329b1d4e5870837dce6021db9933b1743c1` |
| Decide-only | `results/v10-h1-dev-scored-v2-h1-decision.json` (`h1_dev_decision.v1`) |
| Split | `dev` only |
| Seed | `20260815` |

v1 staging remains audit-only (`results/v10-h1-dev-scored-v1.INVALID.md`). It
was not resumed and was not scored.

## H1 answers (verbatim from `decide_h1`)

Applied only after freeze. `--decide-only` reproduced the freeze-time
decision. Verdicts:

```text
H1a: UNDECIDED
H1b: FAIL
H1c: FAIL
```

| ID | Question | Comparison | Verdict | Why |
|---|---|---|---|---|
| H1a | Did deterministic context help? | B vs A | UNDECIDED | `t1_8pp_success=true` (`verified_success_diff=0.209`); `holm_survives=false` (`p=0.171875`, `p_holm=0.515625`) |
| H1b | Did deterministic recursive orchestration help? | C0 vs B | FAIL | `verified_success_diff=0.0`; no threshold met; `p=1.0` |
| H1c | Did the live 2070 controller add incremental value? | C1 vs C0 | FAIL | no incremental benefit; `verified_success_diff=0.0`; C1 wall +5.99s is not a win |

Paired tests used **43 ARB DEV tasks / 6 clusters**. Holm family `(H1a, H1b, H1c)`,
alpha 0.05, permutation seed `20260815`.

Do not treat UNDECIDED as PASS. Do not write `h1_selected_local_strategy`
from this wave.

## Watch items (recorded; batch not invalidated)

| Check | Frozen v2 |
|---|---|
| `rg` on PATH | yes (14.1.1); B ≠ A (ARB verified_success 0 vs 27 true slots) |
| Retrieval nonempty | A 0 / B 27 / C0 27 / C1 27 |
| C1 invoke | **0/153** (`controller_model_invoked=false`, `recursive_invoked=0`) |
| C1 identity | never gpt-4o-mini / external; `gpt4_hits=0`; driver `MODEL_2070_BASE_URL=http://127.0.0.1:11435` |
| 3080 | localhost `:11434` served `:14b`/`:7b`/`llama3`; C1 did not use it |
| `msi` digest | `qwen2.5-coder:7b` `dae161e2…` via CT103 and the `:11435` tunnel |
| Contamination | none; `controller_data_left_homelab` never true |
| Infra | 0 |
| Evaluated-agent | 3 |
| SWE-CI | 96/96 `failure_class=harness` (`ModuleNotFoundError: No module named 'swe_ci'`); excluded by the frozen procedure; `agent_execution=true` on those slots |
| Overnight stall | wait-loop gap 2026-08-17 05:37Z–12:44Z (~7h, slots 239→241); same WSL pid `131047` resumed; tunnel briefly down at 12:44Z then up by 12:48Z without killing the driver |

SWE-CI official metrics were not computed. H1 is ARB-DEV only. That is a
coverage constraint, not a v1-style invalidation (`rg` worked; C1 was not
answered by a frontier model; ARB evaluated-agent behavior was not rewritten
by the SWE-CI import miss).

## Deploy verify

No ACP source or image change this coordinator turn. Prior Wave D pin remains
live (`c5ccafe`). `deploy_verify: N/A`. `acp_changed: no`.

## Decisions the next coordinator must honor

1. **H1a/H1b/H1c are the frozen procedure verdicts.** Do not re-tune thresholds.
   Do not re-run and pool failures.
2. **Do not write `h1_selected_local_strategy` from a PASS that did not happen.**
   H1a is UNDECIDED. Wave E owns strategy inheritance.
3. **Do not inspect val/test.** Do not start T08.
4. **Do not interpret v1.** Do not start a v3 scored batch.
5. **SWE-CI DEV slots in this freeze are harness-excluded.** Repairing
   `swe_ci` import is a new experiment version if it changes scored rows.

## Next coordinator: first actions

1. Wave E only: inherit or hold local strategy from these H1 verdicts.
2. Leave val/test sealed. Leave T08 WaitingHuman.

## Open risks (one line each)

- C1 never invoked on 153 slots; H1c FAIL means "no incremental benefit", not "2070 was unused as a live proof of routing".
- SWE-CI DEV contributed 0 paired tasks (`swe_ci` module missing in the scored driver env).
- CT104 still holds an external model API key (unused by C1 in this freeze).
- CT102 ruff drift, carried, untouched.
- `cost_per_verified_gain` serialized as JSON `NaN` in the decision file (local paid cost is 0; t2 cannot trigger).
