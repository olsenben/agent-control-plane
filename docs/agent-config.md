# Agent configuration (`.agent/`)

Repo-local agent policy loaded from the **protected base branch** only.

## Required files (write flows)

- `.agent/agent-config.yml`
- `.agent/agents.yml`
- `.agent/flows.yml`

## Inspect bootstrap (allowlisted repos)

Any repo under an owner listed in `config/projects.yaml` → `platform.allowed_owners` (default: all `ai-sdlc-lab/*`) may use platform-default inspect policy when `.agent/agent-config.yml` is missing.

Explicit per-repo entries in `projects.projects` override URLs only; bootstrap still inherits platform defaults unless overridden.

CT103 webhooks use `GITEA_ALLOWED_REPOS` in `.env` (set `ai-sdlc-lab/*` for the whole org).

## Flow risk classes

| Class | Flows |
|-------|-------|
| read_only | inspect, explain |
| read_only_with_repo_context | review |
| planning_only | plan |
| write_patch | fix (Step F) |
| executes_untrusted_code | verify (Step F) |

See [agent-template](../../agent-template/.agent/) for starter config.
