---
id: ADR-0006
title: tool_policy.v2 narrowing-only command allowance
status: proposed
date: 2026-07-19
---

# ADR-0006 — tool_policy.v2 narrowing-only command allowance

## Context

Central `config/command_registry.yaml` defines trusted argv. Repos previously shipped `tool_policy.v1` with their own argv. Missing tools policy silently allowed any central ID.

## Decision

Repos may only publish `tool_policy.v2` under `.agent/policies/tools.yaml` on the pinned policy SHA:

- Allowed keys: `schema`, `allowed_command_ids`, `constraints`, `deny_freeform_shell`, `allow_network` (must be false).
- Constraints may only tighten `max_timeout_seconds` (≤ central) and `allowed_path_globs` (relative, no `..`).
- Missing, invalid, unsupported version, unknown keys, unknown command IDs, or network enablement → **empty repository allowance** (no command execution / repair verifiers).
- Persist `command_registry_hash` and `effective_command_policy_hash` (sha256 over canonical JSON). Repair and verify require effective-hash match.

## Consequences

- Demo/template repos must migrate before repair enablement against those remotes.
- CT103 fetches `tools.yaml` at pin SHA when creating repair reservations; CT104 reloads from detached policy workspace and re-checks the hash.

## Related

- ADR-0005 (policy_source_sha pin)
- V4.1.1 closeout PR2 / [slice-v411-closeout.md](../slice-v411-closeout.md)
