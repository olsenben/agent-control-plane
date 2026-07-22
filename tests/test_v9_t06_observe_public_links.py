"""V9 T06 -- OBSERVE_PUBLIC_BASE_URL fail-closed Observe links (H8).

Covers:

- ``Settings.observe_public_base_url`` fail-closed validation: unset is
  always fine; a set value must be an absolute http(s) scheme+host URL with
  no path/query/fragment, and must be https whenever
  ``OBSERVE_COOKIE_SECURE`` is true (public/secure mode).
- ``agent_control.observe_links`` helpers: unset base URL or an unsafe
  ``run_id`` both mean "omit the link", never a guessed LAN address or an
  unvalidated string interpolated into a URL.
- ``format_invocation_started`` (invocation_ack) and the session comment
  projection (``render_session_comment_body``) and the NL-invocation
  handoff stub all extend with an ``Observe:`` link only when
  ``OBSERVE_PUBLIC_BASE_URL`` is configured, and omit it entirely otherwise
  (no bare relative-path fallback).
- ``/readyz`` surfaces ``observe_public_base_url`` as informational
  (``configured``/``unset``) and never gates readiness on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_control.config import Settings
from agent_control.invocation import begin_invocation, save_invocation
from agent_control.invocation_ack import format_invocation_started
from agent_control.nl_invocation_wire import handoff_invocation_to_session
from agent_control.observe.comment_projection import render_session_comment_body
from agent_control.observe_links import (
    build_observe_session_url,
    is_url_safe_run_id,
    observe_config_warning,
    observe_link_line,
    observe_public_base_url_configured,
)
from agent_control.readiness import build_readiness_report
from agent_shared.models.agent_session import AgentSession, SessionStatus

# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------


def test_unset_base_url_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OBSERVE_PUBLIC_BASE_URL", raising=False)
    settings = Settings()
    assert settings.observe_public_base_url is None


def test_blank_base_url_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVE_PUBLIC_BASE_URL", "   ")
    settings = Settings()
    assert not observe_public_base_url_configured(settings)


def test_relative_url_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVE_PUBLIC_BASE_URL", "/observe")
    with pytest.raises(ValidationError, match="absolute http"):
        Settings()


def test_non_http_scheme_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVE_PUBLIC_BASE_URL", "ftp://control.example.test")
    with pytest.raises(ValidationError, match="absolute http"):
        Settings()


def test_path_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVE_PUBLIC_BASE_URL", "https://control.example.test/observe")
    with pytest.raises(ValidationError, match="no path"):
        Settings()


def test_query_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVE_PUBLIC_BASE_URL", "https://control.example.test?x=1")
    with pytest.raises(ValidationError, match="no path"):
        Settings()


def test_http_rejected_in_secure_mode_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # OBSERVE_COOKIE_SECURE defaults to true -- plain http must fail closed.
    monkeypatch.setenv("OBSERVE_PUBLIC_BASE_URL", "http://control.example.test")
    monkeypatch.delenv("OBSERVE_COOKIE_SECURE", raising=False)
    with pytest.raises(ValidationError, match="https"):
        Settings()


def test_https_accepted_in_secure_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVE_PUBLIC_BASE_URL", "https://control.example.test")
    monkeypatch.setenv("OBSERVE_COOKIE_SECURE", "true")
    settings = Settings()
    assert settings.observe_public_base_url == "https://control.example.test"


def test_http_accepted_when_cookie_secure_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVE_PUBLIC_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("OBSERVE_COOKIE_SECURE", "false")
    settings = Settings()
    assert settings.observe_public_base_url == "http://localhost:8080"


def test_no_lan_http_default() -> None:
    """The field itself must default to None -- never a LAN/HTTP address."""
    settings = Settings.model_construct()
    assert settings.observe_public_base_url is None


# ---------------------------------------------------------------------------
# observe_links helpers
# ---------------------------------------------------------------------------


def test_is_url_safe_run_id_accepts_normal_shapes() -> None:
    assert is_url_safe_run_id("run-abc123")
    assert is_url_safe_run_id("rlm-root-" + "a" * 32)
    assert is_url_safe_run_id("run-" + "f" * 32)


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        None,
        "run id",  # whitespace
        "run/id",  # path separator
        "run`id",  # backtick (code-span breakout)
        "run](id)",  # markdown link breakout
        "run\nid",  # newline
        "a" * 200,  # too long
    ],
)
def test_is_url_safe_run_id_rejects_unsafe_shapes(run_id) -> None:
    assert not is_url_safe_run_id(run_id)


def test_build_observe_session_url_none_when_unset() -> None:
    settings = Settings.model_construct(observe_public_base_url=None)
    assert build_observe_session_url("run-abc", settings=settings) is None


def test_build_observe_session_url_built_when_configured() -> None:
    settings = Settings.model_construct(
        observe_public_base_url="https://control.ham-sup-lo.com"
    )
    url = build_observe_session_url("run-abc123", settings=settings)
    assert url == "https://control.ham-sup-lo.com/observe/sessions/run-abc123"


def test_build_observe_session_url_strips_trailing_slash() -> None:
    settings = Settings.model_construct(
        observe_public_base_url="https://control.ham-sup-lo.com/"
    )
    url = build_observe_session_url("run-abc", settings=settings)
    assert url == "https://control.ham-sup-lo.com/observe/sessions/run-abc"


def test_build_observe_session_url_none_for_unsafe_run_id() -> None:
    settings = Settings.model_construct(
        observe_public_base_url="https://control.ham-sup-lo.com"
    )
    assert build_observe_session_url("run/../../etc", settings=settings) is None
    assert build_observe_session_url("run`; rm -rf`", settings=settings) is None


def test_observe_link_line_wraps_url() -> None:
    settings = Settings.model_construct(
        observe_public_base_url="https://control.ham-sup-lo.com"
    )
    line = observe_link_line("run-abc", settings=settings)
    assert line == "Observe: https://control.ham-sup-lo.com/observe/sessions/run-abc"


def test_observe_link_line_none_when_unset() -> None:
    settings = Settings.model_construct(observe_public_base_url=None)
    assert observe_link_line("run-abc", settings=settings) is None


def test_observe_config_warning_present_when_unset() -> None:
    settings = Settings.model_construct(observe_public_base_url=None)
    warning = observe_config_warning(settings)
    assert warning is not None
    assert "OBSERVE_PUBLIC_BASE_URL" in warning


def test_observe_config_warning_absent_when_configured() -> None:
    settings = Settings.model_construct(
        observe_public_base_url="https://control.ham-sup-lo.com"
    )
    assert observe_config_warning(settings) is None


# ---------------------------------------------------------------------------
# format_invocation_started
# ---------------------------------------------------------------------------


def test_format_invocation_started_omits_observe_line_when_unset() -> None:
    settings = Settings.model_construct(observe_public_base_url=None)
    body = format_invocation_started(
        command="review",
        run_id="run-t06-1",
        invoked_by="alice",
        settings=settings,
    )
    assert "Observe:" not in body


def test_format_invocation_started_includes_observe_line_when_configured() -> None:
    settings = Settings.model_construct(
        observe_public_base_url="https://control.ham-sup-lo.com"
    )
    body = format_invocation_started(
        command="review",
        run_id="run-t06-2",
        invoked_by="alice",
        settings=settings,
    )
    assert "Observe: https://control.ham-sup-lo.com/observe/sessions/run-t06-2" in body


# ---------------------------------------------------------------------------
# Session comment projection
# ---------------------------------------------------------------------------


def _session(**kwargs) -> AgentSession:
    base = dict(
        session_id="sess-t06",
        project="ai-sdlc-lab/demo-app",
        repo="demo-app",
        subject_kind="issue",
        subject_number=1,
        command_kind="review",
        status=SessionStatus.QUEUED,
        run_ids=["run-t06"],
        correlation_id="corr-t06",
        input_state_sha="abc",
        head_sha="def",
        risk_level="risk_1",
        invoked_by="alice",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    base.update(kwargs)
    return AgentSession(**base)


def test_render_session_comment_omits_observe_line_when_unset() -> None:
    settings = Settings.model_construct(observe_public_base_url=None)
    body = render_session_comment_body(
        session=_session(),
        run_id="run-t06",
        display_status="queued",
        command="review",
        settings=settings,
    )
    assert "Observe:" not in body


def test_render_session_comment_includes_observe_link_when_configured() -> None:
    settings = Settings.model_construct(
        observe_public_base_url="https://control.ham-sup-lo.com"
    )
    body = render_session_comment_body(
        session=_session(),
        run_id="run-t06",
        display_status="queued",
        command="review",
        settings=settings,
    )
    assert "Observe: https://control.ham-sup-lo.com/observe/sessions/run-t06" in body


# ---------------------------------------------------------------------------
# NL invocation handoff stub
# ---------------------------------------------------------------------------


def test_handoff_invocation_stub_omits_observe_line_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    project = "ai-sdlc-lab/demo-app"
    record = begin_invocation(
        state,
        project=project,
        raw_text="/agent review",
        invoked_by="alice",
        subject_number=5,
    )
    save_invocation(state, record)

    posted: list[str] = []

    def _capture(project_arg, issue, body, settings=None):
        posted.append(body)
        return {"id": 1}

    monkeypatch.setattr("agent_control.nl_invocation_wire.post_issue_comment", _capture)

    settings = Settings.model_construct(observe_public_base_url=None)
    handoff_invocation_to_session(
        state,
        project=project,
        invocation_id=record.invocation_id,
        session_id="sess-t06-nl",
        run_id="run-t06-nl",
        settings=settings,
    )
    assert posted, "expected handoff stub comment"
    assert "Observe:" not in posted[0]


def test_handoff_invocation_stub_includes_observe_line_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    project = "ai-sdlc-lab/demo-app"
    record = begin_invocation(
        state,
        project=project,
        raw_text="/agent review",
        invoked_by="alice",
        subject_number=5,
    )
    save_invocation(state, record)

    posted: list[str] = []

    def _capture(project_arg, issue, body, settings=None):
        posted.append(body)
        return {"id": 1}

    monkeypatch.setattr("agent_control.nl_invocation_wire.post_issue_comment", _capture)

    settings = Settings.model_construct(
        observe_public_base_url="https://control.ham-sup-lo.com"
    )
    handoff_invocation_to_session(
        state,
        project=project,
        invocation_id=record.invocation_id,
        session_id="sess-t06-nl2",
        run_id="run-t06-nl2",
        settings=settings,
    )
    assert posted, "expected handoff stub comment"
    assert (
        "Observe: https://control.ham-sup-lo.com/observe/sessions/run-t06-nl2"
        in posted[0]
    )


# ---------------------------------------------------------------------------
# /readyz surfacing (informational only, never gates readiness)
# ---------------------------------------------------------------------------


def test_readiness_reports_unset_without_gating(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("OBSERVE_PUBLIC_BASE_URL", raising=False)
    settings = Settings()
    body, _status_code = build_readiness_report(settings)
    assert body["checks"]["observe_public_base_url"] == "unset"


def test_readiness_reports_configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("OBSERVE_PUBLIC_BASE_URL", "https://control.ham-sup-lo.com")
    settings = Settings()
    body, _status_code = build_readiness_report(settings)
    assert body["checks"]["observe_public_base_url"] == "configured"
