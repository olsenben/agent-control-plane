---
id: ADR-0003
title: Cap-bounded bwrap for SRT inside CT104 Docker
status: proposed
date: 2026-07-18
owners:
  - platform
scope:
  globs:
    - "docker-compose.ct104.yml"
    - "src/agent_control/aci/backends/**"
    - "Dockerfile"
  symbols: []
decision_type: security
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-08-18
agent_visibility:
  - review
  - developer
---

# Context

ADR-0002 selected Anthropic SRT / Bubblewrap as the OS sandbox. Homelab CT104 runs workers as Docker containers inside an unprivileged LXC. Default Docker seccomp/AppArmor blocks `bwrap --unshare-net` (`Creating new namespace failed` / loopback setup failures). Attestation canaries previously false-passed when bwrap failed to launch. Verifier commands also need a merged-/usr + `/usr/local` mount so `python -m ruff|pytest` resolve inside the sandbox.

# Decision

For CT104 workers that execute SRT (`worker-ci-repair`, `worker-rlm-root`):

1. Set `security_opt: [seccomp:unconfined, apparmor:unconfined]`.
2. Add capabilities `SYS_ADMIN` and `NET_ADMIN` (not full `--privileged`).
3. Build SRT/bwrap argv via shared `bwrap_isolation_argv` (system runtime ro-bind + workspace rw).
4. Treat bwrap launch failures as attestation/command failure (fail closed), never as deny-success.
5. Install verifier tools (`ruff`, `pytest`) in the worker image via `pip install -e ".[dev]"`.

Sandbox still has no Gitea write credentials; push remains outside SRT on the worker supervisor (transitional CT104 publish debt per §0.7).

# Consequences

- Demo sandboxed repair verify+push works on CT104 Docker-on-LXC.
- Larger container attack surface than default Docker (bounded to two worker services).
- Follow-up: V4.1.1 publish brokerage on CT103 may retire CT104 write tokens; re-evaluate whether SRT can move to a less-privileged executor layout.
