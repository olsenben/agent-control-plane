---
id: ADR-0039
title: Persist treatment exposure before model-response handling
status: proposed
date: 2026-08-19
owners:
  - platform
scope:
  globs:
    - "src/agent_control/context/treatment_artifacts.py"
    - "src/agent_control/eval_dispatch.py"
    - "src/agent_control/context/v2_dispatch.py"
  symbols:
    - persist_pre_invocation_treatment
    - TreatmentExposure
    - dispatch_evaluation
decision_type: architecture
enforcement: hard
risk_level: low
supersedes: []
superseded_by: []
review_after: 2026-11-19
agent_visibility:
  - review
  - developer
---

# Context

WAVE 1 recorded ContextPack V2 hashes on eval-session telemetry only after
`engine.run` returned. Slot 14 of the official DEV bakeoff failed inside
fix-JSON parse / json-retry timeout. `dispatch_evaluation` wrote
`_failed_session` without treatment hashes even though `v2_dispatch._finish`
had already computed them in memory and the official engine had already
persisted the V2 user prompt. STOP_REPAIR fired for incomplete treatment
exposure, not because B1 verification was worse than A.

Telemetry emission is in-memory only (ADR-0037). Session finalization is not a
safe sole source of truth for "what treatment the model consumed."

# Decision

Eval-dispatch persists a create-only pre-invocation treatment artifact after
the job carries `context_pack` and before `engine.run`:

- `context_pack.json` — exact structured dump that is hashed
- `rendered_context.txt` — exact model-visible render that is hashed
- `treatment_exposure.json` — TreatmentExposure plus invocation identity,
  arm, snapshot, hashes, provider/evidence ids

Failed sessions copy those fields onto `evaluation_telemetry`. Successful
finalization links the same artifact and still validates that a V2 pack was
prepended into the persisted user prompt. Json-retry does not write a second
treatment record. `ContextBuilder.build` remains pure. Production default
remains `baseline_v1`. Prompts, model, parser, retry, patch, and verification
are unchanged.

# Consequences

Positive: an `evaluated_agent` parse/timeout failure still proves which
treatment was delivered. Negative: artifact_dir grows by three files per
eval session. Follow-up: do not start WAVE 2 until a repaired 14-slot result
set has complete treatment exposure; do not claim V2 maintenance lift without
verifier discrimination.
