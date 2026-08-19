# Slice: VExp W0-A RepoSnapshot

**Status:** implemented (additive; not wired into the v1 solver path)
**Epic:** Verified Experience Control Plane (W0-A)
**Hard gate:** snapshot identity is `repository_id` + `target_sha` only

## Goal

Freeze a read-only exact-SHA `RepoSnapshot` type that production (Gitea
`RefResolution.target_sha`) and eval (workspace `git rev-parse HEAD`) can both
construct, without changing solver-visible context.

## Allowed touch area

- `src/agent_shared/models/repo_snapshot.py`
- `src/agent_control/context/__init__.py` (package marker only)
- `src/agent_control/context/repo_snapshot.py`
- `tests/test_repo_snapshot.py`
- this slice doc

## Avoid touching

- `graph/snapshot.py`, `eval_arm_context.py`, `graph/context_pack.py`
- `official_engine.py`, `prompts.py`, `models/__init__.py`
- `protocols/`, `v1_adapter.py`, `context_pack_v2.py`
- experience verification / telemetry modules
- solver wiring, git commit, deploy

## Inputs / contracts

- Identity: `snapshot_id = hex digest of (repository_id, target_sha)` via
  `canonical_json_hash`. `workspace_path` and `index_generation` are provenance,
  not identity.
- `from_production(project, refs, workspace_path, ...)` fails if
  `refs.target_sha` is missing. Does not read git or import eval packages.
- `from_eval(repository_id, target_sha, workspace_path, ...)` fails closed when
  `HEAD != target_sha`. Does not resolve the requested SHA as a ref (no
  future-commit walk).

## Deliverables

- Frozen Pydantic `RepoSnapshot`
- Production and eval adapters
- Unit tests in `tests/test_repo_snapshot.py`

## Acceptance tests

1. Same repo+SHA => same `snapshot_id`; different SHA or repository_id => different.
2. Different `workspace_path` or `index_generation` => same `snapshot_id`.
3. Eval adapter raises on HEAD mismatch.
4. Production adapter module source contains no eval-harness package import.
5. Constructing a snapshot does not call `compile_context_pack`.

## Invariants

- Exact-SHA isolation; no future-leak through the snapshot contract
- Snapshots are frozen (no public mutators)
- v1 solver path unchanged (no dispatch / engine wiring)

## Handoff

- Test command: `pytest tests/test_repo_snapshot.py -q`
- Not re-exported from `agent_shared.models` or `agent_control.context` (integration owner)
- Merge conflicts likely only on `src/agent_control/context/__init__.py` if other W0 slices land the package marker first
