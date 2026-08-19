---
id: ADR-0037
title: Keep VExp W0 contracts additive and leave the v1 solver path unchanged
status: proposed
date: 2026-08-19
owners:
  - platform
scope:
  globs:
    - "src/agent_shared/models/repo_snapshot.py"
    - "src/agent_shared/models/context_pack_v2.py"
    - "src/agent_shared/models/experience_verification.py"
    - "src/agent_control/context/**"
    - "src/agent_control/telemetry/taxonomy.py"
    - "../maintenance-evals/schemas/experience_verification_result.v1.json"
  symbols:
    - RepoSnapshot
    - ContextPackV2
    - ExperienceVerificationResult
    - authorized_records
    - can_finalize_production_episode
decision_type: architecture
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-11-19
agent_visibility:
  - review
  - developer
---

# Context

The Verified Experience Control Plane epic needs stable seams (exact-SHA
snapshot identity, ContextPack V2, a shared verification result, telemetry
vocabulary) without changing the frozen H1/eval treatment. The live tree already
stores canonical models under `agent_shared/models/` and compiles v1 packs in
`graph/context_pack.py`. Speculative W2–W6 Protocols and treating ungated
`prior_memory` as authorized would freeze the wrong thesis.

# Decision

W0 is additive. `ContextPack` v1 remains the solver contract. Jobs still carry
v1 packs; `official_engine.py`, `apply_arm_context`, and production dispatch are
not wired to V2.

`RepoSnapshot.snapshot_id` is the digest of `(repository_id, target_sha)` only.
`workspace_path` and `index_generation` are not repository-state identity.

V1 `prior_memory` maps to `experience.compatibility.legacy_prior_memory`.
`authorized_records` stays empty until an authorization decision actually
occurs. `render_v1_compatible` may reproduce old exposure; the normal V2
renderer must not treat legacy memory as authorized.

`ExperienceVerificationResult` separates `verification_scope` (`fast`|`final`)
from `authority_domain` (`ct104_advisory`|`ct102_production`|`eval_harness`).
`can_finalize_production_episode` is derived: true only for
`ct102_production`. Eval harness results may be final for a scored slot and
still cannot finalize a production episode.

ACP and maintenance-evals share `experience_verification_result.v1.json` under
a pinned sha256. Telemetry W0 freezes event names, a common envelope,
`TreatmentExposure`, and a safe-field policy. W3–W7 payloads are not frozen.
Only `RepositoryEvidenceProvider` and `ContextBuilderV2` Protocols are frozen.

The W0-E compatibility comparison must execute on the integration tip. SKIP is
allowed only on an isolated slice branch with `VEXP_W0_ALLOW_COMPAT_SKIP=1`.

# Consequences

Positive: later waves can land behind these seams without rewriting the runtime
twice, and W4 can treat `authorized_records` as a real gate. Negative: two
context schemas coexist until W1 wires V2 onto the solver path. Follow-up: do
not open W1 until `DEPLOY_VERIFY: PASS` on this tip; do not freeze retriever,
applicability, repair, or episode Protocols here.
