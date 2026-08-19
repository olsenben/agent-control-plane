# Slice: VExp W1 treatment-exposure repair

**Status:** implemented (repaired 14-slot rerun frozen; WAVE 2 not started)
**Epic:** Verified Experience Control Plane (WAVE 1 repair; WAVE 2 not started)
**Hard gate:** production default remains `baseline_v1` / `compile_context_pack`; frozen `results/vexp-w1-context-v2-dev-v1` is immutable; solver prompts, model, retry, parser, patch, and verification are unchanged
**ADR:** [ADR-0039](adr/0039-pre-invocation-treatment-exposure.md) (proposed)

## Goal

Persist immutable treatment provenance (structured ContextPack, pack hash,
rendered-context hash, TreatmentExposure) **before** the 14B model response is
parsed. A fix-JSON parse error or json-retry timeout must remain an
`evaluated_agent` failure and must still retain complete V2 treatment
exposure.

## Root cause (slot 14 freeze)

Official W1 freeze `vexp-w1-context-v2-dev-v1`, slot 14
`retry-toolkit-e06` / `context_v2` /
`sess-eval-509576c0e89d4e59bba1d48e0fbd806c`:

1. `apply_eval_context` -> `v2_dispatch.from_eval` -> `_finish` already
   computed `context_pack_hash` / `rendered_context_hash` in memory and built
   a `TreatmentExposure`.
2. Official engine assembled the V2 user prompt (`official_engine_messages.json`
   exists) and invoked the model.
3. Fix JSON parse failed, then json-retry timed out. `OfficialRLMEngine.run`
   raised `ValueError`.
4. `eval_dispatch.dispatch_evaluation` caught that exception and wrote
   `_failed_session` **without** copying `arm_context.treatment_integrity`.
5. `_treatment_integrity` (the only path that copied hashes onto
   `evaluation_telemetry`) ran only after a successful `engine.run`.

STOP_REPAIR was incomplete treatment exposure, not a B1 verifier regression.

## Allowed touch area

- `src/agent_control/context/treatment_artifacts.py` (new)
- `src/agent_control/eval_dispatch.py` (persist before `engine.run`; attach on
  every failed-session path; finalization links the artifact)
- `src/agent_control/context/v2_dispatch.py` (`selected_counts_by_class` on
  in-memory integrity fields only)
- `tests/test_treatment_exposure_pre_invocation.py`
- `maintenance-evals` W1 treatment gate fallback + new create-only result dir
- this slice doc, ADR-0039, handoff, deploy-verify

## Avoid touching

- prompts, model/quant, retry counts, JSON parser, retry timeout
- patch policy, verification commands, repair iterations
- memory, recursion, 2070, A/B0/B1 definitions
- frozen V10 artifacts
- `results/vexp-w1-context-v2-dev-v1`
- production `CONTEXT_MODE` default
- `ContextBuilder.build` (stays pure)

## Lifecycle

1. build ContextPack
2. persist structured ContextPack artifact
3. persist structured pack hash
4. render model-visible context
5. persist rendered-context artifact/hash
6. persist TreatmentExposure record
7. invoke 14B model
8. parse / fix-JSON retry / patch / verify

Failures in 8+ must not erase steps 2–6. Json-retry is the same invocation:
one treatment record unless a real second solver invocation rebuilds a pack.

## Acceptance

1. Normal `context_v2`: pack, hashes, TreatmentExposure present after success.
2. Invalid JSON: artifacts already exist before parse failure handling.
3. JSON retry timeout: same treatment record; no silent reconstruction.
4. Exception after model, before patch extraction: provenance survives.
5. `baseline_v1` hashes still recorded; W0 baseline preservation stays green.
6. Pack hash equals serialized pack used to render; rendered hash equals
   model-visible rendered context.
7. `repair_attempts=0`, `recursive_invoked=false`, 2070 unused.

## Result versioning

- Freeze (immutable): `maintenance-evals/results/vexp-w1-context-v2-dev-v1`
- Repaired create-only rerun: `results/vexp-w1-context-v2-dev-v2-treatment-repair`
