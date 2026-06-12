# Agent configuration (`.agent/`)

Repo-local agent policy loaded from the **protected base branch** only.

## Required files (write flows)

- `.agent/agent-config.yml`
- `.agent/agents.yml`
- `.agent/flows.yml`

## Inspect bootstrap (allowlisted repos)

Missing `.agent/agent-config.yml` on allowlisted repos uses `platform_default` inspect policy with warnings in artifacts.

## Flow risk classes

| Class | Flows |
|-------|-------|
| read_only | inspect, explain |
| read_only_with_repo_context | review |
| planning_only | plan |
| write_patch | fix (Step F) |
| executes_untrusted_code | verify (Step F) |

See [agent-template](../../agent-template/.agent/) for starter config.
