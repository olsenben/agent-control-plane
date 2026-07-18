# Queue reference

## Flow queues (dispatch)

| Queue | Worker | Purpose |
|-------|--------|---------|
| state | worker-state (CT103) | State reduction |
| rlm-root | worker-rlm-root (CT104) | Agent session root |
| rlm-child | worker-rlm-child | Serialized child investigations |
| verify | worker-verify | Patch verification coordinator |
| report | worker-report (CT104) | Final report + result intake |
| ci-repair | worker-ci-repair (CT104) | Slice 6F.2 sandboxed CI repair |

Legacy GPU-tier queues (`rlm-3080`, etc.) are **deprecated** — do not enqueue from dispatch.

## Retry policy

| Queue | Retries | No retry |
|-------|---------|----------|
| rlm-root | 1 | Schema/validation errors |
| report | 3 | Malformed artifacts |
| ci-repair | 1 | Lease expiry allows safe retry |

Optional `QUEUE_PREFIX` env prefixes all queue names.

## CLI

```bash
agentctl queue info
agentctl queue enqueue-rlm-test --project owner/repo --intent inspect --task "why idle"
```
