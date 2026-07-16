# Slice 5.6a — CT104 Anthropic SRT sandbox spike

**Status:** planned (gate before `/agent fix`)  
**Date:** 2026-07-14  
**ADR:** [0002-srt-sandbox-backend.md](adr/0002-srt-sandbox-backend.md)  
**Plan:** V4.1 Phase 14 / implementation order 5.6a

## Why

ACI policy (command IDs, path denylist, closed-world diff) is designed. OS-enforced isolation is not. Until a backend can prove denied reads/writes, network deny, and socket deny on CT104, Risk 2 dispatch must stay disabled.

Preferred first backend: **Anthropic Sandbox Runtime (SRT)** via Bubblewrap on Linux. Fallback policy: **deny** (stricter than GitLab Duo's documented direct-run warning path).

## Target policy (control-plane authority only)

```yaml
sandbox:
  required_for: [fix, repair]
  backend: srt
  fallback: deny
  policy_authority: control_plane
  allow_project_policy_to_expand_access: false
  nested_mode: deny

  filesystem:
    allow_read: [workspace, system_runtime]
    allow_write: [workspace, /tmp/agent-run]
    deny_read: [worker_credentials, /home/agent/.ssh, /proc/*/environ]
    deny_write: [.git/hooks, .agent, .gitea, worker_runtime]

  network:
    default: deny
    allowed_domains: []

  unix_sockets:
    default: deny
    never_allow: [/var/run/docker.sock]
```

Do not load expanding overrides from a checked-out target repository.

## Spike procedure (CT104)

1. **Install** SRT and dependencies: Bubblewrap (`bwrap`), `socat`, `ripgrep` (`rg`). Record package versions and any AppArmor / user-namespace host changes needed for Ubuntu 24.04 unprivileged LXC.
2. **Strong mode only** — confirm SRT is not falling into nested-Docker compatibility mode. If nested mode is the only option inside this LXC, record failure and evaluate OCI-on-VM or disposable VM instead.
3. **Isolation tests** (must all fail closed under sandbox):
   - Denied read outside workspace / of credential paths
   - Denied write outside workspace and to `.git/hooks`, `.agent`, `.gitea`
   - Network egress denied (no allowlist)
   - Unix socket to `/var/run/docker.sock` denied
4. **Reboot CT104** and repeat the same tests (host/AppArmor persistence).
5. **Dispatch gate** — simulate sandbox capability failure; confirm fixer/repair enqueue is refused and would emit `agent.sandbox_check_failed` (wiring may follow in 5.8; spike at least proves the capability probe API).
6. **Decision** — pass → proceed to Slice 5.8 wiring; fail → document reason and select next backend without enabling `/agent fix`.

## Exit criteria

| Check | Required |
|-------|----------|
| SRT/bwrap creates strong sandbox inside CT104 LXC | yes |
| Behavioral canaries pass (secret/read, write, symlink, net, docker.sock, no orphans) | yes |
| Attestation records backend, version, mode=strong, policy_hash, probe_suite_version | yes |
| Nested/weak mode rejected for Risk 2 | yes |
| Capability failure blocks Risk 2 / repair (`agent:blocked`) | yes |
| `/agent fix` and `FIX_CI_REPAIR_ENABLED` remain off until attestation wires through | yes |

## Attestation (not a boolean)

```text
backend, backend_version, mode, policy_hash,
probe_suite_version, host_identity, checked_at,
individual probe results
```

Policy must **explicitly deny host reads** and re-allow only workspace + required runtime. Pin SRT version after a successful live spike; `sandbox_runtime` stubs use `bwrap-only` until then.

Code: `src/agent_control/aci/backends/` (`base.py`, `probes.py`, `srt.py`).

## Homelab notes

- CT104: unprivileged Ubuntu 24.04 LXC on steelleg (see [ct104.md](ct104.md), [agent-worker.md](agent-worker.md)).
- SRT warns that broad domain allowlists and Docker socket access enable exfiltration or escape — keep `allowed_domains: []` and `never_allow` docker.sock for V1.
- If Bubblewrap cannot run under current user-namespace/AppArmor settings, prefer fixing host isolation **or** moving the worker to a small VM over adopting nested-weak mode.

## Live spike checklist (operator)

1. Install pinned SRT + bwrap/socat/rg on CT104.
2. Run probe suite; record pass/fail in this table.
3. Reboot CT104; re-run probes.
4. Confirm `agent:blocked` when attestation fails at worker startup.

| Checked at | Backend version | Mode | Policy hash | Probes | Notes |
|------------|-----------------|------|-------------|--------|-------|
| (pending) | | | | | Fill after CT104 live spike |

## Out of scope for 5.6a

- Full `/agent fix` workflow
- Production SRT packaging in worker images (may start as manual spike install)
- Network allowlists for package installs
- Nested Docker-in-LXC as accepted Risk 2 path

## Next

**Slice 5.8 / 6F.2:** Route Risk 2 `run_command` and repair through SandboxBackend; keep `fallback: deny`. See [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md).
