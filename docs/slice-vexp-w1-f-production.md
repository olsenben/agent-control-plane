# Slice: VExp W1-F — production V2 canary (default remains v1)

**Status:** implemented (factory + flag; live Gitea dispatch stays `compile_context_pack`)
**Epic:** Verified Experience Control Plane (WAVE 1)
**Hard gate:** production default is `baseline_v1` / `compile_context_pack`; V2 materializes a detached SHA workspace then `from_production`; never the graph branch-tip cache
**ADR:** [ADR-0038](adr/0038-vexp-w1-discriminated-context-pack.md) (proposed)

## Goal

Own the production V2 factory: materialize exact-SHA workspace, construct the
same `ContextBuilder` class as eval, put a structured V2 pack on the canary
path. Do not silently flip live Gitea dispatch.

## Read first

- plan frozen contract #1 (exact-SHA production workspace)
- `src/agent_control/context/workspace.py` (`materialize_exact_sha_workspace`)
- `src/agent_control/context/v2_dispatch.py`
- `src/agent_control/session/prepare_dispatch.py`

## Allowed touch area

- `src/agent_control/context/v2_dispatch.py` (`from_production`)
- `src/agent_control/session/prepare_dispatch.py` (default remains v1)
- `src/agent_control/config.py` (`CONTEXT_MODE`, default `baseline_v1`)
- `tests/test_eval_context_mode.py` (production default + factory tests)
- this slice doc

## Avoid touching

- `graph/snapshot.py` (branch-tip cache is not the V2 evidence workspace)
- `workspace.py` internals (call `materialize_exact_sha_workspace` only)
- `builder.py` internals, `providers/*.py`, `indexes/`
- live Gitea enqueue to attach V2 onto typed `RLMJob.context_pack` (still v1)

## Inputs / contracts

- Production V2: `materialize_exact_sha_workspace` then snapshot `from_production`
  then `ContextBuilder.build`. Providers never checkout.
- `GraphProvider()` is constructed without a `GraphStore`, so evidence is
  ephemeral from the detached workspace, not CT103 branch-tip SQLite.
- Default `Settings.context_mode` / `CONTEXT_MODE` is `baseline_v1`.
- Typed `RLMJob.context_pack` remains `ContextPack`. If `CONTEXT_MODE` is a V2
  value, `prepare_typed_rlm_dispatch` fails closed rather than compile v1 while
  claiming V2. The canary factory is `v2_dispatch.from_production`.
- Eval and production instantiate the same `ContextBuilder` class.

## Deliverables

- Production V2 factory
- Unit test: production default still compiles v1
- Unit test: factory materializes detached SHA then builds
- this slice doc

## Acceptance tests

1. `Settings(_env_file=None).context_mode == baseline_v1`.
2. `prepare_typed_rlm_dispatch` still calls `compile_context_pack` on that default.
3. `from_production` workspace HEAD equals requested SHA, not origin tip; HEAD is detached.
4. Factory module does not import `graph.snapshot`.

## Invariants

- Production default remains v1 until an explicit follow-up
- Exact-SHA isolation; no silent main/tip fallback
- Same builder class as eval
- No `maintenance_evals` import

## Handoff

- Test command: `pytest tests/test_eval_context_mode.py tests/test_context_workspace.py -q`
- Import: `from agent_control.context.v2_dispatch import from_production`
- Next: widen typed `RLMJob.context_pack` if a live canary must enqueue V2
