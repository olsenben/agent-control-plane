# Evaluations

How we measure the homelab agent control plane — maintainability and traceability over headline benchmark scores.

## Verification invariant

Findings are hypotheses. Fixes are proposals. **Truth** requires:

1. Deterministic checks
2. Tests
3. CT102 CI
4. Human approval (Risk 2+)

Model self-review is not an acceptance gate (MIT Sloan verification work).

## Review MVP evals

| Criterion | Pass condition |
|-----------|----------------|
| Command dispatch | `/agent review` from real Gitea issue enqueues rlm-root |
| Read-only clone | CT104 clones repo; no writes |
| Run record | CT103 durable run record with `run_id` |
| Audit trail | Prompt hash, context sources, model output, final comment logged in run artifacts |
| Structured output | Findings, files inspected, confidence, risk_tags, next action, rejected/uncertain hypotheses |
| Graph context | Blast-radius section: affected repos/services/tests/ADRs + missing_edges |
| Memory writeback | Selective `memory_record.v1` — not full prompt dump |
| Second command | Retrieves prior review memory for same issue |
| Policy | No write-capable command without explicit approval |
| Injection | Preamble present; `test_prompt_injection` passes |

Runbook: [RUNBOOK_REVIEW_MVP.md](RUNBOOK_REVIEW_MVP.md).

## CI-native maintainability harness (future)

Score on **your repos** over repeated iterations (SWE-CI / SlopCodeBench rhymes):

| Metric | Description |
|--------|-------------|
| `retries_per_issue` | Commands before human resolution |
| `repeated_failure_rate` | Same dead end revisited |
| `diff_churn` | Lines changed per successful fix |
| `regression_rate` | Follow-up task breaks prior fix |
| `dead_end_avoidance` | Second run skips rejected hypotheses |
| `ci_first_pass_rate` | Fix branches green on first CT102 run |
| `graph_consultation_rate` | Review runs with blast-radius populated |

Log to `agent-state/evals/maintainability.jsonl`.

## Agent transparency (MIT AI Agent Index)

Maintain [AGENT_CARD.md](AGENT_CARD.md) + [agent-card.json](../agent-card.json):

- Capabilities vs safety disclosures
- Known limitations
- Safety test status
- `last_verified` dates

## Safety test suite

```bash
cd agent-control-plane
pytest -q tests/test_prompt_injection.py
pytest -q tests/test_dispatch_payload.py
pytest -q tests/test_intent_parser.py
pytest -q  # full suite before deploy
```

Target additions:

- `tests/test_policy_gates.py`
- `tests/test_memory_writeback.py`
- `tests/test_graph_blast_radius.py`

## Architecture drift detector (portfolio eval, later)

Compare ADR-declared dependencies vs graph-derived edges:

```text
adr_mentions_service(A) -> service_depends_on_service(A, B)
actual imports/deploy config -> repo graph edges
drift = ADR edge missing in graph or graph edge contradicts ADR
```

Distinctive eval: architecture + governance + agents — not generic "AI code review."

## Recurrent memory worker evals (2070)

Measure compression quality, not patch benchmarks:

- Retrieval precision on second-command queries
- Rejected-hypothesis recall
- Token budget reduction vs raw history
- Failure fingerprint classification accuracy

Candidate backends: RWKV, xLSTM, liquid SSM experiments.

## Do not optimize for

- Single SWE-bench headline score alone
- Model-only "looks correct" without CT102
- Autonomous merge rate
