# Slice 5.6a — CT104 Anthropic SRT sandbox spike

**Status:** spike complete (host + worker strong PASS; 2d env pin verified 2026-07-17)  
**Date:** 2026-07-14 (signed off 2026-07-17)  
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
| Live `SANDBOX_*` pins on CT103 + CT104 match `policy_hash()` | yes |
| Full sandboxed repair worker push deferred to 5.8 / 6F.2 completion | yes |

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
| 2026-07-16T23:42Z | spike (`bwrap-only` stub) | `unavailable` | `5de9f107fc05367e849f893c815efd18` | all fail (`bwrap_unavailable`) | **2e negative** inside `worker-rlm-root` (pre-bwrap image) |
| 2026-07-16T23:22:03Z | spike | `strong` | `5de9f107fc05367e849f893c815efd18` | 7/7 passed | **2b positive** on CT104 host (`root@agentworker`); `strong_ok=true` |
| 2026-07-16T23:24:56Z | spike | `strong` | `5de9f107fc05367e849f893c815efd18` | 7/7 passed | **2c reboot retest** after CT104 login; `strong_ok=true` |
| 2026-07-17T00:01:51Z | spike (image bwrap 0.8.0) | `strong` | `5de9f107fc05367e849f893c815efd18` | 7/7 passed | **Worker-runtime positive** inside `worker-rlm-root`; `strong_ok=true` |

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

- After Dockerfile rebuild (`bubblewrap`/`socat`/`ripgrep`): `bwrap --version` → **bubblewrap 0.8.0** (Debian bookworm; host is 0.9.0).
- Nested Docker-in-LXC did **not** block strong mode on this host.

**Worker-runtime strong canaries (PASS):**

```text
docker compose -f docker-compose.ct104.yml exec -T worker-rlm-root \
  python3 - <<'PY'
# same attest_environment script as host
PY
```

| Field | Value |
|-------|-------|
| `checked_at` | `2026-07-17T00:01:51Z` |
| `mode` | `strong` |
| `host_identity` | `c60da1b7404d\|Linux\|25` (container) |
| `policy_hash` | `5de9f107fc05367e849f893c815efd18` |
| `strong_ok` | `True` |
| probes | 7/7 passed |

**2e — Negative test (PASS, pre-rebuild):**

Ran attestation + `SrtSandboxBackend.run` + `evaluate_repair_allowed` inside `worker-rlm-root` with no `bwrap` available (rename unnecessary).

| Gate | Result |
|------|--------|
| `attest_environment` | `mode=unavailable`, `strong_ok=false`; probes detail `bwrap_unavailable` |
| `backend.run(["echo","hi"])` | exit `126`, `violated=True`, `violation_codes=['sandbox_check_failed']` — no silent exec |
| `evaluate_repair_allowed` | `allowed=False`, `label=agent:blocked`, `reason_codes=['sandbox_attestation_not_strong']` |

**2d — Live env pin (PASS, 2026-07-17):**

| Host | Service | `SANDBOX_BACKEND` | `SANDBOX_EXPECTED_POLICY_HASH` | `SANDBOX_REQUIRE_ATTESTATION` |
|------|---------|-------------------|--------------------------------|-------------------------------|
| CT103 | `control-plane` | `srt` | `5de9f107fc05367e849f893c815efd18` | `true` |
| CT104 | `worker-rlm-root` | `srt` | `5de9f107fc05367e849f893c815efd18` | `true` |

Confirm commands:

```text
# CT103
docker compose exec -T control-plane printenv \
  SANDBOX_BACKEND SANDBOX_EXPECTED_POLICY_HASH SANDBOX_REQUIRE_ATTESTATION

# CT104
docker compose -f docker-compose.ct104.yml exec -T worker-rlm-root printenv \
  SANDBOX_BACKEND SANDBOX_EXPECTED_POLICY_HASH SANDBOX_REQUIRE_ATTESTATION
```

**5.6a exit checklist:**

- [x] **2b** strong canaries pass on CT104 host (`mode=strong`, all probes `passed`).
- [x] **2c** reboot / re-login CT104 and re-attest strong.
- [x] Fill positive rows in the attestation table above.
- [x] Install `bwrap` (+ socat/rg) **in the worker image** and confirm Risk 2 runtime `strong_ok`.
- [x] **2d** pin `SANDBOX_EXPECTED_POLICY_HASH` / backend env on CT103+CT104 live `.env`.
- [x] **2e** negative: missing `bwrap` → `unavailable` / `agent:blocked` (recorded pre-rebuild).

Demo-only: CT103 may have `FIX_CI_REPAIR_ENABLED=true` for the 6F.2 **gate** proof on `demo-app` (see [slice-6f](slice-6f-ci-failure-repair.md)). That does **not** complete repair worker push — Slice **5.8** still required before treating repair as sandboxed end-to-end.

## Out of scope for 5.6a

- Full `/agent fix` workflow
- Production SRT packaging in worker images (may start as manual spike install)
- Network allowlists for package installs
- Nested Docker-in-LXC as accepted Risk 2 path
- 6F.2 worker `repair_started` / `repair_pushed` path

## Next

**Next:** [slice-5.8-6f2-sandboxed-repair.md](slice-5.8-6f2-sandboxed-repair.md) (Approved / implementation pending) — `command_runner` + repair reservation/lease + worker push.
