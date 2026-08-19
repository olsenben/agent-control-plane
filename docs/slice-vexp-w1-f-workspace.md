# Slice: VExp W1-F exact-SHA workspace materializer

**Status:** implemented (adapter only; production V2 dispatch not wired this slice)
**Epic:** Verified Experience Control Plane (W1-F)
**Hard gate:** production V2 evidence workspace HEAD equals requested SHA; never a mutable branch tip

## Goal

Own production exact-SHA workspace materialization so ContextPack V2 dispatch
never reads a mutable branch-tip checkout. Providers query a path whose
`git rev-parse HEAD` already equals `RefResolution.target_sha`.

## Allowed touch area

- `src/agent_control/context/workspace.py`
- `tests/test_context_workspace.py`
- this slice doc

## Avoid touching

- `context/__init__.py` (W0 package marker; import workspace by module path)
- `protocols/`, `context_pack_v2.py`, `evidence_query.py`, `eval_dispatch.py`
- `official_engine.py`, `graph/snapshot.py`, `graph/store.py`
- `eval_arm_context.py`, `v1_adapter.py`, `maintenance-evals`, `boss-ledger-v10.md`

## Inputs / contracts

- `materialize_exact_sha_workspace(repo_url=..., target_sha=..., dest=...)`
  returns a `Path` for `from_production(..., workspace_path)`.
- Clone, fetch exact SHA, `git checkout --detach`; then require
  `HEAD == requested SHA` and a non-branch HEAD.
- Missing or unfetchable SHA raises `ExactShaWorkspaceError` (no main / tip fallback).
- Failed materialization must not leave a branch-tip checkout at `dest`.
- This module is the only production V2 git clone/fetch/checkout owner.
  Public API does not expose checkout/clone/fetch to providers.
- Credentials/scrub are optional and no-op for local `file://` repos.
- Does not construct `RepoSnapshot`. Does not reuse `_sync_cached_repo`.

## Deliverables

- Exact-SHA detached workspace adapter
- Unit tests with a local `file://` origin
- this slice doc

## Acceptance tests

1. Two-commit origin; request first SHA; workspace HEAD equals first SHA, not tip.
2. After materialize, a new commit on origin `main` does not change detached HEAD.
3. Unfetchable SHA raises `ExactShaWorkspaceError`; `dest` is not left as a checkout.
4. Empty `target_sha` fails closed before clone.
5. Public module API is materialize + error only (no provider git-checkout API).

## Invariants

- Exact-SHA isolation; no silent branch-tip fallback
- Detached HEAD (not a fast-forwardable branch)
- No `maintenance_evals` import
- No coupling to `publish.validate.ValidationError`
- Graph snapshot cache is not the V2 evidence workspace

## Handoff

- Test command: `pytest tests/test_context_workspace.py -q`
- Import: `from agent_control.context.workspace import materialize_exact_sha_workspace`
- Next: production V2 dispatch calls this adapter before `from_production`
