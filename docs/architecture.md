# Architecture

See [gitea_agentic_sdlc_cursor_step_plan_v4.md](../../gitea_agentic_sdlc_cursor_step_plan_v4.md) (§0.4–§0.5).

**Build less like a chatbot. Build more like a governed distributed system for AI-assisted software work.**

## Project thesis (2026-06)

Persistent, auditable engineering control plane with optional recurrent-memory experiments — not a bet that recurrent models replace transformer coders on consumer hardware.

- **3080 / Qwen Coder 14B** — primary generator: plans, patches, repair attempts, final synthesis
- **2070 / recurrent-SSM** — recursive inference wrapper: memory preflight, critique packets, failure summarization, belief state, writeback after verification (not primary patch author)
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
| [slice-5-structured-output-hardening.md](slice-5-structured-output-hardening.md) | Structured output boundary (complete) |
| [slice-5.1-engine-reliability.md](slice-5.1-engine-reliability.md) | Engine I/O: Instructor adapter, parse-failure reporting (blocks 6D) |
| [slice-4c-result-ingest-automation.md](slice-4c-result-ingest-automation.md) | Event-driven ingest + reconciliation (blocks 6D) |
| [slice-5.2-plan-quality-gate.md](slice-5.2-plan-quality-gate.md) | Hollow-plan gate — no fixable WI without scoped files |
| [slice-5.3-issue-task-backfill.md](slice-5.3-issue-task-backfill.md) | Bare review/plan: backfill task from issue body on dispatch |
| [slice-6c-closed-world-diff-gate.md](slice-6c-closed-world-diff-gate.md) | Post-apply closed-world diff gate (complete) |
| [slice-6d-branch-push-pr.md](slice-6d-branch-push-pr.md) | Branch push + PR (6D — code complete; homelab pending) |
| [slice-6d1-hollow-artifact-guardrails.md](slice-6d1-hollow-artifact-guardrails.md) | Quality gates, fallback, preflight — no hollow `completed` |
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

## Recursive inference (Qwen 14B + 2070)

The 2070 lane improves Qwen 14B **effective** performance via structured recursive calls (same weights, better scaffolding). It does not replace Qwen as patch author. Bounded loops use memory preflight, graph context, diff gate, and CI/tests as required external feedback — not self-confidence alone. Config: `recursive_qwen_loop` in `.agent/project.yaml` (see V4 plan §0.4).

## Specialist roles (bounded)

Reviewer, planner, patch author, memory worker (recursive support) — four roles max unless measurable need.

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
| **Review MVP** | **Done** | Review + graph blast-radius + context-pack + memory (4A/4B); homelab issue #4 (2026-06-21 UTC) |
| Plan MVP | **Done** | Graph-informed plan + CI hints + structured comment + prior memory (issue #4) |
| **Slice 5 — structured output boundary** | **Done** | Pre-merge, normalizers, repair retry, `parse_failure.json`; homelab review `run-19a15588…` → plan `run-d71996d3…` (2026-06-21 UTC). See [slice-5-structured-output-hardening.md](slice-5-structured-output-hardening.md) |
| **Slice 6A — approval plumbing** | **Done (CT103)** | Plan-scoped `WI-*` / `PLAN-run-*` handles; owner-only approve. See [slice-6a-approval-plumbing.md](slice-6a-approval-plumbing.md) |
| **Slice 6B — local patch artifact** | **Done (CT103+CT104)** | Enqueue fix worker; `fix_result.json` + `patch.diff` in run workspace only; post-apply diff subset assert. See [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md) |
| **Slice 6C — closed-world diff gate** | **Done (CT104)** | Post-apply policy gate; `raw_patch.diff` → promoted `patch.diff`; `diff_gate_result.json`. See [slice-6c-closed-world-diff-gate.md](slice-6c-closed-world-diff-gate.md) |
| **Slice 5.1 — engine reliability** | **Done (code)** | Failure reporting, missing-JSON retry, `StructuredOutputClient`, RQ handler. Homelab failure-path re-check optional. See [slice-5.1-engine-reliability.md](slice-5.1-engine-reliability.md) |
| **Slice 4C — result ingest automation** | **Done (homelab)** | Ingest + ledger on issue #16; cron fallback still on CT103. See [slice-4c-result-ingest-automation.md](slice-4c-result-ingest-automation.md) |
| **Slice 5.2 — plan quality gate** | **Done (homelab)** | issue #16 `run-cca5ddc0…` not fixable / no WI. See [slice-5.2-plan-quality-gate.md](slice-5.2-plan-quality-gate.md) |
| **Slice 5.3 — issue-task backfill** | **Done (homelab)** | issue #16 bare plan backfills `natural_language_task`. See [slice-5.3-issue-task-backfill.md](slice-5.3-issue-task-backfill.md) |
| **6D — branch push + PR** | **Done (code); homelab pending** | issue #17 publish test. See [slice-6d-branch-push-pr.md](slice-6d-branch-push-pr.md) |
| **6E — CT102 CI truth loop** | **Planned** | After 6D homelab sign-off |
| Later | — | Command reconciliation (`agentctl commands reconcile`), AgentFacts-lite, replay console, drift detector, MCP graph |

Homelab sign-off: [AGENT_CARD.md](AGENT_CARD.md) — issue #16 (2026-07-06): 4C ingest, 5.2+5.3, 6B/6C official fix pipeline; 6D → issue #17.

### Review MVP acceptance (full)

**Status: satisfied on homelab (2026-06-21 UTC, issue #4).** See [EVALS.md](EVALS.md) and §0.5 in V4 plan. Summary:

1. Real Gitea issue; read-only clone; CT103 run record
2. Audit trail in run artifacts; structured output with risk_tags
3. Blast-radius section (repos/services/tests/ADRs + missing_edges)
4. Selective memory writeback; second command retrieval
5. No write without policy approval

### Future experiments

AgentFacts-lite, memory-as-governance, review replay console, risk-tagged ledger, graph-gated fix, CI minimizer, architecture drift detector, SARIF ingestion, MCP graph server, 2070 SSM memory worker, gated self-improvement PRs.

See §0.5 in V4 plan.
