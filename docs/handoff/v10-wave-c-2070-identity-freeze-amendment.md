# V10 Wave C — 2070 controller identity freeze amendment

| Field | Value |
|---|---|
| Date (UTC) | 2026-08-16 |
| Authority | Boss human resume after handoff 048; Wave C retry (handoff 049) |
| Kind | Identity freeze / host alignment |
| ACP runtime | unchanged (env-only on hosts) |
| Experiment version | **not** bumped — no scored C1 batch has run; this makes the C1 identity comparable before any scored arm |

## What was recorded at T00 / T04 (do not rewrite)

| Record | Value then |
|---|---|
| [V10_BASELINE.md](../evals/V10_BASELINE.md) | `MODEL_2070_NAME=qwen2.5-coder:3b`; `:7b` listed as available but not configured |
| [v10-experiment-freeze.md](v10-experiment-freeze.md) §7 | Controller model `qwen2.5-coder:3b` |
| Handoff [034](coordinator-handoff-034.md) decision 3 | T00.5 must use configured `:3b` |
| Handoff [048](coordinator-handoff-048.md) | CT103 `:3b` vs CT104 `:7b`; 2070 offline; `c1_proof=FAIL`; `controller_model_id=qwen2.5-coder:3b` with `planned_not_invoked` |
| Live evidence 048 | [c1-live-smoke-027ad9f.json](../evidence/v10-wave-c/c1-live-smoke-027ad9f.json) — left intact |

Those records stay true as history. This amendment does not edit 048 or its
JSON.

## Why the T00 identity cannot be served

ACP-host `/api/tags` against the configured 2070 URL
(`http://100.125.235.54:11434`, `msi`) returns only `qwen2.5-coder:7b`
(digest `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`,
Q4_K_M, 7.6B). `qwen2.5-coder:3b` is absent. CT103's configured `:3b` cannot
be an observation.

The human localhost curl on `buttholecentral` also listed `:14b` and
`llama3:latest`. From the ACP hosts those names are on the **3080** URL
(`http://100.107.20.28:11434`), not on `msi`. They are not C1 candidates.

## Frozen identity (Wave C retry)

```text
MODEL_2070_NAME = qwen2.5-coder:7b
MODEL_2070_BASE_URL = http://100.125.235.54:11434
digest            = dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364
quant / params    = Q4_K_M / 7.6B
```

Reason (boss, not invented here): `:7b` is the only previously-configured
identity (CT104 already used it) that the live 2070 endpoint actually serves.
Do not select `:14b` (never a configured C1 identity). Do not keep `:3b`.

## What this is not

No change to prompts, recursive trigger, budgets, tool policy, sampling,
verification, Qwen patch-author identity (`MODEL_3080_NAME=qwen2.5-coder:14b`),
`config/recursive_context.yaml` (still `8258dc95…`), or C1 evaluated behaviour
other than the requested model name on CT103.

## Host action

CT103 `.env` `MODEL_2070_NAME` `qwen2.5-coder:3b` → `qwen2.5-coder:7b`, then
recreate `control-plane` (no rebuild). CT104 already had `:7b`. Both containers
now print `MODEL_2070_NAME=qwen2.5-coder:7b`.
