# Slice 5.3 — Issue-Task Backfill (Bare Review/Plan)

**Status:** implemented (homelab sign-off 2026-07-06, issue #16 — `run-cca5ddc0…`)  
**Prerequisite:** [Plan MVP](architecture.md) (complete), `compile_context_pack` on issue threads (complete)  
**Recommended before:** official-engine homelab sign-off at scale; **before 6D** (with [slice-5.2-plan-quality-gate.md](slice-5.2-plan-quality-gate.md))

## Thesis

On issue threads, bare `/agent review` and `/agent plan` (no trailing task text) must not leave `command_intent.natural_language_task` empty when `context_pack.issue_text` is available. The official engine builds `Task: {natural_language_task}` and the system preamble states the task goal comes from that field only — so an empty task string produces hollow model output even when the issue body is present in `Repository context`.

This is a **CT103 dispatch / intent wiring** problem, not a CT104 parse problem.

## Problem (observed)

| Homelab | Command | Symptom |
|---------|---------|---------|
| Issue #13 | `/agent plan` (bare) | `input_job.json`: `natural_language_task: ""`; `plan_result.json`: empty scope/steps; WI emitted; fix blocked |
| Issue #14 | `/agent review Verify whether hello.md…` | Explicit task present — review still returned `(none)` findings (model quality; separate from this slice) |
| Issue #14 | `/agent plan Create hello.md…` | Explicit task present — plan had human workflow steps but **no** `steps[].files` (handled by **5.2**, not this slice) |

Root cause for #13 (confirmed on CT104 artifacts):

```text
intent_parser: bare review/plan -> natural_language_task=""
dispatch:      context_pack.issue_text populated
official_engine user_prompt: "Repository context: ... issue body ... \n\nTask: "
system preamble: "Your task goal comes from command_intent.natural_language_task only."
```

Issue text is in context but explicitly deprioritized relative to an empty authoritative task field.

## IssueTaskBackfill

Run in `build_rlm_job` (or immediately after `compile_context_pack`) when dispatching review/plan jobs.

| Condition | Action |
|-----------|--------|
| `kind` in `review`, `plan` | Candidate for backfill |
| `natural_language_task` is empty or whitespace | Attempt backfill |
| `trigger_context.issue_number` is set | Use issue-thread context |
| `context_pack.issue_text` non-empty | Set task from issue body |

### Backfill text rules

1. Prefer issue **body** over title; strip leading `# title` markdown line if duplicated.
2. Truncate to the same budget used for issue text in context pack (do not exceed existing caps).
3. Do **not** overwrite a non-empty `natural_language_task` from explicit comment text (e.g. `/agent plan Create hello.md…`).
4. Persist backfilled value on the dispatched `RLMJob.command_intent` so artifacts reflect what the worker actually used.

### Optional prompt alignment (same slice)

In `build_plan_system_preamble` / `build_review_system_preamble`, clarify that when `natural_language_task` is empty on an issue thread, the `--- issue ---` section in context is the task source. Prefer backfill in dispatch so `Task:` is never empty when issue text exists.

## Implementation

**Files (expected):**

- `src/agent_control/workflows/dispatch.py` — backfill after `compile_context_pack`, before `RLMJob` construction
- `src/agent_control/intent_parser.py` — docstring note: bare commands rely on 5.3 backfill on issue threads
- `tests/test_dispatch_issue_task_backfill.py` — bare plan/review on issue vs PR-only / empty issue

## Acceptance criteria

1. Bare `/agent plan` on issue #N with body text → dispatched job has non-empty `natural_language_task` matching issue body (truncated).
2. Bare `/agent review` on same issue → same backfill behavior.
3. `/agent plan explicit task here` → explicit task wins; no overwrite.
4. Issue-less trigger (if any) → no backfill; behavior unchanged.
5. Homelab replay: issue shaped like #13 → plan produces scoped steps more often (model-dependent; **5.2** still required when files missing).

## Out of scope

- Requiring task text on bare commands (fail-closed) — optional future policy
- Fix/plan approval scoping (**6A** / **5.2**)
- Model prompt simplification (**5.1** Phase 4 / Slice 5 Phase 7)
- Inferring `steps[].files` from prose summaries (**5.2**)

## Related

- [slice-5.2-plan-quality-gate.md](slice-5.2-plan-quality-gate.md) — steps without `files[]` still not fixable
- [slice-5.1-engine-reliability.md](slice-5.1-engine-reliability.md)
- [slice-6d-branch-push-pr.md](slice-6d-branch-push-pr.md) — homelab sign-off after 5.2 + 5.3 recommended
- [POLICY_GATES.md](POLICY_GATES.md)
