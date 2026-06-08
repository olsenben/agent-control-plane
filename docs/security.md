# Security

- Webhook HMAC validation on raw body (constant-time compare).
- Repo allowlist enforced before event append.
- Target repos must not contain privileged dispatch workflows.
- Gitea bot token lives on the control-plane host only.
- External/fallback model API keys (`MODEL_*_EXTERNAL_API_KEY`, `MODEL_*_FALLBACK_API_KEY`) live in `.env` on CT103 only; never commit them or echo them in trajectories or Gitea comments.
- State worker concurrency: 1 globally at MVP.
- Redis/RQ use pickle serialization; keep Redis on CT103 private only (UFW denies 6379; no public exposure).
- ADR mandatory constraints fail closed on prompt budget overflow.
