# Slice: VExp W1-D — ContextBuilderV2

**Status:** implemented (pure builder against injected providers; not wired into dispatch)
**Epic:** Verified Experience Control Plane (WAVE 1)
**Hard gate:** same inputs => same pack hash + same `build_trace`; unavailable provider diagnostics never enter `current_evidence` or `render_v2`; `authorized_records` empty
**ADR:** proposed by integration owner (do not append to V10 ledger)

## Goal

Land a pure `ContextBuilderV2` that returns `ContextBuildResult` (pack + trace)
against constructor-injected lexical/symbol/graph providers. Memory, recursion,
2070, and repair stay off. Production default remains v1.

## Read first

- `EPIC_verified_experience_control_plane.md` W1-D
- `src/agent_shared/protocols/context.py`
- `src/agent_shared/models/evidence_query.py`
- `src/agent_shared/models/context_pack_v2.py`
- `src/agent_control/context/v1_adapter.py` (`render_v2` omits `legacy_prior_memory`)
- `src/agent_control/context/repo_snapshot.py`

## Allowed touch area

- `src/agent_control/context/builder.py`
- `tests/test_context_builder_v2.py`
- this slice doc

## Avoid touching

- `context/providers/*.py` (real providers are other agents; tests use fakes)
- `workspace.py`, `eval_dispatch.py`, `official_engine.py`
- `telemetry/taxonomy.py` (do not call `emit_experience_event`)
- `graph/context_pack.py`, `protocols/context.py`, `evidence_query.py`
- `v1_adapter.py` (read-only; `render_v2` must keep omitting `legacy_prior_memory`)

## Inputs / contracts

- `ContextBuilder.build(snapshot, task, evidence_budget, authorized_experience=())`
  returns `ContextBuildResult`. No telemetry I/O inside `build`.
- Entry rechecks `HEAD == target_sha`. Missing `workspace_path` fails closed
  (empty pack + `build_trace.provider_statuses["exact_sha"] = "error"`), no crash.
  Git workspaces use `git rev-parse HEAD`. Tests use `from_eval` or monkeypatch
  `recheck_exact_sha`.
- Providers are injected (`lexical` / `symbol` / `graph` callables or Protocol
  objects). This module does not import W1-A/B/C provider implementations.
- Query/selection order: (1) task literals / `failure_signature` (2) lexical
  (3) mentioned files/symbols (4) symbol neighbors (5) dependency/test
  neighborhood (6) config (7) architecture/ADR (8) authorized experience —
  always empty this wave even if a sequence is passed.
- Only `ProviderResult.evidence` with `status == "ok"` fills `current_evidence`.
  `unavailable` / `unsupported` / `error` contribute to
  `build_trace.provider_statuses` only.
- Budget clamps per class via `max_items_by_class`, `max_chars_total`, and
  `max_snippet_chars`. Drops are recorded on the trace (`dropped_by_budget`,
  `chars_by_class`, `total_chars`).
- No recursive worker.

## Deliverables

- implementation: `agent_control.context.builder.ContextBuilder`
- unit tests: `tests/test_context_builder_v2.py`
- this slice doc
- telemetry: none (trace only; integration owns emit)
- migration note: additive; production solver contract remains v1

## Acceptance tests

1. `build` returns `ContextBuildResult` with pack + `build_trace`.
2. Same snapshot/task/budget/providers => same `context_pack.model_dump` hash
   and same trace.
3. Fake unavailable lexical (`rg_unavailable` diagnostic) does not appear in
   `render_v2`.
4. Per-class item/char budget drops are counted on the trace.
5. `experience.authorized_records == []` even when `authorized_experience` is
   passed.
6. Missing workspace and HEAD mismatch fail closed with an empty pack.

## Invariants

- CT102 remains authoritative (unchanged this slice)
- exact-SHA isolation at builder entry
- diagnostics never become model-visible evidence
- builder is pure (no `emit_experience_event`)
- `authorized_records` empty
- no recursive worker

## Handoff

Report:

- files changed: listed under Allowed touch area
- interfaces implemented: `ContextBuilder` (`ContextBuilderV2.build` -> `ContextBuildResult`)
- test command: `pytest tests/test_context_builder_v2.py -q`
- known gaps: real W1-A/B/C providers not wired; production/eval dispatch still v1
- merge conflicts likely: none expected (new files)
