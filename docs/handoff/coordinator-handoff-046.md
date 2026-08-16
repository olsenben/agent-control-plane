# Handoff — coordinator-handoff-046

## Meta

| Field | Value |
|---|---|
| Handoff ID | 046 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10-WAVE-A-1.2.0-eval-dispatch (commit + deploy-verify only) |
| Tip SHA (ACP) | `657a445d38e0b2a32970c7b6169e598883b33d06` |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` @ `fb7bde1e58c4666f75c0182fd96bab9817e201d4` (local-only, no remote) |
| Experiment freeze | `v10-experiment-freeze-2026-08-16`, amended (both corpora and dispatch gates recorded cleared) |
| Experiment version | `1.2.0-eval-dispatch` |
| Deploy verify | [deploy-verify-v10-wave-a-eval-dispatch-20260816.md](deploy-verify-v10-wave-a-eval-dispatch-20260816.md) — **PASS** |
| `stopped_reason` | `group_boundary_stop` (Wave A only; Wave B not started by design) |

## Sealed return

```text
handoff_path: docs/handoff/coordinator-handoff-046.md
wave: A
ticket: V10-WAVE-A-1.2.0-eval-dispatch
acp_sha: 657a445d38e0b2a32970c7b6169e598883b33d06
maintenance_evals_sha: fb7bde1e58c4666f75c0182fd96bab9817e201d4
maintenance_evals_materialization_sha: 886c9703895c5ba421e24b232c8d0796e75148bb
deployed_sha: 657a445d38e0b2a32970c7b6169e598883b33d06
deploy_verify: PASS
smoke: results/v10-t07b-longitudinal-de-agent-smoke-v1 agent_execution=true 6/6
t07_instrument_preserved: yes
scored_result_produced: no
hypotheses_decided: 0 / 5
paid_calls: 0
blocker: none
stopped_reason: group_boundary_stop
```

## What landed

Three commits, split by provenance rather than by convenience.

1. `maintenance-evals@886c970` — **`MATERIALIZE_LICENSED_CORPORA` clearance.**
   Registry, split policies, field maps, adapters (`1.0.1`), gate tests and the
   identifier-level evidence for ARB (427), SWE-CI (100) and SWE-Chain (155).
   Registry SHA-256 `adf6f971…`. Raw corpora stay outside Git.
2. `maintenance-evals@fb7bde1` — **`1.2.0-eval-dispatch` harness.**
   `adapters/agent_control.py` resolves the trusted ACP command;
   `run_longitudinal_de.py --with-agent` dispatches each slot and records real
   outcome/telemetry fields; the manifest version bump; the non-scored smoke set.
3. `agent-control-plane@657a445` — **`agentctl eval dispatch`.**
   `src/agent_control/eval_dispatch.py` implements `maintenance_eval_dispatch.v1`
   over JSON stdio with an exact-SHA workspace invariant, plus the CLI wiring and
   the freeze-document amendment. Pushed to `origin/main`.

The one place the split could not be clean is
`manifests/experiments/v10-longitudinal.yaml`: its registry-SHA and SWE-Chain
hunks belong to the corpora clearance and its `experiment_version` line belongs to
eval-dispatch. It was staged with the old version string in commit 1 and bumped in
commit 2, so each commit is internally consistent.

Both working trees carry unrelated dirt from earlier sessions (V9 productization
docs, `agent-facts.json` re-signing, ~250 untracked scratch scripts). None of it
was swept in. `maintenance-evals` is now clean on tracked files; ACP still shows
the V9 documentation edits and the revised epic plan, deliberately left for their
own owner.

## Deploy verification summary

`DEPLOY_VERIFY: PASS`. CT103 and CT104 both pinned to `657a445` and rebuilt. The
runtime delta against the previously deployed `e5d91ce` is exactly two files —
`cli.py` and `eval_dispatch.py` — so this is the smallest possible platform move
for the gate it clears.

Live proof rather than inference: a throwaway git workspace was created **inside**
the CT103 `control-plane` container and dispatched through `agentctl eval dispatch`,
returning a `maintenance_eval_session.v1` record with `status=finished` and
`agent_execution=true`. The host-side longitudinal smoke then produced 6 of 6 slots
with `agent_execution=true` under `experiment_version 1.2.0-eval-dispatch`, and the
T07 instrument set still hashes to `6f2fe308…` under `1.1.0-t04-frozen`.

Pre-commit gates: ACP ruff clean and 905 tests passed; maintenance-evals ruff clean
on the committed surface and 179 tests passed.

## Three findings the next coordinator must not rediscover

1. **CT102 CI is red for a reason that has nothing to do with this wave.**
   `pyproject.toml` pins `ruff>=0.4`, CI installs `0.16.3`, and a clean checkout of
   the tip reports 391 lint errors under `0.16.3` versus 0 under the repo's pinned
   `0.15.17`. `Lint` fails in about one second and `Test` is skipped, which is why
   `deploy` and `deploy-ct104` never reach their deploy steps. This began at
   `d9dae98`; `2532de7` and `fa51ec8` were green. Deployment was therefore applied
   by host pin, as in V10 waves 2 and 4. Fixing it means pinning the dev extra and
   re-greening the tree — a wave of its own, and it touches the frozen platform.
2. **CT104 holds a real external model API key.** All three workers carry
   `MODEL_2070_EXTERNAL_API_KEY` / `MODEL_3080_EXTERNAL_API_KEY` (`sk-…`, 164
   chars, same value), and CT103 `/readyz` resolves both external and fallback
   model checks against `https://api.openai.com/v1`. The `.env` predates this wave
   by weeks and Wave A made zero paid calls, but a "local-only" scored batch could
   silently fail over to a paid endpoint. Resolve or explicitly freeze this before
   Wave B scores anything.
3. **In-container dispatch loses control-plane provenance.** `control_plane_sha`
   came back as forty zeros inside the container because the image carries no git
   checkout. Set `CONTROL_PLANE_SHA` (or `EVAL_CONTROL_PLANE_SHA`) for any scored
   batch dispatched in-container; harness runs from the repo checkout are fine.

## Decisions the next coordinator must honor

1. **No hypothesis moved.** H3 is still unclaimed. Clearing the dispatch path is
   not evidence about memory; only a full scored D/E agent batch evaluated against
   the four pre-registered thresholds can claim it.
2. **The T07 instrument set is immutable.** `results/v10-t07-longitudinal-de-v1`
   stays at `6f2fe308…` under `1.1.0-t04-frozen`. Agent runs write to a new
   directory under `1.2.0-eval-dispatch`.
3. **Split assignments were not redrawn** when the corpora gate cleared. Seeds and
   `frozen_groups` are untouched; redrawing them would be a protocol violation.
4. **Frontier work stays gated.** `FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE` is
   still open, so `v10-frontier-hybrid` and `v10-hybrid-held-out` keep it in
   `resolve_before_scoring` even though their corpora are now materialized.
5. **`maintenance-evals` has no Git remote.** Its SHAs are local-only; do not
   report them as pushed and do not assume another host can fetch them.

## Next coordinator: first actions

1. Read this handoff and the deploy-verify record; do not re-verify the deploy.
2. Get an explicit human decision on finding 2 (CT104 model key) before proposing
   any scored batch — it is the cheapest way to invalidate a Wave B result.
3. If Wave B is authorized, the scored longitudinal D/E agent batch is the shortest
   route from zero decided hypotheses to one: the corpus is materialized, the
   instrument is verified, and the dispatch path is now live.

## Open risks

- CT102 pipeline red; every future tip will look "unverified" to anyone reading
  Actions alone until ruff is pinned.
- Non-scored smoke result sets are not reproducible byte-for-byte (session ids and
  timestamps are embedded); only frozen scored sets carry hash stability.
- The `official` dispatch engine has been exercised end to end only through the
  fake engine in this wave; the first real-engine batch will be the first true test
  of wall-clock limits and local GPU availability.
