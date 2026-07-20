---
id: ADR-0020
title: AgentFacts-lite content-hash integrity with optional HMAC
status: proposed
date: 2026-07-20
---

# ADR-0020: AgentFacts-lite content-hash integrity with optional HMAC

## Context

V4 deferred AgentFacts signing. V5 T01 needs a capability/limitation manifest that keeps `AGENT_CARD.md` and `agent-card.json` honest before A2A/MCP protocol glue, without adding a new PKI service.

## Decision

1. Commit `agent-facts.json` (`agent_facts.v1`) derived from both cards; limitations come from the human card.
2. Integrity is primarily `sha256` over a canonical payload plus `source_hashes` of the two card files — stale or unsigned manifests fail `agentctl agentfacts check`.
3. Optional `hmac-sha256` when `AGENTFACTS_SIGNING_SECRET` is set (`--require-hmac` for hard fail).
4. CT103 owns the check; no CT104 Gitea write tokens; per-worker role manifests are a follow-up.

## Consequences

- Positive: deployable sync/integrity gate without key ceremony; operators re-sign after card edits.
- Negative: content-hash alone does not stop a malicious committer who rewrites cards + manifest together; HMAC is the upgrade path.
- Follow-up: per-worker AgentFacts; wire check into readiness or CI as a required job.
