# Slice: VExp W1-B — Python symbol index

**Status:** implemented (Python-first index + provider; builder not wired)
**Epic:** Verified Experience Control Plane (WAVE 1)
**Hard gate:** `language_unsupported` is `ProviderResult.status` / `diagnostics.reason`, never an `EvidenceItem` or `current_evidence` field
**ADR:** proposed by integration owner (do not append to V10 ledger)

## Goal

Ship an exact-SHA, parser-neutral Python symbol index and map `SymbolEvidenceProvider.query` onto `ProviderResult` evidence items with stable ids.

## Read first

- `EPIC_verified_experience_control_plane.md` W1-B / WAVE 1
- `src/agent_shared/models/evidence_query.py` (`ProviderResult`, `EvidenceQuery`, `compute_evidence_item_id`)
- `src/agent_control/context/repo_snapshot.py` (`from_eval` HEAD check)
- `src/agent_control/graph/extractors/python_imports.py` (Tree-sitter setup pattern)
- `tests/fixtures/vexp_mini_repo/` (`src/pkg/foo.py` declares `foo`; `src/pkg/bar.py` references it)

## Allowed touch area

- `src/agent_control/context/indexes/python_symbols.py`
- `src/agent_control/context/providers/symbols.py`
- `tests/test_symbol_provider.py`
- this slice doc

## Avoid touching

- `providers/__init__.py`, `indexes/__init__.py` (import by module path)
- `lexical.py`, `builder.py`, `workspace.py`, `graph/store.py`, `mcp/queries.py`
- `eval_dispatch.py`, `protocols/context.py`, `evidence_query.py`, `python_imports.py`
- `agent_workers/compilers` `compile_symbol_index` stub
- retriever, applicability, repair, episode, or `state_predicate` Protocols

## Inputs / contracts

- Facade: `find_symbol`, `symbols_in_file`, `references_to`, `symbol_signature` (Python first; Tree-sitter preferred).
- Regex `def`/`class` + identifier scan is the fallback when the parser cannot be constructed. Fallback still returns `status=ok` with evidence; diagnostics may include `parser=regex_fallback`.
- `query` uses `EvidenceQuery.mentioned_symbols` and identifier tokens from `query_text`.
- Recheck `git rev-parse HEAD == snapshot.target_sha` on every query. Never `git checkout` / reset / mutate.
- SHA mismatch -> `status=error`, `diagnostics.reason=sha_mismatch`, `evidence=[]`.
- No `.py` files, or query `mentioned_paths` that are all non-Python -> `status=unsupported`, `diagnostics.reason=language_unsupported`, `evidence=[]`. Mixed repos may still index `.py` files when the request is not a non-Python-only path.
- `EvidenceItem.source` is `symbol.declaration` or `symbol.reference`. Ids from `compute_evidence_item_id`; `normalized_fact` includes `snapshot.target_sha` and `index_generation`.
- Do not call MCP `find_callers` (file-import reverse edges, not symbol callers).

## Deliverables

- implementation: Python symbol index + `SymbolEvidenceProvider`
- unit tests: `tests/test_symbol_provider.py`
- this slice doc
- telemetry: none this slice

## Acceptance tests

1. Git-init copy of `vexp_mini_repo`: `find_symbol("foo")` hits `src/pkg/foo.py`.
2. `symbols_in_file("src/pkg/foo.py")` and `symbol_signature` return `def foo`.
3. `references_to` includes `src/pkg/bar.py`.
4. `query(mentioned_symbols=["foo"])` maps to `EvidenceItem`s with non-empty ids; declaration and reference sources present.
5. Non-Python-only workspace (or non-`.py` query path) -> `status=unsupported`, empty evidence.
6. Snapshot `target_sha` != workspace HEAD -> `status=error`.
7. Query does not change `HEAD` or porcelain status.

## Invariants

- CT102 remains authoritative (unchanged this slice)
- exact-SHA isolation; providers never checkout
- diagnostics never become model-visible evidence
- no `state_predicate`
- no MCP `find_callers`

## Parser fallback

If `tree_sitter` / `tree_sitter_python` cannot be imported, the index walks `def`/`class` lines and identifier uses with regex. Provider status remains `ok` when Python files exist and HEAD matches.

## Handoff

Report:

- files changed: listed under Allowed touch area
- interfaces implemented: `PythonSymbolIndex` facade + `SymbolEvidenceProvider.query -> ProviderResult`
- test command: `pytest tests/test_symbol_provider.py -q`
- known gaps: Python only; callers/callees recorded only as call-kind references; builder not wired
- merge conflicts likely: none expected (`indexes/__init__.py` / `providers/__init__.py` left untouched)
