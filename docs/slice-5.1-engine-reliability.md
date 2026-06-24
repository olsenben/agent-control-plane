# Slice 5.1 — Engine Reliability / Structured-Output Failure Handling

**Status:** planned  
**Prerequisite:** [slice-5-structured-output-hardening.md](slice-5-structured-output-hardening.md) (complete), [slice-6c-closed-world-diff-gate.md](slice-6c-closed-world-diff-gate.md) fake acceptance (recommended order)  
**Blocks:** [6D branch push + PR](#related) — **mandatory before any remote write**

## Thesis

Slice 5 fixed common shape errors at the Pydantic boundary. Homelab issue #9 showed the remaining gap: Ollama can accept `format: schema` and still return markdown prose. Parser patches alone will not close this. Add a **structured-output client abstraction** and ensure **every run ends in a reportable terminal artifact** — even parse failures.

**Cross-cutting reliability gap A:** engine I/O reliability and failure visibility.

## Problem (observed)

| Symptom | Impact |
|---------|--------|
| No JSON blob after schema/json completion | Repair retry never runs (ValidationError-only path) |
| Prose instead of FixResult JSON | Fix run fails; approval already consumed on enqueue (6B) |
| Parse fail in `rlm_root` | RQ failed job only — no Gitea comment, no inbox, no ledger event |
| Model echoes CT103-owned fields poorly | Token waste + shape errors |

## StructuredOutputClient abstraction

Do **not** rewrite the stack around a framework. Use a dedicated adapter **only inside** `official_engine.py` / `model_output.py`.

```text
StructuredOutputClient:
  provider: native_ollama_schema   # current path
  provider: instructor_ollama      # Pydantic-first extraction + retries
  provider: fake                   # existing test/offline path
```

Keep existing: Pydantic validation, CT103-owned premerge (`premerge.py`), normalizers, finalize paths.

### Library path (dependency acceptance rule applies)

| Priority | Library | Role |
|----------|---------|------|
| 1 | **Instructor** | Pydantic models, automatic validation, retries; Ollama/local support |
| 2 | **Outlines** (if Instructor insufficient for fix) | Grammar / JSON Schema constrained generation |
| — | **Tenacity** | Non-LLM transient retries only if needed; Instructor covers LLM retries |

Spike note required under `docs/research/tool-spikes/` before adding runtime dependencies.

### Ollama requirements (all providers)

- `stream: false` for single-shot completions
- Explicit prompt instruction to respond in JSON (JSON mode still requires prompt instruction per Ollama docs)
- Log which provider/mode was used (preserve in trace — fix runner overwrite noted in Slice 5)

## Implementation phases

### Phase 1 — Missing-JSON retry (highest priority)

When `extract_json_blob` fails after schema/json completion:

1. One stricter retry: `format: "json"`, prompt: "JSON object only, no markdown"
2. Extend repair path for **missing JSON**, not only `ValidationError`
3. Max one JSON retry + one repair retry (same bounds as Slice 5)

### Phase 2 — Instructor-backed provider

- Add `instructor_ollama` provider behind env flag (e.g. `STRUCTURED_OUTPUT_PROVIDER=instructor_ollama`)
- Wire for plan, review, fix kinds
- Fall back to `native_ollama_schema` on provider init failure

### Phase 3 — Parse failure must never skip reporting

**Every agent run ends in a reportable terminal status:**

```text
completed | failed_parse | failed_apply | failed_gate | failed_infra
```

Add RQ custom exception handler for `rlm-root`:

```text
on_worker_exception(job, exc):
  locate run_id / artifact root
  write error.json
  write parse_failure.json if relevant
  enqueue worker-report failure path
  post Gitea failure comment when trigger context exists
  write inbox/ct104-results/{run_id}.json with status=failed
```

RQ supports custom exception handlers on the worker — use them so failures are not silent in `FailedJobRegistry` only.

This is **more important than perfect model output**. Failures must be visible and ingestible.

### Phase 4 — Prompt simplification (Slice 5 Phase 7)

Once premerge owns `blast_radius`, `prior_memory_used`, and platform IDs:

- Remove model obligations to echo CT103-owned fields
- Emphasize model-authored reasoning only (findings, steps, fix edits)

### Phase 5 — Outlines evaluation (conditional)

If official-engine fix still leaks prose after Instructor + missing-JSON repair:

- Spike Outlines or grammar-constrained serving path
- Compare against fake-engine baseline on `README.md` fix scope

## Acceptance criteria

Homelab sign-off after 6C fake acceptance:

1. Induced parse failure → Gitea failure comment + inbox JSON + ledger `agent.run_failed` (or completed with failed status)
2. Missing-JSON path triggers repair or JSON retry before terminal failure
3. Instructor provider passes plan/review/fix unit tests; homelab official fix on one allowed file succeeds OR fails with full report chain (not silent RQ fail)
4. No regression in Slice 5 normalization tests
5. `MODEL_ROUTING_POLICY=fake` still works for offline/CI

## Out of scope

- Branch push / PR (6D)
- Closed-world diff gate logic (6C — gate emits `failed_gate`, not this slice)
- Replacing CT103 premerge with model echoes

## Rollback

- `STRUCTURED_OUTPUT_PROVIDER=native_ollama_schema`
- `MODEL_ROUTING_POLICY=fake` on CT104

## Related

- [slice-5-structured-output-hardening.md](slice-5-structured-output-hardening.md)
- [slice-4c-result-ingest-automation.md](slice-4c-result-ingest-automation.md) — ingest must process failure inbox events
- [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md) — parse fail reporting gap (checklist #10)
- [deploy.md](deploy.md)
