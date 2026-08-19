# Slice: VExp W1-E — eval-path ContextPack V2

**Status:** implemented (discriminated job transport; baseline_v1 unchanged)
**Epic:** Verified Experience Control Plane (WAVE 1)
**Hard gate:** `baseline_v1` still compiles a v1 pack via `apply_arm_context`; `context_v2*` puts `schema_version=context-pack.v2` on the job; the engine renders by schema_version
**ADR:** [ADR-0038](adr/0038-vexp-w1-discriminated-context-pack.md) (proposed)

## Goal

Wire ContextPack V2 onto the eval solver path as a discriminated job payload.
The official and fake engines own rendering. Memory, recursion, 2070, and
repair stay off. Frozen H1 arms are not replaced.

## Read first

- plan Phase 2 frozen contracts (discriminated union; exact-SHA eval workspace)
- `src/agent_control/context/builder.py` (pure; no telemetry)
- `src/agent_control/context/v2_dispatch.py`
- `docs/adr/0037-vexp-w0-additive-contracts.md`

## Allowed touch area

- `src/agent_control/eval_arm_context.py` (add `context_mode` path; keep H1 arms)
- `src/agent_control/eval_dispatch.py`
- `src/agent_workers/rlm/official_engine.py`
- `src/agent_workers/rlm/fake_engine.py`
- `src/agent_control/context/v2_dispatch.py`
- `tests/test_eval_context_mode.py`
- `tests/test_eval_dispatch.py`
- `tests/test_official_engine.py`
- this slice doc

## Avoid touching

- `context/builder.py` internals (inject providers via constructor)
- `context/providers/*.py`, `indexes/`, `workspace.py` (eval does not re-clone)
- `evidence_query.py`, `protocols/context.py`, frozen V10 manifests
- `boss-ledger-v10.md`, `graph/snapshot.py`

## Inputs / contracts

- Job `context_pack` is a discriminated union:
  - `schema_version=context_pack.v1` -> `render_context_pack_text`
  - `schema_version=context-pack.v2` -> `render_v2`
  Do not pre-render V2 to opaque text on the job.
- `context_mode`:
  - `baseline_v1`: existing `apply_arm_context` / local-deterministic + v1 pack
  - `context_v2_lexical`: lexical provider only -> V2 pack
  - `context_v2`: lexical + symbol + graph providers -> V2 pack
- Eval uses `from_eval` on the existing exact-SHA workspace. No re-clone.
- `emit_experience_event("context.candidate_evidence" / "context.evidence_selected")`
  after `build`, payload from `build_trace` only (no prompt bodies).
- Treatment fields on eval session telemetry: `repo_snapshot_id`, `target_sha`,
  `context_pack_version`, `context_pack_hash`, `rendered_context_hash`,
  `evidence_provider_ids`, `selected_evidence_ids`.
- A V2 pack with a v1-only prompt is a failed gate, not a silent fallback.
- `repair_attempts` stay 0. No recursion. No 2070. `authorized_records` empty.

## Deliverables

- Discriminated engine render path
- `context_mode` on eval dispatch without replacing H1 arms
- Treatment hashes + context.* events from `build_trace`
- Tests: `tests/test_eval_context_mode.py` plus extensions
- this slice doc

## Acceptance tests

1. Official and fake engines render by `schema_version`.
2. `baseline_v1` still produces `context_pack.v1` (W0-E golden path unchanged).
3. `context_v2` / `context_v2_lexical` put a V2 pack on the job.
4. Treatment hashes recorded; persisted user prompt contains `render_v2` bytes.
5. H1 arm tests still pass. Fake engine path used so no GPU.

## Invariants

- CT102 remains authoritative
- exact-SHA isolation; eval does not re-clone
- diagnostics never become model-visible evidence
- builder is pure; telemetry is integration-owned
- `authorized_records` empty
- frozen V10 manifests not rewritten

## Handoff

- Test command: `pytest tests/test_eval_context_mode.py tests/test_eval_dispatch.py tests/test_eval_arm_context.py tests/test_official_engine.py tests/test_context_pack_v2.py -q`
- Next: Phase 3 CT103/CT104 deploy verify (out of this slice)
