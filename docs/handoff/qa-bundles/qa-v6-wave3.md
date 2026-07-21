# QA V6 wave 3 — patch bundle

**Date:** 2026-07-21  
**Against tip:** `eda495d` (waves 1–2)  
**Unified diff:** [qa-v6-wave3.patch](qa-v6-wave3.patch)

## Purpose

Close thin residual gaps after wave 2: DUR unit matrix, ambiguous PATCH reconcile,
approval N0x mocked evaluate suite, Observatory 401/403 auth tests.

## Included fixes / coverage

| Item | Change |
|------|--------|
| PATCH reconcile | `get_issue_comment` + `_reconcile_patch_applied`; ambiguous timeout advances sequence when body matches |
| N04 base SHA | `evaluate_fix_request(..., expected_base_sha=)` fail-closed |
| N01–N06/N08 | Mocked evaluate/grant suite in `tests/test_qa_v6_wave3.py` |
| DUR-01–03/05/08 | Legacy load, idempotent append, restart projection, budget key, abandoned invocation |
| Observatory auth | Invalid shared token → 403; missing auth → 401 |

## Apply / verify

```bash
cd ai-sdlc-lab/agent-control-plane
.venv/bin/ruff check .
.venv/bin/pytest -q tests/test_qa_v6_wave3.py
```

## Remaining thin gaps

- Homelab DUR soak
- N07 approver revoked before publish (live)
- Mid-SSE revoke integration
- Real Observatory OAuth (shared token remains gate)
