---
id: ADR-0038
title: Expose ContextPack V2 as an optional solver contract via schema_version and context_mode
status: proposed
date: 2026-08-18
owners:
  - platform
scope:
  globs:
    - "src/agent_workers/rlm/official_engine.py"
    - "src/agent_workers/rlm/fake_engine.py"
    - "src/agent_control/eval_dispatch.py"
    - "src/agent_control/eval_arm_context.py"
    - "src/agent_control/context/v2_dispatch.py"
    - "src/agent_control/session/prepare_dispatch.py"
    - "src/agent_control/config.py"
  symbols:
    - context_mode
    - render_job_context_pack
    - ContextBuilder
    - from_eval
    - from_production
decision_type: architecture
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-11-18
agent_visibility:
  - review
  - developer
---

# Context

ADR-0037 kept ContextPack V2 additive and left the live solver contract on v1.
WAVE 1 needs the same task, SHA, model, patch policy, and verifier while only
the repository evidence supplied to the solver changes. Pre-rendering V2 to
opaque text on the job would break provenance. Putting V2 on typed `RLMJob`
without a flag would silently flip production. Frozen H1 arms must keep
working. The graph snapshot cache is a mutable branch-tip checkout and is not
an evidence workspace.

# Decision

The RLM job carries a discriminated `context_pack` union. The engine owns
rendering:

- `schema_version=context_pack.v1` -> `render_context_pack_text`
- `schema_version=context-pack.v2` -> `render_v2`

Do not coerce a V2 dump into `ContextPack`. A V2 pack with a v1-only prompt is
a failed treatment gate, not a silent fallback. V2 packs have no
`blast_radius` / `prior_memory`; those attributes are not read.

Eval adds `context_mode` without replacing frozen H1 arms:

- `baseline_v1` — existing `apply_arm_context` / local-deterministic + v1 pack
- `context_v2_lexical` — `ContextBuilder(lexical=LexicalEvidenceProvider(), symbol=None, graph=None)`
- `context_v2` — all three providers

Eval uses `from_eval` on the existing exact-SHA workspace (no re-clone).
Production V2 uses `materialize_exact_sha_workspace` then `from_production`.
Eval and production instantiate the same `ContextBuilder` class. Providers are
injected via the constructor. `emit_experience_event` for
`context.candidate_evidence` and `context.evidence_selected` runs after
`build`, from `build_trace` only.

Production default remains `CONTEXT_MODE=baseline_v1` /
`compile_context_pack`. Typed `RLMJob.context_pack` stays `ContextPack`. The
V2 canary is `v2_dispatch.from_production`; live Gitea enqueue does not attach
V2. Memory, recursion, 2070, and repair stay off this wave.
`authorized_records` stays empty.

# Consequences

Positive: W1 can compare baseline_v1 vs context_v2 on the same SHA without
rewriting production, and treatment hashes (`context_pack_hash`,
`rendered_context_hash`, provider/evidence ids) are first-class telemetry.
Negative: two job schemas coexist; typed production jobs cannot yet carry V2.
Follow-up: widen `RLMJob.context_pack` only after a scored GO and an explicit
production-default decision; do not use `graph/snapshot.py` as the V2
workspace.
