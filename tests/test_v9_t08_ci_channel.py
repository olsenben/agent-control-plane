"""V9 T08 -- CT102 CI truth-loop (agent.fix_ci_*) into the Agent Observatory.

Covers:

- ``resolve_ci_run_id``/``resolve_ci_session_id``: additive fallbacks for the
  generic projector, scoped to ``FIX_CI_EVENT_TYPES`` only.
- ``ci_log_category``: tags the fix_ci_*/verification_* channel as ``"ci"``;
  every other event type is untagged.
- ``flatten_observation_fields``: promotes the nested ``WorkflowObservation``
  scalar fields to top-level ``observation_*`` keys for
  ``agent.fix_ci_observed`` only; a no-op for every other event.
- ``build_ci_deep_link``: only from a configured, http(s) ``gitea_base_url``
  and conservative allowlists on ``repository``/``workflow_run_id``; ``None``
  otherwise.
- ``current_ci_phase_view``: reads the canonical ``VerificationClaim``
  directly; ``None`` when absent; correct phase mapping.
- End-to-end: a real ``agent.fix_ci_observed`` ledger append (keyed by
  ``fix_run_id``, no top-level ``run_id``) is projected into observe.sqlite
  via the *existing* generic projector, tagged ``category=ci``, with a safe,
  flattened, allowlisted payload and no terminal regression to any other
  event family's classification.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_control.ci.events import (
    append_fix_ci_observed,
    append_fix_ci_repair_blocked,
    append_fix_ci_verdict_changed,
)
from agent_control.config import Settings
from agent_control.observe.ci_channel import (
    CI_CHANNEL_EVENT_TYPES,
    CI_PHASE_BY_CLAIM_STATUS,
    FIX_CI_EVENT_TYPES,
    build_ci_deep_link,
    ci_log_category,
    current_ci_phase_view,
    flatten_observation_fields,
    is_safe_repository_slug,
    is_safe_workflow_run_id,
    resolve_ci_run_id,
    resolve_ci_session_id,
)
from agent_control.observe.projector import project_ledger_event, resolve_run_id
from agent_control.observe.safe_display import safe_display_event
from agent_control.observe.store import ObserveStore, observe_db_path
from agent_control.observe.ui import current_state_view
from agent_control.session.storage import persist_session_with_run_index
from agent_control.session.verification import persist_verification_claim
from agent_control.webhook_server import create_app
from agent_shared.models.agent_session import AgentSession, SessionStatus
from agent_shared.models.ci import (
    FixCiObservedEvent,
    FixCiRepairBlockedEvent,
    FixCiVerdictChangedEvent,
    WorkflowObservation,
)
from agent_shared.models.verification_claim import VerificationClaim

PROJECT = "ai-sdlc-lab/demo-app"


def _observation(**overrides) -> WorkflowObservation:
    base = dict(
        workflow_id="ci",
        path=".gitea/workflows/ci.yaml",
        display_name="CI",
        workflow_run_id="9001",
        run_attempt=1,
        status="completed",
        conclusion="success",
        head_sha="a" * 40,
        pr_number=42,
        delivery_id="delivery-9001",
        observed_at="2026-07-22T00:00:00+00:00",
        api_verification_status="confirmed",
    )
    base.update(overrides)
    return WorkflowObservation(**base)


def _fix_ci_observed_event(**overrides) -> dict:
    body = FixCiObservedEvent(
        fix_run_id="run-t08-observed",
        repository=PROJECT,
        expected_head_commit_sha="a" * 40,
        observation=_observation(),
        delivery_id="delivery-9001",
    )
    return {
        "event_id": "evt-t08-observed-1",
        "type": "agent.fix_ci_observed",
        "source": "ct103",
        "ledger_sequence": 1,
        "recorded_at": "2026-07-22T00:00:00+00:00",
        "payload": body.model_dump(mode="json"),
        **overrides,
    }


def _seed_session(root: Path, *, run_id: str, session_id: str) -> AgentSession:
    session = AgentSession(
        session_id=session_id,
        project=PROJECT,
        repo=PROJECT.split("/", 1)[1],
        subject_kind="issue",
        subject_number=21,
        command_kind="fix",
        status=SessionStatus.RUNNING,
        run_ids=[run_id],
        correlation_id=f"corr-{session_id}",
        trace_id=f"tr-{session_id}",
        input_state_sha="a" * 64,
        head_sha="a" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        risk_tags=["needs_review"],
        invoked_by="tester",
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:05:00+00:00",
    )
    persist_session_with_run_index(root, session)
    return session


def _app(tmp_path: Path, monkeypatch, **env):
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "false")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return create_app()


# --- resolve_ci_run_id / resolve_ci_session_id -----------------------------


def test_resolve_ci_run_id_only_for_fix_ci_event_types() -> None:
    event = _fix_ci_observed_event()
    assert resolve_ci_run_id(event) == "run-t08-observed"

    other = dict(event)
    other["type"] = "agent.verification_passed"
    assert resolve_ci_run_id(other) is None


def test_resolve_ci_run_id_none_for_malformed_payload() -> None:
    event = _fix_ci_observed_event()
    event["payload"] = "not-a-dict"
    assert resolve_ci_run_id(event) is None


def test_resolve_ci_session_id_best_effort_lookup(tmp_path: Path) -> None:
    run_id = "run-t08-session-lookup"
    session_id = "sess-t08-session-lookup"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    assert resolve_ci_session_id(tmp_path, PROJECT, run_id) == session_id


def test_resolve_ci_session_id_none_when_session_missing(tmp_path: Path) -> None:
    assert resolve_ci_session_id(tmp_path, PROJECT, "run-does-not-exist") is None


# --- resolve_run_id (projector, generic path + T08 fallback) --------------


def test_projector_resolve_run_id_falls_back_to_fix_run_id() -> None:
    event = _fix_ci_observed_event()
    assert "run_id" not in event["payload"]
    assert resolve_run_id(event) == "run-t08-observed"


def test_projector_resolve_run_id_still_prefers_payload_run_id() -> None:
    event = _fix_ci_observed_event()
    event["payload"]["run_id"] = "run-explicit"
    assert resolve_run_id(event) == "run-explicit"


# --- ci_log_category --------------------------------------------------------


def test_ci_log_category_tags_the_whole_ci_channel() -> None:
    for event_type in FIX_CI_EVENT_TYPES:
        assert ci_log_category(event_type) == "ci"
    assert ci_log_category("agent.verification_passed") == "ci"
    assert ci_log_category("agent.verification_failed") == "ci"


def test_ci_log_category_none_outside_the_channel() -> None:
    assert ci_log_category("agent.session_started") is None
    assert ci_log_category("agent.control_decision") is None
    assert ci_log_category("") is None


def test_ci_channel_event_types_is_union_of_fix_ci_and_verification() -> None:
    assert FIX_CI_EVENT_TYPES <= CI_CHANNEL_EVENT_TYPES
    assert "agent.verification_passed" in CI_CHANNEL_EVENT_TYPES


# --- flatten_observation_fields ---------------------------------------------


def test_flatten_observation_fields_promotes_known_scalars() -> None:
    event = _fix_ci_observed_event()
    flattened = flatten_observation_fields(event)
    payload = flattened["payload"]
    assert payload["observation_workflow_run_id"] == "9001"
    assert payload["observation_status"] == "completed"
    assert payload["observation_conclusion"] == "success"
    assert payload["observation_pr_number"] == 42
    # Original nested blob is untouched (still present) -- classification
    # simply never reads it (default-deny on unlisted top-level keys).
    assert payload["observation"]["workflow_run_id"] == "9001"


def test_flatten_observation_fields_is_a_noop_for_other_event_types() -> None:
    event = {"type": "agent.fix_ci_verdict_changed", "payload": {"fix_run_id": "r1"}}
    assert flatten_observation_fields(event) is event


def test_flatten_observation_fields_noop_on_malformed_payload() -> None:
    event = {"type": "agent.fix_ci_observed", "payload": "not-a-dict"}
    assert flatten_observation_fields(event) is event
    event2 = {"type": "agent.fix_ci_observed", "payload": {"observation": "not-a-dict"}}
    assert flatten_observation_fields(event2) is event2


# --- safety allowlists for the deep link ------------------------------------


def test_is_safe_repository_slug() -> None:
    assert is_safe_repository_slug("ai-sdlc-lab/demo-app")
    assert not is_safe_repository_slug("ai-sdlc-lab/../etc")
    assert not is_safe_repository_slug("no-slash-here")
    assert not is_safe_repository_slug("owner/repo with space")
    assert not is_safe_repository_slug(123)
    assert not is_safe_repository_slug(None)


def test_is_safe_workflow_run_id() -> None:
    assert is_safe_workflow_run_id("9001")
    assert is_safe_workflow_run_id("run-9001_a")
    assert not is_safe_workflow_run_id("9001/../escape")
    assert not is_safe_workflow_run_id("has space")
    assert not is_safe_workflow_run_id("x" * 65)
    assert not is_safe_workflow_run_id(None)


# --- build_ci_deep_link ------------------------------------------------------


def test_build_ci_deep_link_happy_path() -> None:
    settings = Settings(GITEA_BASE_URL="https://git.ham-sup-lo.com")
    url = build_ci_deep_link(
        repository="ai-sdlc-lab/demo-app", workflow_run_id="9001", settings=settings
    )
    assert url == "https://git.ham-sup-lo.com/ai-sdlc-lab/demo-app/actions/runs/9001"


def test_build_ci_deep_link_none_when_base_url_unset_or_unsafe() -> None:
    settings = Settings(GITEA_BASE_URL="")
    assert build_ci_deep_link(repository="a/b", workflow_run_id="1", settings=settings) is None
    settings2 = Settings(GITEA_BASE_URL="not-a-url")
    assert build_ci_deep_link(repository="a/b", workflow_run_id="1", settings=settings2) is None


def test_build_ci_deep_link_none_on_unsafe_fields() -> None:
    settings = Settings(GITEA_BASE_URL="https://git.ham-sup-lo.com")
    assert build_ci_deep_link(repository="a/b/c", workflow_run_id="1", settings=settings) is None
    assert build_ci_deep_link(repository="a b/c", workflow_run_id="1", settings=settings) is None
    assert build_ci_deep_link(repository="a/b", workflow_run_id="has space", settings=settings) is None
    assert build_ci_deep_link(repository=None, workflow_run_id="1", settings=settings) is None


def test_build_ci_deep_link_never_reads_html_url() -> None:
    """The webhook's own free-form html_url is never a parameter this
    function accepts -- it can only ever build from repository +
    workflow_run_id + server-side settings."""
    import inspect

    sig = inspect.signature(build_ci_deep_link)
    assert "html_url" not in sig.parameters


# --- current_ci_phase_view ---------------------------------------------------


def test_current_ci_phase_view_none_without_a_claim(tmp_path: Path) -> None:
    assert current_ci_phase_view(tmp_path, project=PROJECT, session_id="sess-none") is None


def test_current_ci_phase_view_maps_claim_status_to_phase(tmp_path: Path) -> None:
    for status, expected_phase in CI_PHASE_BY_CLAIM_STATUS.items():
        session_id = f"sess-t08-phase-{status}"
        claim = VerificationClaim(
            session_id=session_id,
            run_id="run-t08-phase",
            repo=PROJECT,
            claim="test claim",
            scope_commit_sha="a" * 40,
            status=status,
            verdict_revision=3,
            created_at="2026-07-22T00:00:00+00:00",
            updated_at="2026-07-22T00:00:00+00:00",
        )
        persist_verification_claim(tmp_path, claim)
        view = current_ci_phase_view(tmp_path, project=PROJECT, session_id=session_id)
        assert view is not None
        assert view["phase"] == expected_phase
        assert view["claim_status"] == status
        assert view["verdict_revision"] == 3


def test_current_ci_phase_view_excludes_limitations_free_text(tmp_path: Path) -> None:
    session_id = "sess-t08-limitations"
    claim = VerificationClaim(
        session_id=session_id,
        run_id="run-t08-limitations",
        repo=PROJECT,
        claim="test claim",
        scope_commit_sha="a" * 40,
        status="failed",
        limitations="SECRET-EXCEPTION-DETAIL-should-never-surface",
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:00:00+00:00",
    )
    persist_verification_claim(tmp_path, claim)
    view = current_ci_phase_view(tmp_path, project=PROJECT, session_id=session_id)
    assert view is not None
    assert "limitations" not in view
    assert "SECRET-EXCEPTION-DETAIL-should-never-surface" not in str(view)


# --- safe_display_event integration -----------------------------------------


def test_safe_display_fix_ci_observed_is_flattened_and_allowlisted() -> None:
    display = safe_display_event(_fix_ci_observed_event())
    assert display.category == "ci"
    assert display.known_type is True
    assert display.display_fields["observation_status"] == "completed"
    assert display.display_fields["observation_conclusion"] == "success"
    assert "observation" not in display.display_fields
    assert "9001" in display.summary


def test_safe_display_fix_ci_observed_deep_link_present_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITEA_BASE_URL", "https://git.ham-sup-lo.com")
    display = safe_display_event(_fix_ci_observed_event())
    assert display.display_fields.get("ci_deep_link") == (
        "https://git.ham-sup-lo.com/ai-sdlc-lab/demo-app/actions/runs/9001"
    )


def test_safe_display_fix_ci_observed_no_deep_link_when_base_url_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITEA_BASE_URL", "")
    display = safe_display_event(_fix_ci_observed_event())
    assert "ci_deep_link" not in display.display_fields


def test_safe_display_verdict_changed_allowlisted_no_deep_link() -> None:
    body = FixCiVerdictChangedEvent(
        fix_run_id="run-t08-verdict",
        repository=PROJECT,
        expected_head_commit_sha="a" * 40,
        previous_verdict="pending",
        verdict="verified",
        verdict_revision=1,
        reason_codes=["all_required_workflows_passed"],
        evaluated_at="2026-07-22T00:00:00+00:00",
    )
    event = {
        "event_id": "evt-t08-verdict-1",
        "type": "agent.fix_ci_verdict_changed",
        "source": "ct103",
        "payload": body.model_dump(mode="json"),
    }
    display = safe_display_event(event)
    assert display.category == "ci"
    assert display.display_fields["verdict"] == "verified"
    assert "ci_deep_link" not in display.display_fields
    assert "pending" in display.summary and "verified" in display.summary


def test_safe_display_repair_blocked_allowlisted() -> None:
    body = FixCiRepairBlockedEvent(
        fix_run_id="run-t08-blocked",
        repository=PROJECT,
        expected_head_commit_sha="a" * 40,
        reason_codes=["max_attempts_reached"],
        label="agent:blocked",
    )
    event = {
        "event_id": "evt-t08-blocked-1",
        "type": "agent.fix_ci_repair_blocked",
        "source": "ct103",
        "payload": body.model_dump(mode="json"),
    }
    display = safe_display_event(event)
    assert display.category == "ci"
    assert display.display_fields["label"] == "agent:blocked"
    assert "agent:blocked" in display.summary


def test_safe_display_fix_ci_never_leaks_a_prohibited_field_value() -> None:
    event = _fix_ci_observed_event()
    event["payload"]["auth_token"] = "SECRET-SHOULD-NEVER-SURFACE"
    display = safe_display_event(event)
    dumped = display.model_dump_json()
    assert "SECRET-SHOULD-NEVER-SURFACE" not in dumped
    assert "auth_token" in display.metadata_only_field_names or "auth_token" in display.prohibited_field_names


def test_safe_display_unrelated_event_types_unaffected_by_ci_channel() -> None:
    """T08 must not regress classification for any non-CI event type."""
    event = {
        "event_id": "evt-t08-unrelated-1",
        "type": "agent.session_started",
        "source": "ct103",
        "payload": {"run_id": "run-x", "session_id": "sess-x", "command_kind": "review"},
    }
    display = safe_display_event(event)
    assert display.category is None
    assert display.known_type is True


# --- projector end-to-end: fix_run_id-keyed event, no run_id key -----------


def test_project_ledger_event_projects_fix_ci_observed_by_fix_run_id(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    run_id = "run-t08-project"
    session_id = "sess-t08-project"
    _seed_session(state_root, run_id=run_id, session_id=session_id)

    store = ObserveStore(observe_db_path(state_root))
    event = _fix_ci_observed_event(event_id="evt-t08-project-1")
    event["payload"]["fix_run_id"] = run_id
    sequence = project_ledger_event(store, event, project=PROJECT, state_root=state_root)
    assert sequence is not None

    rows = store.list_events_for_run(run_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "agent.fix_ci_observed"
    assert row["session_id"] == session_id

    observation = store.get_session_observation(session_id)
    assert observation is not None


def test_project_ledger_event_fix_ci_replay_is_idempotent(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    store = ObserveStore(observe_db_path(state_root))
    event = _fix_ci_observed_event(event_id="evt-t08-replay-1")
    event["payload"]["fix_run_id"] = "run-t08-replay"

    first = project_ledger_event(store, event, project=PROJECT, state_root=state_root)
    second = project_ledger_event(store, dict(event), project=PROJECT, state_root=state_root)
    assert first is not None
    assert second is None
    assert len(store.list_events_for_run("run-t08-replay")) == 1


def test_project_ledger_event_fix_ci_without_session_still_projects(tmp_path: Path) -> None:
    """No session exists for this fix_run_id (race/pruned) -- the event is
    still projected, just without a session_id (no H6 refresh), matching
    the existing behaviour for any other run-scoped event with an
    unresolvable session."""
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    store = ObserveStore(observe_db_path(state_root))
    event = _fix_ci_observed_event(event_id="evt-t08-nosession-1")
    event["payload"]["fix_run_id"] = "run-t08-nosession"
    sequence = project_ledger_event(store, event, project=PROJECT, state_root=state_root)
    assert sequence is not None
    rows = store.list_events_for_run("run-t08-nosession")
    assert rows[0]["session_id"] is None


# --- current_state_view (panel 1) ci_phase -----------------------------------


def test_current_state_view_ci_phase_populated_when_state_root_given(tmp_path: Path) -> None:
    session_id = "sess-t08-panel1"
    run_id = "run-t08-panel1"
    session = _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    claim = VerificationClaim(
        session_id=session_id,
        run_id=run_id,
        repo=PROJECT,
        claim="test claim",
        scope_commit_sha="a" * 40,
        status="passed",
        verdict_revision=2,
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:00:00+00:00",
    )
    persist_verification_claim(tmp_path, claim)
    store = ObserveStore(observe_db_path(tmp_path))
    view = current_state_view(session, store, state_root=tmp_path)
    assert view["ci_phase"] is not None
    assert view["ci_phase"]["phase"] == "verified"


def test_current_state_view_ci_phase_none_without_state_root(tmp_path: Path) -> None:
    session_id = "sess-t08-panel1-none"
    run_id = "run-t08-panel1-none"
    session = _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    store = ObserveStore(observe_db_path(tmp_path))
    view = current_state_view(session, store)
    assert view["ci_phase"] is None


# --- end-to-end via the session detail page ---------------------------------


def test_session_detail_page_shows_ci_phase_and_category(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t08-page"
    session_id = "sess-t08-page"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    claim = VerificationClaim(
        session_id=session_id,
        run_id=run_id,
        repo=PROJECT,
        claim="test claim",
        scope_commit_sha="a" * 40,
        status="failed",
        verdict_revision=1,
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:00:00+00:00",
    )
    persist_verification_claim(tmp_path, claim)

    append_fix_ci_observed(
        tmp_path,
        FixCiObservedEvent(
            fix_run_id=run_id,
            repository=PROJECT,
            expected_head_commit_sha="a" * 40,
            observation=_observation(),
            delivery_id="delivery-page-1",
        ),
    )

    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    body = resp.text
    assert "failing" in body
    assert "[ci]" in body


def test_session_detail_page_never_regresses_on_no_ci_events(tmp_path: Path, monkeypatch) -> None:
    """A session with zero CI events must render exactly as before T08 --
    the panel 1 CI row shows the placeholder, and no [ci] tag appears."""
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t08-no-ci"
    session_id = "sess-t08-no-ci"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    assert "no CT102 CI verification recorded for this session" in resp.text
    assert "[ci]" not in resp.text


# --- unrelated repair-lineage events keep the fix_run_id contract ----------


def test_repair_blocked_event_also_resolves_by_fix_run_id(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    run_id = "run-t08-repair-blocked"
    body = FixCiRepairBlockedEvent(
        fix_run_id=run_id,
        repository=PROJECT,
        expected_head_commit_sha="a" * 40,
        reason_codes=["max_attempts_reached"],
    )
    append_fix_ci_repair_blocked(state_root, body)
    store = ObserveStore(observe_db_path(state_root))
    rows = store.list_events_for_run(run_id)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "agent.fix_ci_repair_blocked"


def test_verdict_changed_event_resolves_by_fix_run_id(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    run_id = "run-t08-verdict-changed"
    body = FixCiVerdictChangedEvent(
        fix_run_id=run_id,
        repository=PROJECT,
        expected_head_commit_sha="a" * 40,
        previous_verdict="pending",
        verdict="failing",
        verdict_revision=1,
    )
    append_fix_ci_verdict_changed(state_root, body)
    store = ObserveStore(observe_db_path(state_root))
    rows = store.list_events_for_run(run_id)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "agent.fix_ci_verdict_changed"
