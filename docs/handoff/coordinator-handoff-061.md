# Handoff — coordinator-handoff-061

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 061 |
| Date (UTC) | 2026-08-19 |
| Slice / ticket ID | VExp W1-TE treatment-exposure repair |
| Tip SHA (ACP) | `7e51983ac5a3b9fa38a6176da99ff03cdda3ee66` |
| maintenance-evals SHA | `5891c452c53e3b35627a33ddb0aedcc0ea47e895` (local-only) |
| Epic | Verified Experience Control Plane (not V10) |
| `stopped_reason` | `group_boundary_stop` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-061.md
tickets_done: W0 5/5; W1 coded; W1-TE Done
next_ticket_id: evidence-quality diagnostics (not WAVE 2)
blocker: none
stopped_reason: group_boundary_stop
decision: GO_EVIDENCE_ONLY + floor_no_verified_signal
```

## Slice outcome

- Goal completed (one sentence): Pre-invocation treatment artifacts now survive parse/retry failures; repaired 14-slot bakeoff has complete treatment exposure and no verifier lift.
- Slice doc path: `docs/slice-vexp-w1-treatment-exposure-repair.md`
- Deploy verify path / status: `pass` — [deploy-verify-vexp-w1-te-20260819.md](deploy-verify-vexp-w1-te-20260819.md)
- CT103 tip / CT104 tip: both `7e51983ac5a3b9fa38a6176da99ff03cdda3ee66`

## Evidence pointers (paths / IDs only)

- Gitea: `https://git.ham-sup-lo.com/ai-sdlc-lab/agent-control-plane/commit/7e51983ac5a3b9fa38a6176da99ff03cdda3ee66`
- Actions (tip `7e51983`): test 931/932/933 success; deploy 934/935 success; runs 940/941/942 success
- Repair code commit: `f367bf05a23d90d58a6614a0f0f2deeb4483ce2d`
- Frozen STOP_REPAIR: `maintenance-evals/results/vexp-w1-context-v2-dev-v1`
- Repaired result: `maintenance-evals/results/vexp-w1-context-v2-dev-v2-treatment-repair`
- Slot 14 repaired session: `sess-eval-b963f329665042f3906eb14e37c764f6`
- ADR: ADR-0039 (proposed)

## Decisions the next coordinator must honor

1. Production default stays `CONTEXT_MODE=baseline_v1`. This freeze does not flip it.
2. Do not start WAVE 2. Treatment exposure is complete, but verified_success is 0/14 across A/B0/B1.
3. Do not claim ContextPack V2 improves maintenance. Verifier outcomes do not discriminate arms.
4. Do not mutate `results/vexp-w1-context-v2-dev-v1` or frozen V10 artifacts.
5. Next work is evidence-quality diagnostics on the repaired result set, then a separate decision whether verify-to-repair is justified.

## Next coordinator: first actions

1. Read `results/vexp-w1-context-v2-dev-v2-treatment-repair/DECISION.md` and `comparison-with-stop-repair-v1.json`.
2. Inspect provider statuses / selected counts (slot 14 lexical was `unavailable`; selected class was mostly `dependency_edges`).
3. Do not open WAVE 2 from this handoff.

## Open risks (one line each)

- Lexical `unavailable` on some V2 slots may mean B1 is not delivering the intended lexical evidence even when hashes exist.
- Official bakeoff used local ACP checkout; freeze.json `acp_runtime_sha` is `f367bf0` (preflight) while later sessions recorded live git HEAD `7e51983` (ruff-exclude only).
