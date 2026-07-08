# Slice 5.2 + 5.3 — Bundle Implementation Plan

**Status:** implemented  
**Prerequisite:** Slice 5 (complete), Plan MVP (complete)  
**Unblocks:** Official-engine homelab retry (#16+), 6D sign-off prep  
**Spec:** [slice-5.2-plan-quality-gate.md](slice-5.2-plan-quality-gate.md), [slice-5.3-issue-task-backfill.md](slice-5.3-issue-task-backfill.md)

## Double-check (2026-07-03)

| Check | Result |
|-------|--------|
| `plan_quality.py` exists | **Yes** |
| Issue-task backfill in `dispatch.py` | **Yes** |
| `PlanResult.fixable` field | **Yes** |
| WI block gated on scoped files | **Yes** — `finalize_plan_result` skips WI when not fixable |
| Hash excludes `fixable` / `quality_gate_reasons` | **Yes** — `plan_result_for_hash` |
| Homelab evidence | #13 (empty task), #14–#16 (steps without `files[]` or empty plan) |
| Fake plan E2E uses bare `/agent plan` | **Yes** — backfill assertion in `test_fake_plan_run.py` |

**Out of bundle (fast follow):** review quality gate (#15 empty review), create-file prompt tweak, 5.1 Phase 7.

---

## Bundle thesis

One PR, two layers, one homelab milestone:

```text
5.3 (CT103)  issue body → natural_language_task when bare review/plan
5.2 (CT104)  plan finalize → fixable=false when no steps[].files → no WI block
```

---

## Part A — Slice 5.3 (CT103 dispatch)

### A1. `issue_task_backfill.py`

New module: `src/agent_control/workflows/issue_task_backfill.py`

```python
def issue_body_for_task(issue_text: str) -> str:
    """Strip leading '# title' line; return body suitable for natural_language_task."""

def maybe_backfill_command_intent(
    intent: CommandIntent,
    *,
    kind: str,
    context_pack: ContextPack | None,
    issue_number: int | None,
) -> CommandIntent:
```

Rules (from spec):

- Only `kind in ("review", "plan")`
- Only when `not intent.natural_language_task.strip()`
- Only when `issue_number is not None` and `context_pack.issue_text`
- Never overwrite explicit comment remainder
- Truncate to `ISSUE_BUDGET` (4000) from `context_pack.py` — import constant, do not duplicate

### A2. Wire `build_rlm_job`

File: `src/agent_control/workflows/dispatch.py`

After `compile_context_pack`, before `RLMJob(...)`:

```python
intent = maybe_backfill_command_intent(
    intent,
    kind=kind,
    context_pack=context_pack,
    issue_number=trigger_context.issue_number,
)
```

### A3. Docstring

File: `src/agent_control/intent_parser.py` — note bare `_BARE_COMMAND_KINDS` rely on 5.3 backfill on issue threads.

### A4. Tests

File: `tests/test_dispatch_issue_task_backfill.py`

| Case | Expect |
|------|--------|
| Bare `/agent plan` + issue body in pack | `job.command_intent.natural_language_task` non-empty |
| Bare `/agent plan` + title-only Gitea shape | task = title text |
| Body-only issue text `"Do X"` | no accidental strip |
| `"## Context\nDo X"` | unchanged |
| Bare `/agent review` + issue body | same |
| `/agent plan explicit task` | explicit wins |
| Inspect bare | no backfill (not in kinds) |
| Plan + no issue_number | no backfill |

Use mocked `compile_context_pack` or minimal trigger with issue payload (pattern from `test_dispatch_payload.py`).

---

## Part B — Slice 5.2 (CT104 plan finalize)

### B1. `plan_quality.py`

New module: `src/agent_workers/rlm/plan_quality.py`

```python
@dataclass(frozen=True)
class PlanQualityResult:
    fixable: bool
    reasons: list[str]

def evaluate_plan_quality(plan: PlanResult) -> PlanQualityResult:
```

**Blocking rules** (when plan would recommend fix — always true today if steps exist or scope non-empty; simplify):

| Rule | Block if |
|------|----------|
| Steps | `not plan.steps` |
| Scoped files | no path in any `step.files` after path validation |

**Non-blocking (warn only in comment):**

- Empty `ci_hints`
- `prior_memory_used` empty when pack had prior_memory (optional warning line)

Do **not** block on blast_radius — premerge owns it.

### B2. `PlanResult` model

File: `src/agent_shared/models/plan.py`

Add:

```python
fixable: bool = True
quality_gate_reasons: list[str] = Field(default_factory=list)
```

Include in `plan_result.json` artifact. Exclude from `plan_hash` — **mandatory** pops in `plan_result_for_hash`:

```python
data.pop("fixable", None)
data.pop("quality_gate_reasons", None)
```

These fields are finalizer metadata and must not affect plan identity.

### B3. `finalize_plan_result`

File: `src/agent_workers/rlm/plan_finalize.py`

Order after `apply_path_validation`:

1. `quality = evaluate_plan_quality(validated)`
2. If not `quality.fixable`:
   - Set `fixable=False`, `quality_gate_reasons=quality.reasons`
   - **Do not** set `approval_target_id`, `plan_alias`, or `/agent fix WI-*` recommended command
   - Set `recommended_next_command` to replan hint, e.g. `/agent plan Update README.md to ...`
   - **Invariant:** `approval_target_id is None`, `plan_alias is None`, no `WI-*` in `recommended_next_command`
3. If fixable: existing WI / approval_target logic unchanged

### B4. `render_plan_comment`

File: `src/agent_workers/formatters/plan_comment.py`

When `not plan.fixable`:

- Add section `### Plan not fixable` with bullet reasons
- **Omit** `### Approval required (Risk 2)` block entirely
- Recommended next command → replan guidance

When fixable: unchanged (including WI block).

### B5. CT103 approve (optional hardening)

File: `src/agent_control/approval/service.py`

If `allowed_files` empty after plan lookup, approval already warns. Optional: if ingested `plan_result.fixable is False`, return clearer message. **Minimal scope:** rely on empty `allowed_files` + 5.2 comment; no required CT103 change for v1.

### B6. Tests

File: `tests/test_plan_quality_gate.py`

Fixtures (dict → PlanResult):

| Fixture | fixable |
|---------|---------|
| #9 empty steps | false |
| #13 empty scope/steps | false |
| #14 steps without files | false |
| Good plan with `files: ["hello.md"]` | true |
| Fake-engine-shaped plan with `files: ["README.md"]` | true |

File: `tests/test_plan_finalize_quality_gate.py` — **direct regression** for production bug:

| Scenario | Assert |
|----------|--------|
| issue_number + empty steps | `approval_target_id is None`, no WI in comment |
| steps with prose only, no `files[]` | same |
| all step files rejected by path validation | same + path validation reason |
| good plan with valid step files + issue | WI block present, IDs set |

- Not fixable → no "Approval required" in rendered comment
- Fixable → WI block present

Update `tests/test_fake_plan_run.py`:

- Assert backfilled task when bare plan + issue

---

## Part C — Integration checklist (PR)

```text
[ ] pytest -q (new + existing plan/dispatch tests)
[ ] ruff check .
[ ] Update slice-5.2 / slice-5.3 status → implemented
[ ] Update architecture.md roadmap rows
[ ] ADR if architectural-adr skill triggers (policy gate extension — likely yes)
```

---

## Files touched (expected)

| File | Change |
|------|--------|
| `src/agent_control/workflows/issue_task_backfill.py` | **new** |
| `src/agent_control/workflows/dispatch.py` | backfill wire |
| `src/agent_control/intent_parser.py` | docstring |
| `src/agent_workers/rlm/plan_quality.py` | **new** |
| `src/agent_workers/rlm/plan_finalize.py` | gate wire |
| `src/agent_shared/models/plan.py` | `fixable`, `quality_gate_reasons` |
| `src/agent_workers/formatters/plan_comment.py` | not-fixable render |
| `tests/test_dispatch_issue_task_backfill.py` | **new** |
| `tests/test_plan_quality_gate.py` | **new** |
| `tests/test_fake_plan_run.py` | adjust for 5.3 |
| `docs/slice-5.2-plan-quality-gate.md` | status |
| `docs/slice-5.3-issue-task-backfill.md` | status |
| `docs/architecture.md` | status |

---

## What this bundle does **not** fix

| Gap | Still needs |
|-----|-------------|
| Official model puts `hello.md` in summary not `files[]` with explicit task | Stricter prompt or 5.2 blocks WI (user must replan) |
| Empty review (#15) | Review quality gate (future 5.2b) |
| Create-file path not in repo context | Prompt tweak (5.1 Phase 7 or small prompt patch) |
| 6D push/PR | Homelab ops after 6B/6C pass |

---

## Verification walkthrough (after merge + deploy)

### Tier 1 — CI / local (required before deploy)

```bash
cd ai-sdlc-lab/agent-control-plane
.venv/bin/ruff check .
pytest -q tests/test_dispatch_issue_task_backfill.py tests/test_plan_quality_gate.py tests/test_fake_plan_run.py
pytest -q
```

### Tier 2 — Deploy

| Host | Action |
|------|--------|
| CT103 | Pull, rebuild/restart `worker-state` + API |
| CT104 | Pull, rebuild/restart `worker-rlm-root` + `worker-report` |

No new env vars for 5.2/5.3.

### Tier 3 — Unit behavior on homelab (#16)

**Test 5.3 — bare plan**

1. New comment on #16: `/agent plan` (bare, no trailing text)
2. Inspect CT104: `input_job.json` → `natural_language_task` matches issue goal text (non-empty)
3. Plan may still be not fixable if model omits `files[]` — that is 5.2 working

**Test 5.2 — hollow plan blocked**

1. If model returns empty steps (like `run-87f0892…`):
   - Plan comment has **Plan not fixable** section
   - **No** `### Approval required (Risk 2)` block
2. If user approves anyway on old WI pattern: `Allowed files: (none)` still blocks fix (existing 6A)

**Test 5.2 — good fake plan**

1. Set `MODEL_ROUTING_POLICY=fake` on CT104; restart
2. `/agent plan Create hello.md…` (explicit)
3. Plan shows `(README.md)` or scoped file on step
4. Approve → `Allowed files: README.md` (fake uses first source)
5. `/agent fix WI-*` → enqueue, patch, 6C gate

### Tier 4 — Sign-offs (homelab 2026-07-06, issue #16)

| Item | Status | Evidence |
|------|--------|----------|
| **4C** | **Pass** (cron still active) | inbox `.processed`, ledger events; disable cron to prove Redis-only |
| **5.3** | **Pass** | `run-cca5ddc0…` — `natural_language_task` backfilled |
| **5.2** | **Pass** | `run-cca5ddc0…` — Plan not fixable, no WI block |
| **6B/6C** | **Pass** (weak content) | `run-cfdb799a…`, `run-0ef720ec…` — gate pass, empty `patch.diff` |
| **5.1 failure path** | **Not re-run** | Official fix completed; no induced parse failure |
| **6D** | **Pending** | issue #17 |

### Tier 5 — Official engine (after fake path green)

1. `MODEL_ROUTING_POLICY=official` on CT104
2. Replan on #16 with explicit `files: ["hello.md"]` language
3. **Pass criteria:** plan fixable **or** 5.2 clearly says not fixable (no false-positive WI)
4. Do not approve until `(hello.md)` appears on a step

---

## Suggested PR title

`feat: slice 5.2 plan quality gate + 5.3 issue-task backfill`

## Suggested merge order

Single PR; deploy **CT103 first** (5.3 backfill), then **CT104** (5.2 quality gate). Behavior is only fully corrected once both are deployed. Run Tier 3 before re-attempting official #16.
