# agent-state storage (homelab)

CT103 and CT104 both need the same `agent-state` tree. CT103 owns the ledger; CT104 `worker-report` writes `inbox/ct104-results/*.json` for CT103 `agentctl results ingest --inbox`.

**Do not run NFS inside unprivileged LXC containers** — `nfs-kernel-server` and NFS client mounts fail or behave badly (`rpc_pipefs`, `Operation not permitted`, `nobody` ownership).

Use **host-owned storage on goldenleg**, bind mounts into CTs, and NFS only between Proxmox hosts.

## Topology

```text
goldenleg (192.168.4.50)  canonical: /srv/agent-state
    |
    |-- Proxmox mp0 bind --> CT103 /mnt/agent-state
    |                         Docker: /data/agent-state (control-plane, worker-state)
    |
    |-- NFS export --------> steelleg (192.168.4.51) /srv/agent-state
                                |
                                |-- Proxmox mp0 bind --> CT104 /mnt/agent-state
                                                          Docker: /data/agent-state (workers)

CT104 local only: /mnt/agent-runs, /mnt/agent-cache
Queue traffic: CT104 --> CT103 Redis over Tailscale (not NFS)
```

| Path | Host | Shared? |
|------|------|---------|
| `/srv/agent-state` | goldenleg Proxmox | Canonical copy |
| `/mnt/agent-state` | CT103, CT104 | Same files via bind (+ NFS on steelleg) |
| `/mnt/agent-runs` | CT104 only | No |
| `/mnt/agent-cache` | CT104 only | No |

## Runtime layout under agent-state

```text
projects/{owner}/{repo}/events/...     # CT103 webhook / reducer
projects/.../summaries/...             # verification_state.json
outbox/state/...                       # CT103 state worker
inbox/ct104-results/{run_id}.json      # CT104 worker-report; CT103 ingest
```

## goldenleg (NFS server + CT103 bind)

### 1. Create canonical directory on the Proxmox host

```bash
mkdir -p /srv/agent-state
chown -R 100000:100000 /srv/agent-state
chmod 775 /srv/agent-state
```

UID `100000` maps to container `root` when CT103/CT104 are **unprivileged** (`unprivileged: 1`).

Migrate existing data from CT103 rootfs if needed (before adding `mp0`):

```bash
pct exec 103 -- tar -C /mnt/agent-state -cf - . | tar -C /srv/agent-state -xf -
chown -R 100000:100000 /srv/agent-state
```

### 2. Bind mount into CT103

In `/etc/pve/lxc/103.conf` on goldenleg:

```text
mp0: /srv/agent-state,mp=/mnt/agent-state
```

Spelling must be exact (`agent-state`, not `agent-stat`). Restart CT103:

```bash
pct stop 103 && pct start 103
pct exec 103 -- findmnt /mnt/agent-state
touch /srv/agent-state/.bind-test
pct exec 103 -- ls -la /mnt/agent-state/.bind-test
```

Inside CT103, clone/bootstrap `agent-state` at `/mnt/agent-state` if empty (see `scripts/ct103-host-bootstrap.sh`).

**Do not** install `nfs-kernel-server` on CT103. **Do not** add `/etc/exports` inside CT103.

### 3. NFS export from goldenleg host

```bash
apt install -y nfs-kernel-server

# NFS client is steelleg host (192.168.4.51), not CT104 IP — mount runs on the Proxmox host
echo "/srv/agent-state 192.168.4.51(rw,sync,no_subtree_check,no_root_squash)" >> /etc/exports

exportfs -ra
systemctl enable --now nfs-server
exportfs -v
```

Tighter homelab option: also allow `192.168.4.63` if you ever NFS-mount from CT104 directly (not recommended).

## steelleg (NFS client + CT104 bind)

### 1. NFS mount on the Proxmox host (not inside CT104)

```bash
apt install -y nfs-common
mkdir -p /srv/agent-state

mount -t nfs 192.168.4.50:/srv/agent-state /srv/agent-state
echo "192.168.4.50:/srv/agent-state /srv/agent-state nfs defaults,_netdev 0 0" >> /etc/fstab
systemctl daemon-reload
```

Verify ownership shows `100000` (not host `root`):

```bash
ls -la /srv/agent-state
```

### 2. Bind mount into CT104

In `/etc/pve/lxc/104.conf` on steelleg:

```text
mp0: /srv/agent-state,mp=/mnt/agent-state
```

```bash
pct stop 104 && pct start 104
pct exec 104 -- findmnt /mnt/agent-state
```

**Do not** add NFS lines to `/etc/fstab` inside CT104.

### 3. Local worker directories on CT104

```bash
pct exec 104 -- mkdir -p /mnt/agent-runs /mnt/agent-cache
```

## Verification

```bash
# CT104 write
pct exec 104 -- mkdir -p /mnt/agent-state/inbox/ct104-results
pct exec 104 -- sh -c 'echo from-ct104 > /mnt/agent-state/inbox/ct104-results/.e2e-test'

# goldenleg canonical
cat /srv/agent-state/inbox/ct104-results/.e2e-test

# CT103 bind
pct exec 103 -- cat /mnt/agent-state/inbox/ct104-results/.e2e-test
```

All three must show `from-ct104`.

## Ownership troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `nobody:nogroup` inside CT | Host files owned by uid `0` on goldenleg | `chown -R 100000:100000 /srv/agent-state` on goldenleg |
| `Permission denied` in CT104 | Same, or NFS export ACL | Fix ownership; export to **steelleg** `192.168.4.51` |
| `access denied by server` | Export allows wrong client IP | Client is steelleg host, not CT104 `.63` |
| `findmnt` empty on `/mnt/agent-state` | `mp0` typo or CT not restarted | Fix `mp=/mnt/agent-state`, `pct stop/start` |
| `.mount-test` missing in CT103 | Bind points at wrong path | Fix typo in `103.conf` |

Avoid creating files on steelleg as **host root** over NFS — they may not map into unprivileged CTs. Prefer writes from inside CT103/CT104.

## Docker paths

Both hosts use the same compose env (see `.env.example`):

```env
AGENT_STATE_HOST_PATH=/mnt/agent-state
AGENT_STATE_ROOT=/data/agent-state
```

CT103: `docker-compose.yml` mounts host `/mnt/agent-state` → container `/data/agent-state`.

CT104: `docker-compose.ct104.yml` — same for state; `/mnt/agent-runs` and `/mnt/agent-cache` stay local.

## Boot order

1. goldenleg: `nfs-server` up, `/srv/agent-state` present
2. steelleg: fstab NFS mount to `/srv/agent-state`
3. Start CT103, CT104 (Proxmox `mp0` binds)

## Rejected patterns

| Pattern | Why |
|---------|-----|
| NFS server on CT103 | LXC cannot host `nfs-kernel-server` (`rpc_pipefs`) |
| NFS client inside CT104 | `mount.nfs: Operation not permitted` in unprivileged LXC |
| Export `192.168.4.62:/mnt/agent-state` | CT103 is not the NFS server |
| Bind mount between CT103 and CT104 directly | Different Proxmox nodes (goldenleg vs steelleg) |

## Homelab addresses (reference)

| Component | LAN IP |
|-----------|--------|
| goldenleg (NFS server) | 192.168.4.50 |
| steelleg (NFS client) | 192.168.4.51 |
| CT103 agentcontrol | 192.168.4.62 |
| CT104 agentworker | 192.168.4.63 |

See also [deploy.md](deploy.md), [ct104.md](ct104.md), [run-artifacts.md](run-artifacts.md).
