# Slice: VExp W0-B — ContextPackV2 + V1 compatibility bridge

**Status:** implemented (awaiting integration merge)
**Epic:** Verified Experience Control Plane (W0-B)
**Hard gate:** `authorized_records` stays empty in V1 compat; do not treat `prior_memory` as authorized
**ADR:** proposed by integration owner (do not append to V10 ledger)

## Goal

Add `ContextPackV2` (`schema_version: context-pack.v2`) and an explicit V1 adapter so Wave 0 does not change today's solver-visible treatment. V1 `ContextPack` remains the solver contract.

## Read first

- `EPIC_verified_experience_control_plane.md` W0-B / §14 / §20
- `src/agent_shared/models/context_pack.py` (do not mutate fields)
- `src/agent_control/graph/context_pack.py` (`compile_context_pack`, `render_context_pack_text`, `TOTAL_BUDGET=24000`)
- `src/agent_control/eval_arm_context.py` (minimal eval v1 packs)

## Allowed touch area

- `src/agent_shared/models/context_pack_v2.py`
- `src/agent_control/context/v1_adapter.py`
- `src/agent_shared/protocols/__init__.py`
- `src/agent_shared/protocols/context.py` (`RepositoryEvidenceProvider`, `ContextBuilderV2` only)
- `tests/test_context_pack_v2.py`
- this slice doc

## Avoid touching

- `official_engine.py`, `prompts.py`, `eval_arm_context.py`, `graph/context_pack.py`
- `models/context_pack.py` fields, `models/__init__.py`
- `agent_control/context/__init__.py` (Agent A)
- experience verification / telemetry taxonomy
- W3–W6 Protocols (retriever, applicability, repair, episode)

## Inputs / contracts

- V1 `ContextPack.prior_memory` is ungated model-visible history.
- Mapping `prior_memory` -> `authorized_records` is forbidden (would imply a safety decision that never occurred).
- Adapter mapping: `search_hits` -> `current_evidence.lexical`; `prior_memory` -> `experience.compatibility.legacy_prior_memory`; `authorized_records = []`; `rejected_records = []`.
- `render_v1_compatible` reconstructs an equivalent `ContextPack` (private `v1_compat` payload) and calls `render_context_pack_text`. Compat path re-applies `TOTAL_BUDGET` clamp.
- `render_v2` may show `authorized_records` and must omit `legacy_prior_memory`. `rejected_records` never appear in either renderer.

## Deliverables

- implementation: V2 schema + adapter + W1-seam Protocols
- unit tests: `tests/test_context_pack_v2.py`
- fixtures: constructed eval-like v1 pack; `compile_context_pack` via `graph_settings`
- telemetry: none this slice
- migration note: additive only; jobs still carry v1 `ContextPack`

## Acceptance tests

1. Round-trip `model_dump(mode="json")` / `model_validate` is stable.
2. `v1_to_v2` leaves `authorized_records` empty even when `prior_memory` is non-empty.
3. `render_v2` does not contain the legacy prior_memory payload.
4. Rejected records are absent from both renderers.
5. Golden: eval-like constructed pack and `compile_context_pack` -> `v1_to_v2` -> `render_v1_compatible == render_context_pack_text`.
6. Compat renderer drops `search_hits` when reconstructed v1 sections exceed `TOTAL_BUDGET`.

## Invariants

- CT102 remains authoritative (unchanged this slice)
- exact-SHA isolation (RepoSnapshot is identity, not rewritten here)
- no future-leak
- deterministic fallback: v1 renderer remains the solver contract
- no model-visible rejected memory
- `authorized_records` empty until a real authorization decision exists

## Handoff

Report:

- files changed: listed under Allowed touch area
- interfaces implemented: `ContextPackV2`, `v1_to_v2`, `render_v1_compatible`, `render_v2`, `RepositoryEvidenceProvider`, `ContextBuilderV2`
- test command: `tests/test_context_pack_v2.py`
- known gaps: `ContextBuilderV2` / `RepositoryEvidenceProvider` are Protocol-only (W1 implements); V2 is not wired into `official_engine.py` or `apply_arm_context`
- merge conflicts likely: `src/agent_control/context/` (Agent A owns `__init__.py` and snapshot adapters)
