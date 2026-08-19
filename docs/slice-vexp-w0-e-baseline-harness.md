# Slice: VExp W0-E — Baseline preservation harness

**Status:** implemented (evals-only; does not rewrite frozen artifacts)
**Epic:** Verified Experience Control Plane (W0-E)
**Hard gate:** golden V1 compatibility comparison must execute; SKIP only when the ACP adapter is missing AND `VEXP_W0_ALLOW_COMPAT_SKIP=1`

## Goal

Executable proof that Wave 0 contracts did not change today's treatment on a defined hash surface (rendered solver context, prompt identity, H1 arms, verification command lists, model pins, starting SHA, frozen manifests, scored policy).

## Read first

- `EPIC_verified_experience_control_plane.md` W0-E / §20
- plan W0-E: treatment-equivalence surface
- `maintenance-evals/tests/test_contracts.py`
- ACP `src/agent_control/context/v1_adapter.py`
- ACP `src/agent_control/graph/context_pack.py` (`render_context_pack_text`)

## Allowed touch area

- `maintenance-evals/tests/test_w0_baseline_preservation.py`
- `maintenance-evals/src/maintenance_evals/w0_compat.py` (skip policy only)
- this slice doc

## Avoid touching

- frozen experiment manifests, reserved split data, scored flags
- `verifier-bindings.yaml` command text
- ACP solver path (`official_engine`, `eval_arm_context`, `graph/context_pack.py`, `prompts.py`)
- experience verification schema files (`experience_verification_result.v1.json`, `DIGESTS.md`, `test_experience_verification_schema.py`)

## Inputs / contracts

- `v1_to_v2` / `render_v1_compatible` live in `agent_control.context.v1_adapter`
- `prior_memory` maps to `experience.compatibility.legacy_prior_memory`; `authorized_records` stays empty
- `RepoSnapshot` is identity/provenance, not part of the treatment hash
- W0 emits nothing with `scored=true`

## Deliverables

- baseline harness test hashing the treatment surface
- skip-policy helper (default: execute)
- this slice doc

## Acceptance tests

1. SHA-256 of `render_context_pack_text(v1)` equals SHA-256 of `render_v1_compatible(v1_to_v2(v1))` and the pinned golden.
2. Adapter missing without `VEXP_W0_ALLOW_COMPAT_SKIP=1` fails (does not skip).
3. Five `experiment_manifest.v1` remain `status: frozen`; execution seed `20260815`; primary model `qwen2.5-coder:14b` / `Q4_K_M`.
4. Fixture `starting_sha` values are 40-hex; official vs additional command lists hash independently.
5. Loading manifests, splits, and bindings does not rewrite those files.

## Invariants

- CT102 remains authoritative (unchanged this slice)
- exact-SHA isolation (`GitWorkspaceProvider` still compares `HEAD` to `starting_sha`)
- no future-leak
- reserved splits untouched
- no scored experiment declared from W0
- no model-visible rewrite of v1 solver prompts

## Handoff

- Test command: `pytest tests/test_w0_baseline_preservation.py -q` from `maintenance-evals`
- Known gaps: prompt / `H1_ARMS` pins are import-gated; ACP tests remain the owners of `prompts.py` identity
- Merge conflicts likely: none expected on frozen manifests
