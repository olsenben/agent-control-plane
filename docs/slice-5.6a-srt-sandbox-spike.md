# Slice 5.6a — CT104 Anthropic SRT sandbox spike

**Status:** in progress (CT104 host strong canaries PASS; worker image still open)  
**Date:** 2026-07-14 (progress 2026-07-16)  
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
| 2026-07-16T23:42Z | spike (`bwrap-only` stub) | `unavailable` | `5de9f107fc05367e849f893c815efd18` | all fail (`bwrap_unavailable`) | **2e negative** inside `worker-rlm-root` — see progress log |
| 2026-07-16T23:22:03Z | spike | `strong` | `5de9f107fc05367e849f893c815efd18` | 7/7 passed | **2b positive** on CT104 host (`root@agentworker`); `strong_ok=true` |
| 2026-07-16T23:24:56Z | spike | `strong` | `5de9f107fc05367e849f893c815efd18` | 7/7 passed | **2c reboot retest** after CT104 login; `strong_ok=true` |

### Progress log (2026-07-16)

**Host CT104 (`agentworker`):**

- `bubblewrap` installed: `/usr/bin/bwrap` → **bubblewrap 0.9.0**.
- Host attestation works with `PYTHONPATH=src python3` from `/opt/ai-sdlc-lab/agent-control-plane`.

**2b — Strong canaries on host (PASS):**

```text
cd /opt/ai-sdlc-lab/agent-control-plane
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from agent_control.aci.backends.probes import attest_environment, policy_hash
import tempfile, json
ws = Path(tempfile.mkdtemp(prefix="sandbox-attest-"))
att = attest_environment(backend="srt", backend_version="spike", workspace=ws)
print(json.dumps(att.to_dict(), indent=2))
print("expected_policy_hash", policy_hash())
print("strong_ok", att.strong_ok)
PY
```

| Field | Value |
|-------|-------|
| `mode` | `strong` |
| `policy_hash` | `5de9f107fc05367e849f893c815efd18` (matches `policy_hash()`) |
| `probe_suite_version` | `sandbox_canary.v1` |
| `strong_ok` | `True` |
| probes | all passed: `deny_host_secret_read`, `deny_write_outside_workspace`, `deny_symlink_escape`, `deny_network`, `deny_docker_sock`, `deny_modify_shell_rc`, `no_surviving_children` |

**2c — Reboot / re-login retest (PASS):**

After CT104 console re-login (`Ubuntu 24.04 LTS` / `agentworker login: root`), same attestation script again → `mode=strong`, `strong_ok=True`, same `policy_hash`, all seven probes passed (`checked_at=2026-07-16T23:24:56Z`).

**Worker container (`docker-compose.ct104.yml` / `worker-rlm-root`):**

- `command -v bwrap` → **empty** — image does **not** ship Bubblewrap.
- Risk 2 runtime path still cannot attest strong until `bubblewrap` (and pinned SRT) are in the worker image / runtime.

**2e — Negative test (PASS):**

Ran attestation + `SrtSandboxBackend.run` + `evaluate_repair_allowed` inside `worker-rlm-root` with no `bwrap` available (rename unnecessary).

| Gate | Result |
|------|--------|
| `attest_environment` | `mode=unavailable`, `strong_ok=false`; probes detail `bwrap_unavailable` |
| `backend.run(["echo","hi"])` | exit `126`, `violated=True`, `violation_codes=['sandbox_check_failed']` — no silent exec |
| `evaluate_repair_allowed` | `allowed=False`, `label=agent:blocked`, `reason_codes=['sandbox_attestation_not_strong']` |

Still keep `FIX_CI_REPAIR_ENABLED=false`. Risk 2 / repair remain correctly blocked.

**Still open for 5.6a exit:**

- [x] **2b** strong canaries pass on CT104 host (`mode=strong`, all probes `passed`).
- [x] **2c** reboot / re-login CT104 and re-attest strong.
- [x] Fill positive rows in the attestation table above.
- [ ] Install `bwrap` (+ socat/rg/SRT pin) **in the worker image** (or otherwise make it available to the runtime that executes Risk 2).
  - 2026-07-16: verified missing in current image (`command -v bwrap` empty; `bwrap: not found`).
  - Dockerfile now installs `bubblewrap`/`socat`/`ripgrep` — rebuild CT104 image and re-attest inside `worker-rlm-root`.
- [ ] **2d** pin `SANDBOX_EXPECTED_POLICY_HASH` / backend env on CT103+CT104.
  - Examples updated to `5de9f107fc05367e849f893c815efd18`; add the same three `SANDBOX_*` lines to live `.env` on both hosts, recreate containers, `printenv` to confirm.
- [ ] Confirm worker-runtime path can also reach `strong_ok` (or document host-bwrap bind into worker as interim).
  - Nested Docker-in-LXC may still fail user-ns even with `bwrap` present — re-run attest after rebuild.

## Out of scope for 5.6a

- Full `/agent fix` workflow
- Production SRT packaging in worker images (may start as manual spike install)
- Network allowlists for package installs
- Nested Docker-in-LXC as accepted Risk 2 path

## Next

**Slice 5.8 / 6F.2:** Route Risk 2 `run_command` and repair through SandboxBackend; keep `fallback: deny`. See [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md).
