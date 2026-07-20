# Agent card

Product-style transparency document for the homelab coding-agent control plane. Inspired by the [MIT AI Agent Index](https://aiagentindex.mit.edu/) — document the agent like a product, not a script.

Machine-readable companion: [agent-card.json](../agent-card.json) (generated/maintained alongside this file).

## Identity

| Field | Value |
|-------|-------|
| **Agent name** | `ai-sdlc-lab-control-plane` |
| **Version** | See `agentctl version` / git tag on CT103 deploy |
| **Operator** | Homelab (single-tenant) |
| **Control surface** | Gitea issue/PR comments (`/agent …`) |
| **Governance host** | CT103 (`agent-control-plane`) |
| **Execution host** | CT104 (`agent-worker`) |
| **CI truth** | CT102 Gitea Actions (`docker-ci`) |

## Supported commands

| Command | Autonomy | Repo access | Memory write | Gitea comment | Human approval |
|---------|----------|-------------|--------------|---------------|----------------|
| `/agent inspect` | Risk 0 — auto-run | Read-only clone | No | Yes | None |
| `/agent explain` | Risk 0 — auto-run | Read-only clone | No | Yes | None |
| `/agent review` | Risk 1 — auto-run | Read-only clone | Yes (selective) | Yes | None |
| `/agent plan` | Risk 1 — auto-run | Read-only clone | Yes (selective) | Yes | None |
| `/agent fix` | Risk 2 — gated | Branch write only | Yes | Yes | Required before execution |
| deploy / migrate / secrets | Risk 3 | — | — | — | **Blocked by default** |

Detail: [POLICY_GATES.md](POLICY_GATES.md).

## Allowed tools (by worker)

### CT104 `worker-rlm-root`

- `git clone` / `git fetch` (read-only credentials)
- `git diff`, file read within worktree
- Model inference (3080 primary; 2070 memory compression when enabled)
- Session artifact write (run dir only)
- Structured output validation

### CT104 `worker-report`

- Result inbox write (`agent-state/inbox/ct104-results/`)
- **No** Gitea comments (V4.1.1 — CT103 only)

### CT104 producers (fix / repair)

- Immutable `bundle-inbox` READY artifacts (`patch-bundle.v1`)
- **No** Gitea write tokens (fail-closed at startup)

### CT103

- Webhook intake, event append, reducer, dispatch
- Memory writeback (SQLite), graph snapshot queries
- **`worker-state` / results-ingest**: Gitea issue comments for plan/review/inspect/explain (+ failed fix summaries) via `GITEA_BOT_TOKEN`
- **`publish-broker`**: sole repo mutation (push / PR) + publish lifecycle comments after independent validation
- Policy gate evaluation, risk tag attachment
- No direct `main` / protected-branch mutation

## Write permissions

| Resource | CT103 | CT104 read workflows | CT104 fix (gated) |
|----------|-------|----------------------|-------------------|
| `agent-state` events | Append (reducer) | Read via mount | Read |
| Memory DB | Read/write | No | No |
| Target repo | Via `publish-broker` only | Read-only clone | Patch bundle only (no push) |
| `main` / protected branches | No | No | **Never** |
| Gitea comments | CT103 ingest + publish-broker | **No** | **No** |

## Model endpoints

| Tier | Host | Default model | Role |
|------|------|---------------|------|
| 3080 | Tailscale Ollama | `qwen2.5-coder:14b` | Review, plan, patch reasoning |
| 2070 | Tailscale Ollama | `qwen2.5-coder:7b` | Memory compression, retrieval hints |
| Fake | In-process | `FakeRLMEngine` | CI/offline tests |

Routing: `MODEL_ROUTING_POLICY` in CT104 `.env`.

## Memory sources

| Source | Owner | Used for |
|--------|-------|----------|
| Event ledger (`agent-state/events/`) | CT103 | Audit, replay |
| Trajectory memory (SQLite) | CT103 | Prior runs, rejected hypotheses |
| Cross-repo intelligence graph | CT103 | Blast-radius, affected tests/services |
| ADR compiler output | CT103 | Architecture constraints |
| Tree-sitter / FTS5 index | CT103 | Symbol and text retrieval |

Schema: [MEMORY_SCHEMA.md](MEMORY_SCHEMA.md).

## Approval requirements

```text
Risk 0 (inspect/explain):     none
Risk 1 (review/plan):         none; structured output required
Risk 2 (fix):                 explicit human approval before dispatch
Risk 3 (deploy/secrets):      blocked unless one-off override + manual verification
```

Fix approval is recorded as a CT103 event (`human.approval_granted`).

## Known limitations

- Single-tenant homelab; no multi-org isolation
- Graph indexer MVP covers subset of node/edge types (see [graph-indexer.md](graph-indexer.md))
- Model findings are **hypotheses** until CT102 CI + human verification
- No autonomous merge to protected branches
- MCP write tools not exposed; read-only MCP state server is future-only
- AgentFacts signing not yet implemented (planned: AgentFacts-lite)

## Safety tests

| Test area | Location | Status |
|-----------|----------|--------|
| Prompt injection guards | `tests/test_prompt_injection.py` | Passing |
| Public surface restriction | `tests/test_webhook_*` | Passing |
| Dispatch payload validation | `tests/test_dispatch_payload.py` | Passing |
| Structured output validation | `tests/test_*_output_normalization.py`, `model_output.py`, engine layer | **Slice 5 done** (163 tests) |
| Policy gate unit tests | target | Not yet |
| Graph blast-radius smoke | `tests/test_graph_blast_radius.py`, CT103 live | Verified 2026-06-18 |
| Plan structured output | `tests/test_fake_plan_run.py`, engine layer | Plan MVP + Slice 5 |
| Risk 2 approval + local patch | `tests/test_approval_*.py`, `tests/test_fix_*.py`, `tests/test_fake_fix_run.py` | **Slice 6A+6B done** (211 tests) |

Run: `pytest -q` in `agent-control-plane`.

## Verification invariant

No model output is considered true until validated by:

1. Deterministic checks (schema, policy, closed-world diff gate)
2. Tests (unit/integration in repo)
3. CT102 CI (authoritative)
4. Human approval where required (Risk 2+)

Model self-review is **not** an acceptance gate.

## Last verified

| Milestone | Date (UTC) | Evidence |
|-----------|------------|----------|
| Inspect MVP end-to-end | 2026-06-14 | Homelab runbook + ingest |
| Review Slice 1 (structured comment) | 2026-06-17 | `agent-control-plane` issue #3; run `run-d91435838f457716cb443736c4cc3c6b`; README in files inspected, blast-radius stub |
| Review MVP (graph + context-pack) | 2026-06-18 | CT103 snapshot + blast-radius; `/agent review` on issue #2/#3 |
| Plan MVP (structured comment) | 2026-06-21 | issue #2; `plan_result.v1` + `/agent plan` on official engine (`run-425a2cbe…`, `run-bde99cf…`) |
| Memory 4A writeback | 2026-06-20 | issue #2; review run `run-f32dd48059abccc08338352894b886f3`; `agentctl memory show` |
| Memory 4B retrieval | 2026-06-21 | issue #2; plan run `run-bde99cf06bff485fec153c89a7841150`; `prior_memory_used` + `memory_retrieval` in audit |
| **Review MVP (full + memory loop)** | **2026-06-21** | **issue #4** clean path: review `run-be063cbd2993bb2496bb038233151849` → plan `run-dc0b71ebebb3379b440471e2caa2b9cc`; `prior_memory[0]` = review; `prior_memory_used` cites review run |
| **Slice 5 — structured output boundary** | **2026-06-21** | review `run-19a15588a6bc82d0104ee78006e4febf` → plan `run-d71996d36fca5c54e3f54cc50a4a6f35`; no `parse_failure.json`; pack blast_radius in `plan_result.json` |
| **Slice 6A — Risk 2 approval plumbing** | **2026-06-21** | issue #6 initial (`WI-0006-d4c92e62`, CLI grant); issue #7 retest (`WI-0007-68922c7f`, Gitea `/agent approve` via `GITEA_APPROVER_LOGINS`) |
| **Slice 6B — local patch artifact** | **2026-06-22** | issue #8 fake E2E (`run-025ff111…`, approval consumed); issue #9 official review/plan + `README.md` scope + enqueue (`run-2fc4eff…` official fix parse fail); pytest 6B green; see [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md) |
| **Slice 4C — result ingest** | **2026-07-06** | issue #16; inbox → `.processed` + ledger events for plan/fix runs (`run-87f0892…`, `run-cfdb799a…`, `run-0ef720ec…`); **note:** 2-min cron still active on CT103 — disable to prove Redis-only ingest |
| **Slice 5.2 — plan quality gate** | **2026-07-06** | issue #16 bare plan `run-cca5ddc0…`: "Plan not fixable", no WI block; scoped plan `run-5fc4e1a…`: `Allowed files: README.md` |
| **Slice 5.3 — issue-task backfill** | **2026-07-06** | issue #16 bare `/agent plan` `run-cca5ddc0…`: `natural_language_task` backfilled from issue body on CT104 |
| **Slice 6B+6C — fix E2E (official)** | **2026-07-06** | issue #16; plan `run-5fc4e1a…` / fix `run-cfdb799a…` and plan `run-c482b39…` / fix `run-0ef720ec…`; gate passed, no publish; **caveat:** `patch.diff` empty (0 bytes), `files_changed: (none)` — pipeline green, content weak |
| **Slice 5.1 — engine reliability** | **partial** | Official fix completes without parse fail but empty patch; induced failure path not re-verified on this run |
| **Slice 6D — branch push + PR** | **2026-07-13** | issue #19 fake E2E: plan `run-1b0a7162…` → fix `run-cf4c2b2e…` → branch `agent/run-cf4c2b2e…` → [PR #20](https://git.ham-sup-lo.com/ai-sdlc-lab/agent-control-plane/pulls/20); `main` untouched |
| **Slice 5.2 harden** | **2026-07-13** | Nested `plan_quality`, CT103 fail-closed (empty `allowed_files` / not fixable), per-mutating-step files; see [slice-5.2-plan-quality-gate.md](slice-5.2-plan-quality-gate.md) |
| **Slice 6E.1 / 6E.2 — CI truth** | **2026-07-14** | issue #19 / PR #20 / `run-cf4c2b2e…` @ `ef22f721…`: reconcile → `verdict=verified`; comment `rev1`; memory `ci_verified`; append-only `agent.fix_ci_*`; see [slice-6e-ct102-ci-truth-loop.md](slice-6e-ct102-ci-truth-loop.md) |
| **Slice 6F.1 — CI failure evidence** | **2026-07-16** | PR #20 @ `9b3d83be…`; runs 463/464; `verdict=failing`; evidence obs `562cde10…` / `3256dfc0…` `collected`; ledger `agent.fix_ci_failure_evidence_collected`×2; repair off; follow-ups: comment upsert, agent-runs mount on control-plane, classifier; see [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md) |
| **Slice 5.6a — SRT sandbox spike** | **2026-07-17** | Host 2b/2c + `worker-rlm-root` strong PASS; 2e fail-closed; **2d** env pin CT103+CT104 (`srt` / `5de9f107fc05367e849f893c815efd18` / require attestation); see [slice-5.6a-srt-sandbox-spike.md](slice-5.6a-srt-sandbox-spike.md) |
| **Slice 6F.2 — repair gate demo** | **2026-07-17** | `demo-app` issue #4 / PR #5 @ `4ebaab0…`; runs 481/482; evidence collected; `agent.fix_ci_repair_requested` + `agent.fix_ci_repair_blocked`; see [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md) |
| **Slice 5.8 + 6F.2 — sandboxed repair** | **2026-07-18** | Same PR #5: reservation → CT104 `ci-repair` → SRT verify → non-force push `16886456…`; CT103 pending re-point; Gitea CI green; `main` untouched; ACP `d3d3ea2` + ADR-0003; see [slice-5.8-6f2-sandboxed-repair.md](slice-5.8-6f2-sandboxed-repair.md) |
| **Slice 6D.2 / V4.1.1 — publish brokerage** | **2026-07-19** | Barrier cutover: CT104 write tokens stripped; `publish-broker` sole push/PR; seeded fix `71527138…` + repair FF `c88f1e86…` on `demo-app`; plan/review comments via CT103 ingest; see [slice-6d2-ct103-publish-brokerage.md](slice-6d2-ct103-publish-brokerage.md), ADR-0004 |
| **V4.1.1 closeout (umbrella)** | **2026-07-19** | Trust-boundary PRs + staged ACP repair + demo brokerage E2E + CT102 user split — [slice-v411-closeout.md](slice-v411-closeout.md) |
| **Slice 5.4a — typed sessions** | **2026-07-20** | Fake `/agent review` demo-app#2 → `sess-206dce2b…` finished; mismatch fail-closed — [slice-5.4-typed-sessions.md](slice-5.4-typed-sessions.md), ADR-0010 |
| **Slice 5.4b — failure taxonomy** | **2026-07-20** | demo-app#2 early deny `sess-78ce5694…` / `run-78a9139c…` (`human_approval_required`); late broker deny `sess-ca35c33b…` / `run-54b-late-66b1677f…` (`sandbox_unavailable`); tip `dfb3d22` — [slice-5.4b-session-failure-taxonomy.md](slice-5.4b-session-failure-taxonomy.md) |
| **Slice 5.5a — deterministic preflight** | **2026-07-20** | tip `6f170a4`; Actions 590–592; CT103+CT104 tip pin; `PREPARE_OK` `sess-47b90b22…` — [slice-5.5-deterministic-preflight.md](slice-5.5-deterministic-preflight.md) |
| **Slice 5.6 — verification evidence gate** | **2026-07-20** | tip `8df60fc`; Actions 596–598; CT103+CT104 tip pin; in-container 6/6 gate tests — [slice-5.6-verification-evidence-gate.md](slice-5.6-verification-evidence-gate.md), ADR-0012 |
| **Slice 5.7 — selective writeback** | **2026-07-20** | tip `a7dd4c5`; Actions×3 success; CT103+CT104 tip pin; in-container `test_session_writeback_57.py` 3 passed — [slice-5.7-selective-writeback.md](slice-5.7-selective-writeback.md) |
| **V4.1.2 exit (T03)** | **2026-07-20** | demo-app#2 review `sess-63968c4e…` → plan `sess-57eaa725…`; prior_memory cites review session + `epistemic_status=inferred` — [slice-v412-exit.md](slice-v412-exit.md) |
| **T04 — adequacy profiles** | **2026-07-20** | tip `e5469f7`; Actions×3; CT103+CT104 pin; in-container 6 passed — [slice-t04-adequacy-profile.md](slice-t04-adequacy-profile.md) |
| **T09 — non-demo 6F.2 ACP** | **2026-07-20** | tip `38e01d6`; `agentctl repair stage-status` → `t09_complete=true` — [slice-t09-non-demo-6f2-acp.md](slice-t09-non-demo-6f2-acp.md) |
| **T13 — flag-gated tournaments** | **2026-07-20** | tip `078d030`; spawn/rewards deny-by-default — [slice-t13-patch-tournaments.md](slice-t13-patch-tournaments.md), ADR-0019 |
| **V4 epic remaining track** | **closed** | T01–T11 + T13 Done; T12 Deferred — [handoff/boss-ledger.md](handoff/boss-ledger.md) |
| **V5 governance epic** | **ready** | Next: T01 AgentFacts-lite — [handoff/boss-ledger-v5.md](handoff/boss-ledger-v5.md) |

Dates are UTC as recorded on CT103/CT104 at ingest time.

Update this table when milestones are verified on CT103+CT104.
