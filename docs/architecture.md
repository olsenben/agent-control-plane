# Architecture

See [gitea_agentic_sdlc_cursor_step_plan_v4.md](../../gitea_agentic_sdlc_cursor_step_plan_v4.md) (§0.4–§0.5).

**Build less like a chatbot. Build more like a governed distributed system for AI-assisted software work.**

## Project thesis (2026-06)

Persistent, auditable engineering control plane with optional recurrent-memory experiments — not a bet that recurrent models replace transformer coders on consumer hardware.

- **3080 / Qwen-class** — primary reasoning, review, plan, patch authoring
- **2070 / recurrent-SSM** — memory specialist: compression, failure fingerprints, retrieval hints
- **CT102** — authoritative CI truth; model self-review is not an acceptance gate
- **Near-term:** memory retrieval, traceability, policy gates, minimal cross-repo graph — not more autonomy

## Three-layer truth model

| Layer | Question | Owner |
|-------|----------|-------|
| **Memory** | What happened on prior runs? | CT103 SQLite trajectory memory |
| **Graph** | What depends on what? | CT103 cross-repo intelligence graph |
| **CI** | What is actually broken? | CT102 Gitea Actions |

All three are required. Findings are hypotheses until CI + human verification.

## Transparency and governance artifacts

| Doc | Purpose |
|-----|---------|
| [AGENT_CARD.md](AGENT_CARD.md) | Product-style agent disclosure (MIT AI Agent Index) |
| [POLICY_GATES.md](POLICY_GATES.md) | Risk 0–3 minimum viable governance (MIT CISR) |
| [MEMORY_SCHEMA.md](MEMORY_SCHEMA.md) | Selective trajectory memory schema |
| [THREAT_MODEL.md](THREAT_MODEL.md) | Searchable `risk_tags` on events |
| [EVALS.md](EVALS.md) | Review MVP + maintainability metrics |
| [RUNBOOK_REVIEW_MVP.md](RUNBOOK_REVIEW_MVP.md) | Verification runbook |
| [graph-indexer.md](graph-indexer.md) | Graph-lite: Tree-sitter + SQLite + catalog-info |
| [graph-oss-borrowing.md](research/tool-spikes/graph-oss-borrowing.md) | OSS borrow map and phases |

## Homelab tiers

```text
Gitea
  -> CT103 governance + memory + graph-indexer
       event ledger (risk_tags), policy gates, SQLite memory + graph
       agentctl graph snapshot | blast-radius | context-pack
       (Tree-sitter + NetworkX + catalog-info.yaml — borrow, don't rebuild)
  -> CT104 execution (read-only first, gated writes later)
  -> 3080 Qwen / 2070 memory worker (inference only)
  -> CT102 CI truth
```

## Policy gates (summary)

| Risk | Commands | Key rule |
|------|----------|----------|
| 0 | inspect, explain | Read-only; auto-run |
| 1 | review, plan | Read-only; selective memory; graph blast-radius required |
| 2 | fix | Branch only; human approval; CT102 verifies |
| 3 | deploy/secrets | Blocked by default |

Detail: [POLICY_GATES.md](POLICY_GATES.md).

## Verification invariant

No model output is true until: deterministic checks → tests → CT102 CI → human approval (Risk 2+).

## Specialist roles (bounded)

Reviewer, planner, patch author, memory worker — four roles max unless measurable need.

Agent identity / AgentFacts-lite before A2A/MCP protocol glue.

## Control-plane data flow

```text
Gitea -> webhook -> policy gate -> memory + graph retrieval
  -> CT104: context pack (issue, diff, ADR, blast-radius, prior memory)
  -> 3080 model -> structured output + risk_tags
  -> audit in run artifacts (prompt hash, sources, output, comment)
  -> ingest -> selective memory writeback -> risk-tagged event
```

## Implementation roadmap

| Phase | Status | Target |
|-------|--------|--------|
| Inspect MVP | **Done** | End-to-end plumbing |
| Explain smoke | Next | Second Risk 0 command |
| **Review MVP** | **In progress** | Review + graph blast-radius + context-pack (memory = Slice 4) |
| Plan MVP | **In progress** | Graph-informed plan + CI hints + structured comment |
| Fix MVP | Deferred | Graph-gated approval + branch + CT102 |
| Later | — | AgentFacts-lite, replay console, drift detector, MCP graph |

### Review MVP acceptance (full)

See [EVALS.md](EVALS.md) and §0.5 in V4 plan. Summary:

1. Real Gitea issue; read-only clone; CT103 run record
2. Audit trail in run artifacts; structured output with risk_tags
3. Blast-radius section (repos/services/tests/ADRs + missing_edges)
4. Selective memory writeback; second command retrieval
5. No write without policy approval

### Future experiments

AgentFacts-lite, memory-as-governance, review replay console, risk-tagged ledger, graph-gated fix, CI minimizer, architecture drift detector, SARIF ingestion, MCP graph server, 2070 SSM memory worker, gated self-improvement PRs.

See §0.5 in V4 plan.
