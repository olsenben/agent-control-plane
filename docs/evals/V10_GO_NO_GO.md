# V10 go / no-go — pointer summary

Authoritative documents live in the evaluation repository. This page exists so a
platform reader does not have to open `maintenance-evals` to learn the status,
and so no one cites a V10 artefact as evidence of maintenance performance.

| Field | Value |
|---|---|
| Produced by | V10 T10, [`coordinator-handoff-045`](../handoff/coordinator-handoff-045.md) |
| Date (UTC) | 2026-08-16 |
| Experiment freeze | `v10-experiment-freeze-2026-08-16` (unchanged) |
| Platform freeze | `eval-baseline-2026-08` at `2532de7cf5098baa461e49b92e0d338c089cff45` |
| Epic status | `blocked_waiting_human` |
| Decision | **HOLD** — no epic section 32 branch is selectable |

## Status in one paragraph

Zero of five pre-registered hypotheses are decided. Four of the five benchmarks
were never downloaded, because corpus licensing is still awaiting human approval.
The one scorable corpus was really executed for 108 slots, but no slot reached
the frozen platform's patch-authoring agent, so every outcome field is null. What
exists is a verified evaluation instrument, not a measurement of agent
performance. No V10 artefact may be cited as evidence of maintenance performance;
each frozen result set says so in its own `claim_scope` field.

## Hypotheses

```text
H1a unclaimed  H1b unclaimed  H1c unclaimed  H2 unclaimed
H3  instrument verified on the synthetic longitudinal corpus; outcome unclaimed
```

No pre-registered threshold was evaluated and no primary test was run.

## Branch assessment (epic section 32)

| Branch | Assessment |
|---|---|
| A. Standalone VerifiedChange product extraction | Not available. Every antecedent unmeasured. **Standalone SaaS cannot be a GO.** |
| B. Vendor-neutral governed control plane | Closest to the evidence and still unearned; suggestive engineering evidence, no comparative outcome |
| C. Controller-backbone research | Not available; no live C1 observation exists anywhere in V10 |
| D. External pilot / GitHub adapter | Not available on technical grounds |
| E. Stop commercial product work | Not available; a NO-GO is as unsupported as a GO |

## Human gates before any scored batch

1. `MATERIALIZE_LICENSED_CORPORA` — unlocks H1a, H1b, H1c and the external half
   of H2.
2. `EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS` — unlocks the outcome
   half of H3; requires a new experiment version.
3. `FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE` plus provider credentials and a
   spend cap — unlocks H2. Recording a decision to drop H2 also clears it.
4. One live C1 run against the real 2070 endpoint, with `controller_provider` and
   `controller_data_left_homelab` checked, before any C1 batch is scored.
5. Decide H1 on the dev split, then re-freeze the local strategy that the D, E,
   and H arms inherit.

## Platform-relevant findings

- The C0/C1 separation is proven against a mocked gateway only. No live 2070
  controller call has ever been recorded, so `controller_backend` alone is not
  evidence of an arm.
- `chat_completion_with_failover` can reach the configured external fallbacks
  `gpt-4.1` and `gpt-4o-mini`. During evaluation this is simultaneously an arm
  confound, a paid-cost event under a price table with no rows, and a
  trust-boundary event. It should be refused before scoring, not reviewed after.
- `controller_gpu_seconds` reports `0.0` when the endpoint strips `eval_duration`,
  in a system that otherwise refuses to zero-fill.
- CT102 runner and version remain `PENDING_LIVE_CERT`.

## Authoritative documents

- `ai-sdlc-lab/maintenance-evals/reports/V10_RESULTS.md`
- `ai-sdlc-lab/maintenance-evals/docs/THREAT_TO_VALIDITY.md`
- `ai-sdlc-lab/maintenance-evals/docs/GO_NO_GO.md`
- `ai-sdlc-lab/maintenance-evals/reports/DEEPER_EVAL.md`
- `ai-sdlc-lab/maintenance-evals/reports/LITERATURE_COMPARISON.md`
