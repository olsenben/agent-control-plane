# Slice T04 — Scoped Verification Claims + Adequacy Profile

**Status:** Implemented — deploy verify pending  
**Date:** 2026-07-20  
**Epic ticket:** T04  
**Plan:** V4 §0.5 verification invariant + impl order item 7  
**Builds on:** [slice-5.6-verification-evidence-gate.md](slice-5.6-verification-evidence-gate.md)  
**ADR:** [0014-adequacy-profiles-scoped-verification.md](adr/0014-adequacy-profiles-scoped-verification.md)

## Goal

Make verification claims explicitly scoped. `fixed_verified` means the configured adequacy profile passed on the exact commit — never universal correctness. Agent-authored tests are `scoped_only` for Risk 2 unless independently attested.

## Locked policy

| Profile | Commands | `fixed_verified` |
|---------|----------|------------------|
| `risk0_read_only` | inspect, explain | never |
| `risk1_hypothesis` | review, plan | never (`verification_missing`) |
| `risk2_fix_ci` | fix, repair | only when required CI checks pass **and** agent-authored tests are attested (or N/A) |

Default CT102 aggregate path (unknown agent-test execution) → outcome `ci_regression_passed`, `fixed_verified=false`, limitations cite scoped agent-test claims.

## Artifacts

| Artifact | Path |
|----------|------|
| Profiles | `config/adequacy_profiles.yaml` |
| Claim fields | `adequacy_profile_id`, `adequacy_status`, `adequacy_outcome`, `adequacy_checks`, `fixed_verified`, `scope_files`, `scope_behavior` |

## Enforcement

- `emit_ingest_verification_missing` / `request_session_verification` / `apply_ci_verdict_to_session` stamp adequacy via `_apply_adequacy_to_claim`
- CI status comments include adequacy block
- `agentctl session show --json` exposes adequacy summary

## Tests

`tests/test_adequacy_t04.py`

## Deploy verification

_(fill after tip lands)_

## Follow-on

- Wire patch `test_*.py` paths into `agent_test_paths` when available
- T05 Orbit graph edges
