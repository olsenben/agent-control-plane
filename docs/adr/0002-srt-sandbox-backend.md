---
id: ADR-0002
title: Anthropic SRT as initial OS sandbox backend
status: proposed
date: 2026-07-14
owners:
  - platform
scope:
  globs:
    - "src/agent_control/aci/**"
    - "src/agent_workers/sandbox/**"
    - "docs/slice-5.6a-srt-sandbox-spike.md"
  symbols:
    - SandboxBackend
    - Sandbox
decision_type: security
enforcement: hard
risk_level: high
supersedes: []
superseded_by: []
review_after: 2026-10-14
agent_visibility:
  - review
  - developer
---

# Context

The V4.1 plan defines a sandbox *contract* for Risk 2 (`/agent fix`, repair): disposable workspaces, command IDs only, no writes outside the workspace, network deny by default, path/closed-world diff enforcement, and fail-closed behavior via `agent.sandbox_check_failed`.

That contract is not yet backed by an OS-enforced isolation layer. `agent_control/aci/sandbox.py` is a disposable-tmpdir stub. A command allowlist alone is not a sandbox: a misbehaving or compromised tool still has CT104/LXC privileges.

GitLab Duo remote flows use Anthropic Sandbox Runtime (SRT) inside the execution image (Bubblewrap + proxy network filtering on Linux). GitLab documents a fallback to direct execution with a warning when SRT is unavailable. For Risk 2 work that writes repositories, an unsandboxed fallback is unacceptable.

Homelab constraint: CT104 is an unprivileged Ubuntu 24.04 LXC. SRT needs Bubblewrap, socat, and ripgrep; AppArmor user-namespace restrictions may block strong isolation unless host configuration is adjusted. SRT nested-Docker mode weakens isolation and must not be the production path without an outer strong layer.

# Decision

1. **Interface:** Keep a generic `SandboxBackend` under ACI. The control plane validates command ID, argv, cwd, and paths, then builds a trusted sandbox policy and launches through the backend.
2. **Initial backend:** Anthropic SRT (`backend: srt`). Future backends may include hardened OCI containers or disposable VMs without changing the ACI contract.
3. **Fallback:** `deny`. No direct execution, no silent degradation, no nested/weak SRT mode for Risk 2.
4. **Policy authority:** Control plane only (`policy_authority: control_plane`). Checked-out repos must not enable network, broaden filesystem access, permit Unix sockets (especially `/var/run/docker.sock`), or select a weaker backend/mode (`allow_project_policy_to_expand_access: false`).
5. **Gate:** Slice 5.6a (CT104 install + behavioral canary attestation + reboot retest + dispatch block on failure) must pass before `/agent fix` or 6F.2 repair is enabled. Attestation is an object (`mode`, `policy_hash`, probe results), not a boolean. If SRT cannot provide strong isolation inside the current LXC, choose another strong backend and re-spike — still fail-closed.
6. **Required for:** `fix` and `repair` (Risk 2). Risk 0 read-only may remain unsandboxed when configured; Risk 3 stays blocked by default.
7. **Policy shape:** Explicitly deny host reads; re-allow only workspace + required runtime paths. Write and network default deny. Reject nested Linux mode. Pin SRT version after CT104 spike.
8. **Capability probes:** At deploy and worker startup, canaries must prove denied host-secret read, write-outside, symlink escape, network/DNS, docker.sock, shell-rc mutation, and no surviving children.

# Consequences

- Positive: Contract matches enforcement intent; stricter than GitLab's documented SRT fallback; portable backend swap later; repair loop cannot enable without strong attestation.
- Negative: CT104/AppArmor work may delay `/agent fix` and 6F.2; SRT dependency and Bubblewrap privilege model must be operated and tested after every host change.
- Follow-up: Complete live CT104 spike record in slice-5.6a; wire Risk 2 `run_command` exclusively through SandboxBackend; 6F.2 uses `repair_allowed` + attestation.
