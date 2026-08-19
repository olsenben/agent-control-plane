# Slice: VExp W1-A — Lexical evidence provider

**Status:** implemented (provider only; builder not wired)
**Epic:** Verified Experience Control Plane (WAVE 1)
**Hard gate:** missing `rg` is `ProviderResult.status=unavailable` with empty evidence (`diagnostics.reason=rg_unavailable`); SHA mismatch is `status=error`; diagnostics never become `EvidenceItem`s
**ADR:** proposed by integration owner (do not append to V10 ledger)

## Goal

Replace ad hoc v1 `rg` search-hit collection with `LexicalEvidenceProvider.query(snapshot, EvidenceQuery) -> ProviderResult` over an exact-SHA workspace. Frozen query normalization lives in this slice, not in `EvidenceQuery`.

## Read first

- `EPIC_verified_experience_control_plane.md` WAVE 1 / W1-A
- `src/agent_shared/models/evidence_query.py` (`ProviderResult`, `EvidenceQuery.query_text`, `compute_evidence_item_id`)
- `src/agent_shared/protocols/context.py` (`RepositoryEvidenceProvider`)
- `src/agent_control/context/repo_snapshot.py` (`from_eval`)
- `src/agent_control/graph/context_pack.py` (`_ripgrep_hits` — copy/adapt only)
- `tests/fixtures/vexp_mini_repo/`

## Allowed touch area

- `src/agent_control/context/providers/lexical.py`
- `src/agent_control/context/providers/rg.py`
- `tests/test_lexical_provider.py`
- this slice doc

## Avoid touching

- `providers/__init__.py`, `indexes/`, `builder.py`, `workspace.py`
- `graph/store.py`, `graph/context_pack.py`
- `eval_dispatch.py`, `official_engine.py`
- `protocols/context.py`, `evidence_query.py`, `context_pack_v2.py`, `v1_adapter.py`
- `maintenance-evals`

## Frozen query normalization

Owned by `normalize_query_terms` in `lexical.py`. Inputs are `query_text`, `failure_signature`, `mentioned_paths`, and `mentioned_symbols` only (never `task_text`).

1. **Preserved literals (first-seen, cap applies):** `mentioned_paths`, then `mentioned_symbols`, then quoted `'...'` / `"..."` spans from `query_text` then `failure_signature`. Backslashes become `/`. These bypass stopwords and `MIN_TERM_LEN`.
2. **Token normalization:** remaining text is scanned with `[A-Za-z_][A-Za-z0-9_]*`, casefolded, then filtered by `STOPWORDS` and `MIN_TERM_LEN` (2).
3. **Max term count:** `MAX_TERM_COUNT = 8`. First-seen unique keys (`casefold`) win; later duplicates drop.
4. **Stopwords:** frozen `STOPWORDS` frozenset in `lexical.py` (function words only; identifiers such as `foo` / `AssertionError` are kept).
5. **Search:** one `rg --json --sort path --fixed-strings --ignore-case` invocation with `-e` per term. Empty terms after normalization is `status=ok` and `evidence=[]` (not `rg_unavailable`).
6. **Evidence sort / tie-break:** unique by `(path, line_number)`; order `(path, line_number, line_text)`; then cap `MAX_EVIDENCE_ITEMS = 24`.
7. **Snippets:** truncated to `DEFAULT_SNIPPET_CHARS = 240` (optional keyword-only `snippet_chars` on the implementation; Protocol signature unchanged; no `EvidenceBudget` on this seam). Identity `normalized_fact` uses the untruncated stripped line.

## Inputs / contracts

- Recheck `git rev-parse HEAD` against `snapshot.target_sha` at entry. Mismatch: `status=error`, `evidence=[]`, `diagnostics.reason=sha_mismatch`. Never git checkout / clone / fetch.
- Missing `rg` (`shutil.which("rg")` is None): `status=unavailable`, `diagnostics.reason=rg_unavailable`, `evidence=[]`. No `EvidenceItem` for this diagnostic.
- Present `rg` with zero hits: `status=ok`, `evidence=[]`. Distinct from unavailable.
- `EvidenceItem.id` via `compute_evidence_item_id(snapshot.snapshot_id, provider="lexical", evidence_type="rg_hit", path_or_node=rel_path, normalized_fact="{line}:{line_text}")`.
- `source` is `lexical.rg`. No embeddings.

## Deliverables

- `LexicalEvidenceProvider` + ripgrep helper
- unit tests against a local git copy of `vexp_mini_repo` (tests do not call the production workspace materializer)
- this slice doc

## Acceptance tests

1. Same `EvidenceQuery` twice against `from_eval` of a copied fixture repo yields the same ordered ids.
2. Monkeypatch `shutil.which` so `rg` is missing: `status=unavailable`, empty evidence.
3. Snapshot `target_sha` not equal to workspace HEAD: `status=error`, `reason=sha_mismatch`.
4. Zero hits with `rg` present: `status=ok`, empty evidence.
5. Quoted path / mentioned symbols survive normalization; stopwords do not.

## Invariants

- Exact-SHA isolation; provider never mutates git HEAD
- `rg_unavailable` is diagnostics, never `current_evidence`
- CT102 remains authoritative (unchanged this slice)
- no embeddings; memory / recursion / 2070 / repair remain off

## Handoff

- Import: `from agent_control.context.providers.lexical import LexicalEvidenceProvider`
- Test command: `pytest tests/test_lexical_provider.py -q`
- Known gaps: not wired into ContextBuilderV2 / dispatch
- Merge conflicts likely: none expected (`providers/__init__.py` left untouched)
