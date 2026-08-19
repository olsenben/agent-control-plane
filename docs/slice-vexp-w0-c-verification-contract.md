# Slice: VExp W0-C / W0-D — verification result contract + telemetry vocabulary

### Goal

Freeze a cross-plane `ExperienceVerificationResult` schema (ACP + maintenance-evals, digest-pinned) and the W0-D telemetry vocabulary plus common envelope. No runtime verifier, ledger, or Observatory behavior change.

### Read first

- `EPIC_verified_experience_control_plane.md` §6 W0-C / W0-D, §4.4, §20
- `src/agent_shared/models/ci.py` (`CiVerificationResult`)
- `src/agent_shared/models/verification_claim.py`
- `maintenance-evals/src/maintenance_evals/verification.py` (`VerificationOutcome`)
- `src/agent_workers/sandbox/verify.py` (`verification_result.v1` dict)
- `src/agent_control/observe/safe_display.py` (`is_prohibited_field_name` keywords; read-only)

### Allowed touch area

- `src/agent_shared/models/experience_verification.py`
- `src/agent_shared/models/experience_events.py`
- `src/agent_shared/schemas/experience_verification_result.v1.json`
- `src/agent_shared/schemas/DIGESTS.md`
- `src/agent_control/experience_verification_adapters.py`
- `src/agent_control/telemetry/taxonomy.py`
- `src/agent_control/telemetry/__init__.py` (re-export only)
- `tests/test_experience_verification_result.py`
- `tests/test_experience_telemetry_taxonomy.py`
- `docs/slice-vexp-w0-c-verification-contract.md`
- evals `schemas/experience_verification_result.v1.json`
- evals `schemas/DIGESTS.md`
- evals `tests/test_experience_verification_schema.py`

### Avoid touching

- `events.py`, `session/events.py`, `observe/safe_display.py`
- `ci.py`, `verification.py` runtime
- `official_engine`, `eval_arm_context`, `graph/context_pack`
- `models/__init__.py`, `context/` package (W0-A / W0-B)
- frozen experiment manifests, reserved splits
- git commit / push / deploy

### Inputs / contracts

`ExperienceVerificationResult`:

- `schema_version`: `experience_verification_result.v1`
- `verification_scope`: `fast` | `final`
- `authority_domain`: `ct104_advisory` | `ct102_production` | `eval_harness`
- `official` / `additional`: `{commands, pass}` (independent lanes)
- `verified_success`, optional `failure_class`, `normalized_failures`, `evidence_refs`, timestamps
- `can_finalize_production_episode` is a computed property, never an input field:
  `== (authority_domain == "ct102_production")`

Adapters (pure functions):

| Source | scope | domain |
|---|---|---|
| VerificationOutcome-like | final | eval_harness |
| sandbox `verification_result.v1` | fast | ct104_advisory |
| `CiVerificationResult` / `VerificationClaim` | final | ct102_production |

W0-D vocabulary (17 names, `domain.action`):

```text
context.candidate_evidence
context.evidence_selected
memory.candidate_retrieved
memory.applicability_checked
memory.exposure_authorized
memory.exposure_abstained
memory.behavioral_use_observed
patch.generated
verification.fast.completed
repair.requested
repair.completed
verification.authoritative.completed
experience.admission_decided
memory.utility_labeled
memory.validity_changed
recursion.requested
recursion.completed
```

Existing closest names (documentation only; no live aliases):

| Epic name | Existing closest | W0 action |
|---|---|---|
| `verification.authoritative.completed` | `agent.verification_passed` | name + envelope only |
| `repair.requested` | `agent.fix_ci_repair_requested` | name only; different domain |
| `experience.admission_decided` | `agent.memory_admitted` / `rejected` | name only; payload deferred to W3 |
| `recursion.completed` | `agent.recursive_context_completed` | name only |
| remaining 13 | none | register names |

### Deliverables

- implementation (models, JSON schema in both repos, digest pin, adapters, taxonomy)
- unit tests (ACP result + taxonomy; evals schema digest)
- schema fixtures inline in tests
- telemetry vocabulary + envelope + `TreatmentExposure` (no W3–W7 payload models)
- migration note: additive only; verifiers and ledger emitters unchanged

### Acceptance tests

1. Schema validates fixtures; SHA-256 of both schema files matches the pinned digest.
2. `can_finalize_production_episode` is derived: `ct102_production` true; `eval_harness` and `ct104_advisory` false. Callers cannot pass a disagreeing boolean.
3. Official vs additional `pass` stay independent.
4. Eval adapter preserves `official_pass` / `additional_pass` / `claim_id` as an evidence ref.
5. All 17 event names registered; envelope builder rejects `prompt` / `token` / `secret` field names; `TreatmentExposure` constructs; emit helper does not append to the NFS ledger.

### Invariants

- CT102 remains the only domain that can finalize a production episode
- eval harness may be `verification_scope: final` for scored slots without production authority
- exact-SHA isolation (untouched this slice)
- no future-leak (untouched this slice)
- deterministic fallback (untouched this slice)
- no model-visible rejected memory (untouched this slice)
- no new failure taxonomy this wave
- Observatory `safe_display` stays single-owner

### Handoff

Report:

- files changed: listed under Allowed touch area
- interfaces implemented: `ExperienceVerificationResult`, `TreatmentExposure`, `ExperienceEventEnvelope`, 17 event names, three adapters
- test command:
  - ACP: `.venv/Scripts/pytest.exe tests/test_experience_verification_result.py tests/test_experience_telemetry_taxonomy.py`
  - evals: `python -m pytest tests/test_experience_verification_schema.py`
- known gaps: live ledger emission and Observatory registration wait for W1+
- merge conflicts likely: `telemetry/__init__.py` re-export only; schema files are new
