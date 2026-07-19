---
id: ADR-0007
title: Dual sandbox and execution attestations with durable bundle-before-teardown
status: proposed
date: 2026-07-19
---

# ADR-0007 — Dual sandbox and execution attestations

## Context

CT104 produces patches; CT103 publishes. After brokerage (ADR-0004), CT103 still needs authenticated executor claims that bind policy pin, target SHA, sandbox readiness, and teardown outcome — without trusting CT104 as sole proof of correctness.

## Decision

1. **Pre-execution `sandbox_attestation.v1`**: run/job IDs, executor/workspace identity, backend/version, policy repo+SHA, target SHA, registry + effective command-policy hashes, network profile, capability tests, credential-scrub categories/names only, CT103-issued nonce, ready/not-ready.
2. **Lifecycle**: `allocated → workspace_prepared → sandbox_attested → work_started → bundle_finalized → workspace_destroyed|quarantined → execution_attestation_finalized`.
3. **Durability**: write READY bundle (including preflight attestation) **before** workspace destroy; attach `execution_attestation.v1` after teardown.
4. **Publish eligibility (CT103)**: destroyed + valid dual attestations (+ nonce/bindings) → eligible; quarantined or missing/invalid attestations → deny.
5. **Clone hygiene**: hooksPath/askpass/credential.helper disabled; `GIT_CONFIG_NOSYSTEM`; strip token remotes; unsafe protocols off.
6. **SimulationSandboxBackend**: unit tests / `model_policy=fake` only when real strong attestation is unavailable — not a production substitute for Risk-2 when isolation is required.

## Consequences

- Fix and repair producers must emit both attestation files before CT103 will publish.
- Jobs carry `attestation_nonce` from CT103; repair reservations record the same.
- CT103 continues independent patch/evidence/hash validation.

## Related

- ADR-0002, ADR-0003 (sandbox), ADR-0004 (brokerage), ADR-0005/0006 (policy)
- V4.1.1 closeout PR3 / [slice-v411-closeout.md](../slice-v411-closeout.md)
