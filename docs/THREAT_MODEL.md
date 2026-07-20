# Threat model and risk tags

Policy violation taxonomy derived from the [MIT AI Risk Repository](https://airisk.mit.edu/) (777 risks, 43 taxonomies). Every CT103 event should carry searchable `risk_tags` for governance history — not ad hoc logs.

See [POLICY_GATES.md](POLICY_GATES.md) for enforcement.

## Policy violation categories

| Tag | Domain | Description | Typical gate |
|-----|--------|-------------|--------------|
| `prompt_injection` | AI system safety | Untrusted content manipulates agent behavior | Preamble + tool policy; block on high confidence |
| `secret_exposure` | Privacy/security | Credentials or tokens in output/logs | Redactor; deny comment post |
| `unsafe_shell_command` | Malicious misuse | Destructive or privileged shell | Sandbox policy; Risk 2+ only |
| `destructive_git_operation` | AI system safety | Force push, hard reset, branch delete | Block always on protected refs |
| `unapproved_network_call` | Privacy/security | Egress outside allowlist | Tool registry deny |
| `dependency_supply_chain_risk` | Privacy/security | Unpinned or suspicious dependency change | Flag in review; block auto-merge |
| `hallucinated_file_reference` | AI system safety | Model cites non-existent paths | Schema validation; graph cross-check |
| `repeated_failed_fix` | Human-computer interaction | Same issue/file failed N times | Memory-as-governance; require human |
| `out_of_scope_issue` | Human-computer interaction | Command outside repo/issue scope | Allowlist + intent parser |
| `capability_spoofing` | Privacy/security | Worker claims permissions it lacks | AgentFacts-lite (`agentctl agentfacts check`) |
| `false_verification_confidence` | AI system safety | Model claims success without CI | Verification invariant |
| `graph_bypass` | AI system safety | Review/plan skipped graph consultation | Require blast-radius in output |
| `architecture_drift` | AI system safety | ADR declares X; graph shows Y | `agentctl graph drift` (fail-soft; V5 T04) |

## Event shape (target)

```yaml
event_type: agent.run_completed
risk_class: 1
risk_tags:
  - hallucinated_file_reference
policy_decision: allow
run_id: run-abc123
```

## Prompt injection (layered)

1. Untrusted-data preamble in every repo-context prompt
2. Tool registry least-privilege per risk class
3. CT103 policy gate before dispatch
4. Secret redactor on outputs
5. No write tools on Risk 0/1

Tests: `tests/test_prompt_injection.py`.

## Zero-trust agent access (NANDA-inspired)

Before MCP/A2A protocol glue:

- Each CT104 worker role has explicit `commands_allowed`, `repo_access`, `can_write_*` flags
- CT103 records AgentFacts-lite at repo tip (`agent-facts.json`); `agentctl agentfacts check` fails on unsigned/stale/diverged cards
- Cross-protocol interoperability only after identity discipline exists

## MCP / A2A attack surface

When read-only MCP state server is added:

- No write, shell, git push, or state mutation tools
- Bound response sizes; schema-validate outputs
- Log all tool calls with `risk_tags`
- MCP reads projections, not raw untrusted comments

## Human oversight triggers

Force `human.approval_required` or block dispatch when:

- Risk class >= 2 without approval event
- `repeated_failed_fix` on same `(repo, issue, file)`
- `secret_exposure` detected in session output
- `destructive_git_operation` requested
- Risk 3 command without explicit override

## Related

- [security.md](security.md)
- [POLICY_GATES.md](POLICY_GATES.md)
- [EVALS.md](EVALS.md)
