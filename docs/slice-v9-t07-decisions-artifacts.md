# Slice V9 T07 -- Decisions + artifact dispositions

**Status:** Deploy gate -- 2026-07-22 (code + docs + tests landed; CT103/CT104
deploy-verify owed before Done, per the established wave pattern)
**Epic:** V9 Agent Observatory ([boss-ledger-v9.md](handoff/boss-ledger-v9.md))
**Depends on:** T03 (done, tip `dae78e3`)
**Hard gate:** H5 -- artifact trust; H1 -- safe-display before store/stream/UI (decision-scoped)

## Goal

Replace the two T04 placeholders on the five-panel Observatory page with real
content: panel 3 ("Decisions and evidence") renders structured
`agent.control_decision` events through a dedicated, curated
`observe_decision.v1` contract that can never leak chain-of-thought/internal
reasoning, and panel 5 ("Artifacts") offers a redacted text view and a
redacted download copy for a session's own `SessionArtifactRef`-backed
artifacts once every trust gate passes -- while the original artifact bytes
remain undownloadable by design.

## What shipped

1. **`agent_control/observe/decisions.py`** (new module) -- the
   decision-scoped safe-display choke point, sibling to `safe_display.py`:
   - `sanitize_decision_metadata` -- allowlist-only extraction of exactly
     four `ControlDecision.metadata` sub-keys (`why`, `evidence`,
     `alternatives_rejected`, `remaining_uncertainty`); every other key,
     including one that is itself chain-of-thought-shaped by name, is
     withheld by name only via `withheld_metadata_field_names`.
     `is_chain_of_thought_like_name` is a defense-in-depth keyword guard
     applied to both unknown keys and known keys that happen to look
     reasoning-shaped.
   - `build_decision_from_raw_event` / `list_decisions_for_run` /
     `decisions_panel_view` -- read the raw per-project ledger directly
     (`agent_control.events.load_project_events`), never through the
     generic `observe.sqlite` projection (which correctly reduces
     `agent.control_decision.metadata` to `metadata_only` for the *generic*
     stream -- this module's own allowlist is a separate, additive
     surface, not a widening of that classification).
   - `ObserveDecisionV1` has no `chain_of_thought` field, by construction;
     strings/lists are capped (500 chars / 20 items / 300 chars per item).
2. **`agent_control/observe/artifacts.py`** (new module) -- the three
   artifact dispositions (`metadata_only` / `redacted_text_view` /
   `downloadable_redacted_copy`), most to least conservative, with H5's
   full trust-gate chain:
   - `artifact_id_for` / `resolve_artifact_ref` -- an opaque, stable id
     derived only from `session_id` + `artifact_type` + `digest`; the
     request never supplies, and this module never derives, a filesystem
     path -- resolution always goes back through the session's own
     `SessionArtifactRef` entries.
   - Path gate (containment under `agent_state_root` after full symlink
     resolution) + explicit symlink gate + size gate (cap and exact match
     to the persisted `SessionArtifactRef.byte_size`) + MIME gate
     (`.json` suffix only) + hash gate (sha256 digest match) -- any single
     gate failure degrades to "not available" (`ArtifactGateError`,
     generic `reason_code`, never surfaced to the HTTP caller as anything
     but a plain 404).
   - `build_redacted_copy` -- recursive redaction reusing
     `safe_display.is_prohibited_field_name` for secret-shaped keys, long
     strings truncated; always a freshly re-serialized JSON value, never
     the original bytes.
   - `artifact_disposition_rows` -- panel 5 view-model, one row per
     `SessionArtifactRef` (`memory_preflight`, `context_packet`,
     `recursive_context`, `verification`), always `metadata_only` in the
     listing itself, with `text_view_available`/`download_available`
     advisory flags (the routes re-run every gate again per request; the
     probe is UI-only, never trusted as an authorization decision).
3. **Routes** (`agent_control/observe/routes.py`) -- two new run_id-keyed
   routes, same auth matrix as every other Observatory route:
   - `GET /observe/sessions/{run_id}/artifacts/{artifact_id}/view` --
     server-rendered redacted text view (`artifact_redacted_view.html`,
     new template).
   - `GET /observe/sessions/{run_id}/artifacts/{artifact_id}/download` --
     redacted JSON download, generic filename
     (`{artifact_type}-redacted.json`), `Content-Disposition: attachment`.
   - `observe_session_page` now wires panel 3 to
     `decisions.decisions_panel_view` and panel 5 to
     `artifacts.artifact_disposition_rows`, replacing the T04 placeholders
     while staying backward compatible (a session with zero decisions
     still shows the pre-existing "ships in T07" placeholder text).
4. **`session_detail.html`** -- panel 3 renders a decision table
   (kind/decision/why/evidence/alternatives_rejected/remaining_uncertainty/
   recorded, auto-escaped) with a `withheld: [...]` row when metadata was
   withheld; panel 5 adds a "Redacted view" column with view/download links
   only when each disposition is currently available, plus updated
   copy explaining the default-metadata-only / fail-closed trust-gate
   model.
5. **Tests** -- `tests/test_v9_t07_decisions.py` (17 tests) and
   `tests/test_v9_t07_artifacts.py` (21 tests): allowlist extraction and
   chain-of-thought withholding (incl. a known key name that is itself
   chain-of-thought-shaped); full decision-build contract and rejection of
   malformed/wrong-type events; run-scoped ordering; every trust gate
   (digest/size/MIME/missing-file/symlink/path-escape) fails closed; the
   redacted view/download never contain the original secret value or the
   original bytes; opaque artifact ids never resolve a forged/path-shaped
   value to a file (an escape-attempt URL segment 404s); auth is enforced
   on both new routes; end-to-end page rendering never leaks
   `chain_of_thought`/unrelated metadata values or unescaped hostile
   content.

## Explicit non-goals honored

- No raw artifact download anywhere in this module or its routes -- every
  content-bearing disposition redacts first; there is no code path that
  returns `SessionArtifactRef`'s original bytes.
- No change to `observe.sqlite`'s generic `metadata_only` classification of
  `agent.control_decision.metadata` (T01/T02) -- `decisions.py` is an
  additive, separately-gated read path over the raw ledger, not a widening
  of the generic projection's contract.
- No new artifact kinds beyond the four `SessionArtifactRef`-typed
  attributes `AgentSession` already exposes.
- CT102 CI channel ingestion (T08) is a separate ticket; this slice does
  not touch `agent.fix_ci_*`/`agent.verification_*` events.

## Done criteria (after CT103/CT104 deploy-verify)

- `ruff check .` clean; full test suite passing (see "Verification" below)
- CT103 (+CT104) deploy-verify: CI green on the pushed tip, `/readyz`
  unchanged, panel 3/5 render real content for a session with recorded
  decisions/artifacts and the pre-existing placeholders for one without,
  no raw artifact bytes reachable from any route

## Verification

```text
.venv/bin/ruff check .          # All checks passed! (tracked files)
.venv/bin/python -m pytest -q tests/test_v9_t07_decisions.py tests/test_v9_t07_artifacts.py
                                 # 38 passed
.venv/bin/python -m pytest -q   # 890 passed (full suite, incl. T08)
```

New test files: `tests/test_v9_t07_decisions.py` (17 tests),
`tests/test_v9_t07_artifacts.py` (21 tests).
