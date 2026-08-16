# Security

- Webhook HMAC validation on raw body (constant-time compare).
- Repo allowlist enforced before event append.
- Target repos must not contain privileged dispatch workflows.
- Gitea bot token lives on CT103 only. CT104 has no Gitea API write token; result comments and publication are brokered by CT103.
- External/fallback model API keys live in `.env` on CT103 only; never commit them or echo them in trajectories or Gitea comments.
- State worker concurrency: 1 globally at MVP.
- Redis/RQ use pickle serialization; keep Redis on CT103 private only (UFW denies 6379; no public exposure).

## Public surface (CT103)

Prefer LAN webhooks: `http://192.168.4.62:8080/webhooks/gitea`.

If `control.ham-sup-lo.com` remains public, set `ENFORCE_PUBLIC_SURFACE_RESTRICTION=true` to expose only `/healthz`, `/readyz`, `/webhooks/gitea`.

## Prompt injection

Layers: explicit activation, command scope / risk_class, untrusted-data preamble (Step D+), ToolRegistry enforcement, context broker (Phases 4-6), secret redaction before logs/comments.

Regression tests: `tests/test_prompt_injection.py`.

## CT104 credentials

| Worker | Has | Does not have |
|--------|-----|---------------|
| worker-rlm-root | Redis, HTTP git credentials (read-only), agent-runs | Gitea API token, model keys |
| worker-report | agent-state/result artifact access | Gitea API write token, repo write key |

- CT104 production startup fails closed if `GITEA_AGENT_TOKEN` or `GITEA_BOT_TOKEN` is present. See [secrets-boundaries.md](secrets-boundaries.md) and ADR-0004.
- ADR mandatory constraints fail closed on prompt budget overflow.
