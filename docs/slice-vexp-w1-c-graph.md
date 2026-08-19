# Slice: VExp W1-C — Dependency / test / config graph provider

**Status:** implemented (provider only; builder and dispatch not wired)
**Epic:** Verified Experience Control Plane (WAVE 1)
**Hard gate:** Graph SQLite is never trusted across SHA mismatch; `query` returns `ProviderResult` (failures are status, never `EvidenceItem`s)
**ADR:** proposed by integration owner (do not append to V10 ledger)

## Goal

Answer what is structurally around a task at an exact SHA: import/dependency neighbors, tests that cover mentioned files, and config/build envelope. Memory, recursion, 2070, and repair stay off. `state_predicate` is not implemented this wave.

## Read first

- `EPIC_verified_experience_control_plane.md` W1-C
- `src/agent_shared/models/evidence_query.py` (`EvidenceQuery.query_text` / `mentioned_paths`, `ProviderResult`)
- `src/agent_control/graph/store.py`, `schema.py`, `blast_radius.py`
- extractors: `python_imports.py`, `sdlc_evidence.extract_test_covers_edges`, `packages.py`
- fixture: `tests/fixtures/vexp_mini_repo/` (`bar` imports `foo`; `tests/test_foo.py` covers `foo`)

## Allowed touch area

- `src/agent_control/context/providers/graph.py`
- `tests/test_graph_provider.py`
- this slice doc

## Avoid touching

- `providers/__init__.py`, `lexical.py`, `symbols.py`, `builder.py`, `workspace.py`
- `graph/snapshot.py`, `eval_dispatch.py`, `protocols/`, `evidence_query.py`, `mcp/queries.py`
- retriever, applicability, repair, episode, or `state_predicate` Protocols

## Inputs / contracts

- Required API this wave: `neighbors(node_id, edge_types, depth)`, `affected_tests(node_ids)`, `dependency_envelope(node_ids)`.
- `GraphProvider.query(snapshot, request) -> ProviderResult`.
- Recheck `git rev-parse HEAD == snapshot.target_sha` at query entry. Mismatch: `status=error`, `evidence=[]`, do not read `GraphStore`.
- Default graph is ephemeral from `snapshot.workspace_path` using existing extractors. Do not mutate a shared CT103 DB.
- `GraphStore` is used only when `repos.source_sha == snapshot.target_sha` after the HEAD check.
- Evidence ids via `compute_evidence_item_id`. Sources: `graph.import`, `graph.test_covers`, `graph.config`.
- Provider failures stay on `ProviderResult.status` / `diagnostics`.

## Deliverables

- `GraphProvider` with neighbors / affected_tests / dependency_envelope plus `query`
- unit tests on a git-init copy of `vexp_mini_repo`
- this slice doc

## Acceptance tests

1. `query` returns `ProviderResult` with dependency and/or test evidence; every item has a canonical `id`.
2. `affected_tests(["src/pkg/foo.py"])` is non-empty and includes `tests/test_foo.py`.
3. `bar.py` import or test neighborhood reaches `foo` (import or `test_covers` edges exist).
4. HEAD / `target_sha` mismatch: `status=error`, empty evidence, planted `GraphStore` is not read.
5. Store `source_sha` != workspace HEAD: ephemeral graph is used; planted stale edges are not emitted.
6. `GraphProvider` has no `state_predicate`.

## Invariants

- Exact-SHA isolation; Graph SQLite is never trusted across SHA mismatch
- No default `GraphStore(settings.graph_db_path)` (CT103 DB stays untouched)
- Diagnostics never become model-visible evidence
- No `state_predicate` this wave
- Memory / recursion / 2070 / repair remain off

## Handoff

- Import: `from agent_control.context.providers.graph import GraphProvider`
- Test command: `pytest tests/test_graph_provider.py -q`
- Known gaps: not wired into `ContextBuilderV2`; architecture/ADR class not emitted here; `state_predicate` deferred
- Merge conflicts likely: none expected (`providers/graph.py` is new)
