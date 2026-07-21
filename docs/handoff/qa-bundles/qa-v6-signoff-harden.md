# QA V6 sign-off harden — patch bundle

**Schema:** operator patch bundle (not `patch-bundle.v1` agent artifact)  
**Date:** 2026-07-21  
**Against tip:** `61a0e7e` (V6 epic complete docs)  
**Unified diff:** [qa-v6-signoff-harden.patch](qa-v6-signoff-harden.patch)

## Purpose

Close critical / high QA failures found while driving the post-V6 QA tickets against the approved sign-off contract.

## Included fixes (F-01 … F-05)

| Failure | Change |
|---------|--------|
| F-01 Observatory open | `observe/auth.py`; auth on list/page/events/artifacts/SSE; `Last-Event-ID`; mid-stream re-check; `OBSERVE_REQUIRE_AUTH` / `OBSERVE_SHARED_TOKEN` |
| F-02 Shadow exclude | High risk → `flag` only; trust class immutable; `assessment_unavailable()` |
| F-03 Status rank | Explicit FSM transitions; terminals absorbing; sequence + transition guards |
| F-04 Auth fail-open | `check_user_repo_permission` fail-closed when token/API unavailable |
| F-05 Eval missing artifact | `EvalBundleError`; `authenticity: integrity_only` in manifest |

## Files

```text
src/agent_control/observe/auth.py                 (new)
src/agent_control/observe/routes.py
src/agent_control/observe/comment_projection.py
src/agent_control/security/injection_scanner.py
src/agent_control/authorization.py
src/agent_control/eval_export.py
src/agent_control/config.py
tests/test_v6_t02_comment_projection.py
tests/test_v6_t03_observatory.py
tests/test_v6_t06_injection_shadow.py
tests/test_v6_t08_eval_export.py
docs/handoff/qa-v6-ledger.md
```

## Apply

```bash
cd ai-sdlc-lab/agent-control-plane
git apply docs/handoff/qa-bundles/qa-v6-signoff-harden.patch
# or work from working tree — changes already present when authored
.venv/bin/ruff check .
.venv/bin/pytest -q tests/test_v6_t01_trace.py tests/test_v6_t02_comment_projection.py \
  tests/test_v6_t03_observatory.py tests/test_v6_t04_gateway.py \
  tests/test_v6_t05_authorization.py tests/test_v6_t06_injection_shadow.py \
  tests/test_v6_t07_nl_invocation.py tests/test_v6_t08_eval_export.py
```

## Homelab note

Set `OBSERVE_SHARED_TOKEN` (or Gitea user bearer with repo read) on CT103 before relying on Observatory. Default `OBSERVE_REQUIRE_AUTH=true` fails closed without credentials.

## Not in this bundle (residual)

F-06 T07 production wire · F-07 durable budget · F-08 comment PATCH matrix · F-09 DUR suite · F-10 CI↔projection · F-11 approval binding N01–N08 · F-12 ledger-sequence projection sort

See [qa-v6-ledger.md](../qa-v6-ledger.md).
