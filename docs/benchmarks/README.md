# V10 benchmark methodology (pointers)

The authoritative benchmark methodology lives in the evaluation repository,
next to the registry, field maps, split policies, and adapters it describes, so
that a version or licence cannot drift between the prose and the code that runs.

`ai-sdlc-lab/maintenance-evals/docs/benchmarks/`

| Benchmark | Page | Scorable at freeze |
|---|---|---|
| Agent-Retrieval-Bench | `agent-retrieval-bench.md` | No — awaiting licence approval |
| SWE-CI | `swe-ci.md` | No — awaiting licence approval |
| SWE-Chain | `swe-chain.md` | No — awaiting licence approval |
| SWE-bench Verified sanity subset (optional) | `swe-bench-sanity.md` | No — optional and never scored |
| Custom longitudinal corpus | `custom-longitudinal.md` | **Yes** |

Each page records upstream source and commit, paper URL, licence, official
metric, unit of evaluation, statefulness, hidden-test boundary, what the agent
may see, what the verifier may see, required transformations, and deviations
from the official evaluation.

Related, also in `maintenance-evals`:

- `docs/BENCHMARK_SPLITS.md` — frozen dev/validation/held-out membership
- `docs/BENCHMARK_LICENSES.md` — licences and redistribution gates
- `docs/STATISTICAL_PLAN.md` — the analysis plan frozen before any scored run

The seal that binds all of the above: [`../handoff/v10-experiment-freeze.md`](../handoff/v10-experiment-freeze.md).
