# Slice 5 — Structured Output Boundary Hardening

**Status:** complete (homelab sign-off 2026-06-21 UTC)  
**Prerequisite:** Review MVP path live (inspect/review/plan dispatch + memory 4A/4B) — satisfied  
**Unblocks:** `/agent fix` (Risk 2)

## Thesis

**Strict on model-authored reasoning. Lenient on malformed echoes of CT103-owned context. Authoritative platform facts come from `context_pack`, not model JSON.**

| Model emits (validated strictly) | CT103 supplies (pre-merged, not trusted to model) |
|----------------------------------|---------------------------------------------------|
| findings, rationale | blast_radius |
| scope_summary, steps | prior_memory_used |
| assumptions, open_questions | context_sources |
| confidence | repo / issue / commit / run IDs |
| recommended_next_command | graph-derived affected tests |
| ci_hints (concrete paths only) | policy / risk metadata |

Parser-only coercion in `plan_parser.py` is a stopgap. This slice replaces whack-a-mole with a shared boundary.

## Problem

`OfficialRLMEngine` uses single-shot Ollama completion. Models return valid JSON with wrong shapes:

- `prior_memory_used`: `["run-..."]` instead of objects
- `blast_radius`: prose string instead of `BlastRadiusContext`
- (next) `findings` as strings, `steps` as strings, scalar `files_inspected`, etc.

Parse failure today:

- RQ job → failed registry (growing `rlm-root` failed count)
- No Gitea comment, no inbox JSON, no memory writeback
- `error.json` only — weak audit trail

`finalize_*` merges `context_pack` **after** parse, so CT103-owned fields cannot rescue a failed validation.

## Target pipeline

```text
raw model text
  → extract_json_blob (or markdown fallback)
  → premerge_platform_context(kind, raw_dict, context_pack)   # CT103-owned fields
  → normalize_*_dict(raw_dict)                                 # harmless coercions
  → PlanResult / ReviewResult.model_validate
  → finalize_* (path validation, comment render)
  → on ValidationError: repair_retry once (format-only, no tools)
  → on final failure: structured parse_failure artifact + RQ fail
```

Ollama structured output (`format: schema | "json"`, `stream: false`) runs **before** extract, but normalization and validation remain mandatory.

## Module layout

```
src/agent_workers/rlm/
  model_output.py      # orchestration: validate_or_repair()
  normalizers.py       # normalize_plan_dict, normalize_review_dict, shared helpers
  premerge.py          # premerge_platform_context, build_prior_memory_used_from_pack
  repair.py            # single repair retry prompt + call
  plan_parser.py       # thin: delegates to model_output for plan
  review_parser.py     # thin: delegates to model_output for review
```

Keep `extract_json_blob` in `review_parser.py` or move to `model_output.py` — one canonical extractor.

## Implementation phases (priority order)

### Phase 1 — Platform pre-merge (highest payoff)

**Files:** `premerge.py`, wire into `plan_parser` / `review_parser` or `official_engine.py`

Before `model_validate`:

**Plan**

- If `context_pack.blast_radius` has data → `raw["blast_radius"] = pack.blast_radius`
- If `context_pack.prior_memory` → `raw["prior_memory_used"] = build_prior_memory_used_from_pack(raw.get(...), pack.prior_memory)`
- Optional: `raw["context_sources"] = pack.context_sources` (for artifact audit, not in PlanResult today)

**Review**

- Same blast_radius pre-merge
- Do not pre-merge findings (model-authored)

**Tests:** `tests/test_plan_output_normalization.py`, `tests/test_review_output_normalization.py` — assert pack wins over model prose/strings.

### Phase 2 — Shared normalizers

**Files:** `normalizers.py`

Shared helpers:

- `coerce_string_list`
- `coerce_blast_radius` (structured lines → dict; prose → narrative in missing_graph_edges only when no pack)
- `coerce_prior_memory_used` (string run IDs → objects)
- `coerce_findings` (strings → minimal `ReviewFinding` objects)
- `coerce_files_inspected` (scalar → list)

Apply in `normalize_plan_dict` / `normalize_review_dict`.

Migrate existing logic from `plan_parser._normalize_*` into shared module; delete duplicates.

### Phase 3 — Tests for known production failures

Fixtures mirroring homelab errors:

| Test file | Cases |
|-----------|--------|
| `test_plan_output_normalization.py` | prior_memory string list; blast_radius prose; steps as strings; pack blast wins |
| `test_review_output_normalization.py` | blast_radius prose; findings as strings; files_inspected scalar; confidence float/string |

Run: `pytest tests/test_plan_output_normalization.py tests/test_review_output_normalization.py tests/test_plan_parser.py tests/test_review_parser.py -q`

### Phase 4 — Ollama structured output

**Files:** `official_engine.py` (`_run_single_shot`)

Progression:

1. `format = PlanResult.model_json_schema()` / `ReviewResult.model_json_schema()` when kind is plan/review
2. Fallback: `format = "json"`
3. Fallback: current unstructured completion

Requirements:

- `stream: false`
- Prompt still says "respond with JSON only" (Ollama docs)
- Feature-detect Ollama version / endpoint capability; log which mode used in `rlm_trace.jsonl`

### Phase 5 — One repair retry

**Files:** `repair.py`, called from `model_output.validate_or_repair`

Trigger only when:

- JSON extracted
- premerge + normalize ran
- `ValidationError` from Pydantic

Repair prompt (bounded):

- Return corrected JSON only
- Do not invent files, repos, run IDs, blast radius, prior memory
- Inject platform context + schema + validation errors + bad JSON excerpt
- No tool calls, no repo re-read

Max **one** retry; same model endpoint, shorter timeout acceptable.

### Phase 6 — Structured parse failure artifact

**Files:** `official_engine.py`, `runner.py`, optional `agent_shared/models/parse_failure.py`

On final validation failure, write e.g. `parse_failure.json`:

```json
{
  "schema_version": "parse_failure.v1",
  "run_id": "run-...",
  "command_kind": "plan",
  "status": "failed_structured_parse",
  "parse_errors": ["..."],
  "raw_response_excerpt": "...",
  "context_sources": ["..."],
  "blast_radius": {},
  "prior_memory_used": [],
  "recommended_next_step": {
    "command": "retry",
    "reason": "model returned invalid structured output"
  }
}
```

Populate CT103-owned fields from `context_pack`, not model output.

- Still mark RQ job failed (or completed with failed status — decide in implementation; prefer completed + failed status for ingest)
- Do **not** write normal memory records for parse failures (audit only)
- Optional: `worker-report` posts short Gitea comment: "Plan failed: structured output invalid; retry `/agent plan`"

### Phase 7 — Prompt simplification (last)

**Files:** `prompts.py`

Once pre-merge owns blast_radius and prior_memory_used:

- Remove or shorten model obligations to echo those fields
- Emphasize findings / steps / scope only
- Reduces token waste and shape errors

## Acceptance criteria

Homelab sign-off: issue on `agent-control-plane`, review `run-19a15588a6bc82d0104ee78006e4febf`, plan `run-d71996d36fca5c54e3f54cc50a4a6f35` (2026-06-21 UTC). Unit/integration: 163 tests passing.

1. Plan survives `prior_memory_used` as `["run-..."]` (with or without pack). **Unit tests**
2. Plan survives `blast_radius` as prose when `context_pack.blast_radius` exists (pack wins). **Unit + homelab** (`plan_result.json` blast matches `context_pack.json`)
3. Review survives `blast_radius` as prose when pack exists. **Unit + homelab**
4. Review survives `findings` as list of strings (coerced to minimal objects). **Unit tests**
5. CT103-owned fields pre-merged before Pydantic validation. **Homelab** (blast_radius match above)
6. Ollama requests use schema or JSON `format` when available. **Code** (`official_engine._run_single_shot`; trace field dropped by runner overwrite — see follow-up)
7. One repair retry on `ValidationError`. **Code + unit tests**
8. Final failure produces `parse_failure.json` with platform context. **Integration test**; not triggered on sign-off runs (no `parse_failure.json`)
9. RQ failed count stops growing for common shape errors (manual homelab check). **Homelab** (review + plan completed; no parse failures)
10. Tests cover plan + review normalization; at least one official-engine integration test for parse failure artifact. **Done**

## Out of scope (this slice)

- `/agent fix` dispatch or sandbox
- Memory schema changes beyond parse-failure audit logging
- New graph indexer features
- Removing markdown fallback (keep as last-resort path)

## Rollback

- Set `MODEL_ROUTING_POLICY=fake` on CT104 for offline tests
- Revert to pre-slice parsers (plan_parser ad-hoc coercions remain until slice lands)

## Related

- [RUNBOOK_REVIEW_MVP.md](RUNBOOK_REVIEW_MVP.md)
- [POLICY_GATES.md](POLICY_GATES.md)
- [architecture.md](architecture.md) — three-layer truth model
- [ct104-rlm-first-adapter-plan.md](ct104-rlm-first-adapter-plan.md)

## Review log

- 2026-06-21 — Slice scoped after homelab plan parse failures (`prior_memory_used` strings, `blast_radius` prose). Ad-hoc fix committed in `fix(plan): coerce prose blast_radius...`; superseded by this slice.
- 2026-06-21 — Slice landed (`04b0dc3` slice 5 complete, `6f74eea` lint). Homelab sign-off: review `run-19a15588…`, plan `run-d71996d3…`; no `parse_failure.json`; `plan_result.blast_radius` matches `context_pack`. `/agent fix` unblocked.
