# Deploy verification — V10 T00 platform baseline freeze

| Field | Value |
|-------|-------|
| Ticket ID | V10 T00 |
| Baseline doc | `docs/evals/V10_BASELINE.md` |
| Tip SHA (requested) | `4376ef417e29f14bf05d2fcee89c0ab2739f2ddb` |
| Tip SHA (verified) | `4376ef417e29f14bf05d2fcee89c0ab2739f2ddb` on CT103 and CT104 |
| Date (UTC) | 2026-08-16 |
| Operator | live-cert evidence supplied to V10 T00 coordinator |
| Status | `PASS` |

Run through WSL bash with the CT103/CT104 deploy key. Commands that inspect environment state must emit variable names or presence/absence only, never values.

## A. Repository and CI pin

- [x] T00 changes are documentation-only; no agent behavior/code change is included.
- [x] CT103 and CT104 live repository tips match.
- [x] Live-deployed Git SHA is recorded in `docs/evals/V10_BASELINE.md`.
- [ ] Final docs-only commit SHA and `eval-baseline-2026-08` tag: `PENDING_COMMIT` (closeout action, not a live-cert failure).

Evidence:

```text
CT103 tip: 4376ef417e29f14bf05d2fcee89c0ab2739f2ddb
CT104 tip: 4376ef417e29f14bf05d2fcee89c0ab2739f2ddb
tag target: PENDING_COMMIT
```

## B. CT103 sole Gitea mutation authority

- [x] CT103 `control-plane`, `worker-state`, and `publish-broker` deployed image IDs were captured.
- [x] `/readyz` reports `ready`; Redis and state are `ok`.
- [x] `GITEA_BOT_TOKEN` is present on CT103 as expected.
- [x] `FIX_REMOTE_PUBLISH_ENABLED=true` on CT103.
- [x] ADR-0004 / Slice 6D.2 remain the frozen authority contract: CT103 `publish-broker` is the sole branch/PR publication authority and does not trust worker-supplied authorization fields.

Commands/checks:

```bash
git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD
cd /opt/ai-sdlc-lab/agent-control-plane
docker compose ps
curl -fsS http://127.0.0.1:8080/readyz
```

Broker evidence: expected CT103 token present; remote publication enabled; dedicated `publish-broker` image captured; ADR-0004 / Slice 6D.2 contract unchanged.  
Result: `PASS`

## C. CT104 write-token and sandbox boundary

- [x] `GITEA_BOT_TOKEN` and `GITEA_AGENT_TOKEN` are absent from `worker-rlm-root`.
- [x] `GITEA_BOT_TOKEN` and `GITEA_AGENT_TOKEN` are absent from `worker-report`.
- [x] `GITEA_BOT_TOKEN` and `GITEA_AGENT_TOKEN` are absent from `worker-ci-repair`.
- [x] Read-only checkout credentials remain the only permitted CT104 Gitea credentials.
- [x] Worker startup fail-closed guard against Gitea write tokens remains frozen by Slice 6D.2.
- [x] CT104 produces result or immutable patch-bundle artifacts only; CT103 owns push, PR, and comment mutation.

Safe inspection pattern (prints names only, never values):

```bash
cd /opt/ai-sdlc-lab/agent-control-plane
git rev-parse HEAD
docker compose -f docker-compose.ct104.yml ps
for service in worker-rlm-root worker-report worker-ci-repair; do
  docker compose -f docker-compose.ct104.yml exec -T "$service" sh -c \
    'for n in GITEA_BOT_TOKEN GITEA_AGENT_TOKEN; do [ -n "$(printenv "$n")" ] && echo "PRESENT:$n"; done' \
    </dev/null
done
```

Observed token-name output: empty for all three worker containers.  
Result: `PASS`

## D. CT102 verification-only boundary

- [ ] CT102 runner/version: `PENDING_LIVE_CERT` (`DEEPER_EVAL` before scored evaluation).
- [x] Frozen architecture remains verification-only; no T00 change expands CT102 authority.
- [x] Verification claims remain scoped to machine-recorded checks actually run.

Runner/version: `PENDING_LIVE_CERT`  
Result: `DEEPER_EVAL` (non-blocking for the T00 CT103/CT104 trust-boundary freeze)

## E. Images, models, and frozen hashes

- [x] CT103 image IDs copied to `V10_BASELINE.md`.
- [x] All three relevant CT104 worker image IDs copied to `V10_BASELINE.md`.
- [x] 3080 model `qwen2.5-coder:14b`, quantization `Q4_K_M`, and Ollama `0.24.0` recorded.
- [x] Configured 2070 model `qwen2.5-coder:3b` and Ollama `0.24.0` recorded; installed-but-unconfigured 7B model distinguished.
- [x] Frozen command-registry, SRT policy, recursive-context, and adequacy-profile hashes remain recorded in `V10_BASELINE.md`.
- [x] Observatory projection remains `observation_projection.v1` from the pinned V9 contract.

Evidence:

```text
CT103 control-plane: sha256:f743c713baa1c756dda4adf330e5908ee6fbad92cb47118fdc51945b6763226a
CT103 publish-broker: sha256:99185d42d19e97f30b3d614a147b928a6d00172563b3316a58e73705b475bdcc
CT103 worker-state: sha256:987fe2ba4b5710a6aa07c2b89a5935fd7721e6e7f196a165602b0b93516ec179
CT104 worker-rlm-root: sha256:f5ffb5996abd0a46c50baebb9a64867dacba099c4bdce433db226982141b7b65
CT104 worker-report: sha256:6eb011a7b6a2e80e00c05972860698255b93e2e3a61ba7a93eff97e3c04271f8
CT104 worker-ci-repair: sha256:ec61dbbde7af00fe69fc84d1b8641d8a8c96544db37537401806953f475ace3f
CT102 runner/version: PENDING_LIVE_CERT / DEEPER_EVAL
3080 model / quantization / Ollama: qwen2.5-coder:14b / Q4_K_M / 0.24.0
2070 configured model / Ollama: qwen2.5-coder:3b / 0.24.0
routing / fallback: official / gpt-4.1 + gpt-4o-mini
```

## F. Documentation and regression floor

- [x] All five stale CT104 write-token documents now identify CT103 as sole Gitea mutation authority.
- [x] No agent behavior/code file changed for T00.
- [x] CT104 direct publication remains retired.
- [x] Risk-2 approval, sandbox, closed-world diff gate, CT103 brokerage, and scoped CT102 verification boundaries remain intact.
- [x] Documentation diagnostics and diff checks pass; no runtime change requires a new behavior test.

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 4376ef417e29f14bf05d2fcee89c0ab2739f2ddb
baseline_tag: eval-baseline-2026-08 (create after docs-only commit)
next_ticket_unblocked: yes (T00.5)
deeper_eval: CT102 runner/version inventory
blocker: none
```
