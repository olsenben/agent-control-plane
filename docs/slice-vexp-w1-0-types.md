# Slice: VExp W1-0 — Query / budget / result types

**Status:** implemented (types only; providers and builder not wired)
**Epic:** Verified Experience Control Plane (WAVE 1)
**Hard gate:** `rg_unavailable` / `language_unsupported` are `ProviderResult` status/diagnostics, never `EvidenceItem` fields or `current_evidence`
**ADR:** proposed by integration owner (do not append to V10 ledger)

## Goal

Freeze W1 query, budget, and result types and tighten `RepositoryEvidenceProvider` / `ContextBuilderV2` so lexical, symbol, graph, and builder slices can land in parallel against a typed seam.

## Read first

- `EPIC_verified_experience_control_plane.md` WAVE 1 / §14
- plan frozen contracts: exact-SHA workspace (W1-F) and discriminated v1/v2 job transport
- `src/agent_shared/models/context_pack_v2.py` (`EvidenceItem` is additive `id` only)
- `src/agent_shared/protocols/context.py`

## Allowed touch area

- `src/agent_shared/models/evidence_query.py`
- `src/agent_shared/models/context_pack_v2.py` (`EvidenceItem.id` default `""` only)
- `src/agent_shared/protocols/context.py`
- `src/agent_shared/protocols/__init__.py`
- `tests/test_evidence_query.py`
- `tests/test_context_pack_v2.py` (only if W0 constructions needed a default)
- `src/agent_control/context/v1_adapter.py` (only if `EvidenceItem` construction needed an id helper; unused)
- `tests/fixtures/vexp_mini_repo/`
- this slice doc

## Avoid touching

- `eval_arm_context.py`, `eval_dispatch.py`, `official_engine.py`, `fake_engine.py`
- `graph/context_pack.py`, `graph/snapshot.py`, `graph/store.py`
- `publish/`, `ci/`, `prompts.py`
- maintenance-evals frozen manifests, `boss-ledger-v10.md`
- retriever, applicability, repair, episode, or `state_predicate` Protocols

## Inputs / contracts

- `EvidenceClass` is a closed Literal. `EvidenceBudget.max_items_by_class` uses those keys, not `dict[str, int]`. Unknown keys (including `"dependancy"`) are rejected.
- Budget invariants: all limits `>= 0`; `max_chars_total > 0`; `max_snippet_chars <= max_chars_total`.
- `RepositoryEvidenceProvider.query` returns `ProviderResult`, not a list.
- `ContextBuilderV2.build` returns `ContextBuildResult` (`context_pack` + `build_trace`), not `ContextPackV2` alone, and implies no telemetry I/O.
- `EvidenceItem.id` defaults to `""` so W0 `v1_to_v2` constructions stay valid. Canonical ids come from `compute_evidence_item_id(snapshot_id, provider, evidence_type, path_or_node, normalized_fact)` via `canonical_json_hash`.
- `v1_to_v2` still leaves `authorized_records` empty. Render bytes are unchanged (id is not model-visible in `render_v2` / `render_v1_compatible`).

## Deliverables

- implementation: typed query/budget/result models + tightened Protocols
- unit tests: `tests/test_evidence_query.py`
- fixtures: `tests/fixtures/vexp_mini_repo/` (source-only; no git metadata)
- telemetry: none this slice (trace shape frozen for W1-D / W1-E)
- migration note: additive; production solver contract remains v1

## Acceptance tests

1. Serialization round-trip for query, budget, provider result, and build result.
2. Budget invariants reject non-positive totals, negative caps, and `max_snippet_chars > max_chars_total`.
3. Unknown class key `"dependancy"` is rejected.
4. `ProviderResult` diagnostics (`rg_unavailable`, `language_unsupported`) are not `EvidenceItem`s and do not appear in `evidence`.
5. Protocol signatures importable: `query -> ProviderResult`, `build -> ContextBuildResult`.
6. W0 `tests/test_context_pack_v2.py` and W0-E golden still pass.

## Invariants

- CT102 remains authoritative (unchanged this slice)
- exact-SHA isolation (snapshot identity unchanged)
- diagnostics never become model-visible evidence
- builder protocol is pure (no emit in the signature)
- `authorized_records` empty on the W0 adapter path
- no `state_predicate` Protocol

## Handoff

Report:

- files changed: listed under Allowed touch area
- interfaces implemented: `EvidenceQuery`, `EvidenceBudget`, `ProviderResult`, `ContextBuildTrace`, `ContextBuildResult`, `ContextTaskSpec`, `compute_evidence_item_id`
- test command: `pytest tests/test_evidence_query.py tests/test_context_pack_v2.py -q`
- known gaps: no provider implementations; `ContextBuilderV2` remains Protocol-only until W1-D
- merge conflicts likely: `src/agent_shared/protocols/context.py` (this slice owns it)
