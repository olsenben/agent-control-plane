"""Remote smoke for V9 T07+T08 deploy verify — run inside control-plane container."""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request

from agent_control.ci.events import append_fix_ci_observed
from agent_control.config import Settings
from agent_control.observe.artifacts import artifact_disposition_rows, artifact_id_for
from agent_control.observe.auth import resolve_observe_shared_token
from agent_control.observe.decisions import decisions_panel_view
from agent_control.observe.events import append_control_decision
from agent_control.observe.store import ObserveStore
from agent_control.session.lifecycle import begin_typed_session
from agent_control.session.storage import load_session_by_run, persist_session_with_run_index
from agent_control.session.verification import apply_ci_verdict_to_session, request_session_verification
from agent_shared.models.agent_session import AgentSession, SessionStatus
from agent_shared.models.ci import FixCiObservedEvent, WorkflowObservation
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.memory_preflight import SessionArtifactRef

PROJECT = "ai-sdlc-lab/demo-app"
RUN_T07 = "run-v9t07-smoke"
SESSION_T07 = "sess-v9t07-smoke"
RUN_T08 = "run-v9t08-smoke"
BASE = "http://127.0.0.1:8080"
SECRET_VALUE = "super-secret-token-value-should-never-be-exposed"


def _resolve_token(settings: Settings) -> str | None:
    token = resolve_observe_shared_token(settings).strip()
    return token or None


def _http_request(
    url: str,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp_headers, resp.read()
    except urllib.error.HTTPError as exc:
        resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        return exc.code, resp_headers, exc.read()


def _seed_t07_session(settings: Settings) -> tuple[str, str]:
    root = settings.agent_state_root
    artifact_body = {
        "schema_version": "memory_preflight.v1",
        "session_id": SESSION_T07,
        "status": "complete",
        "auth_header": SECRET_VALUE,
        "nested": {"api_key": SECRET_VALUE, "note": "kept"},
    }
    artifact_dir = root / f"projects/{PROJECT}/sessions/artifacts/{SESSION_T07}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "memory_preflight.json"
    raw = json.dumps(artifact_body, indent=2).encode("utf-8")
    artifact_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    ref = SessionArtifactRef(
        artifact_type="memory_preflight",
        relative_path=artifact_path.resolve().relative_to(root.resolve()).as_posix(),
        digest=digest,
        byte_size=len(raw),
        schema_name="memory_preflight.v1",
        created_at="2026-07-22T00:00:00+00:00",
    )
    session = AgentSession(
        session_id=SESSION_T07,
        project=PROJECT,
        repo=PROJECT.split("/", 1)[1],
        subject_kind="issue",
        subject_number=99007,
        command_kind="review",
        status=SessionStatus.RUNNING,
        run_ids=[RUN_T07],
        correlation_id="corr-v9t07-smoke",
        trace_id="tr-v9t07-smoke",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        invoked_by="v9t07-smoke",
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:00:00+00:00",
        memory_preflight=ref,
    )
    persist_session_with_run_index(root, session)
    append_control_decision(
        root,
        project=PROJECT,
        kind="approval_required",
        summary="Escalate to human approval",
        session_id=SESSION_T07,
        run_id=RUN_T07,
        trace_id="tr-v9t07-smoke",
        evidence_refs=["evt-v9t07"],
        metadata={
            "why": "risk1 requires sign-off",
            "alternatives_rejected": ["auto_approve"],
            "remaining_uncertainty": "none known",
        },
    )
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    return artifact_id, SECRET_VALUE


def _seed_t08_ci(settings: Settings) -> None:
    root = settings.agent_state_root
    tc = TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=99008,
        author="v9t08-smoke",
        raw_body="/agent fix",
        normalized_body="/agent fix",
    )
    begin_typed_session(
        root,
        project=PROJECT,
        command_kind="fix",
        run_id=RUN_T08,
        head_sha="c" * 40,
        trigger_context=tc,
    )
    request_session_verification(root, project=PROJECT, run_id=RUN_T08, commit_sha="c" * 40)
    append_fix_ci_observed(
        root,
        FixCiObservedEvent(
            fix_run_id=RUN_T08,
            repository=PROJECT,
            expected_head_commit_sha="c" * 40,
            observation=WorkflowObservation(
                workflow_run_id="99008",
                status="completed",
                conclusion="success",
                head_sha="c" * 40,
            ),
            delivery_id="delivery-v9t08-smoke",
        ),
    )
    apply_ci_verdict_to_session(
        root,
        project=PROJECT,
        fix_run_id=RUN_T08,
        verdict="verified",
        previous_verdict="pending",
        expected_head_commit_sha="c" * 40,
        verdict_revision=2,
    )


def _smoke_t07(settings: Settings, token: str) -> None:
    artifact_id, secret = _seed_t07_session(settings)
    root = settings.agent_state_root

    decisions = decisions_panel_view(root, project=PROJECT, run_id=RUN_T07)
    if decisions.get("total", 0) != 1:
        print(f"FAIL decisions_panel_view total={decisions.get('total')}")
        sys.exit(1)
    if decisions["decisions"][0].get("why") != "risk1 requires sign-off":
        print("FAIL decisions_panel_view missing why")
        sys.exit(1)
    print("decisions_panel_view: ok")

    session = load_session_by_run(root, PROJECT, RUN_T07)
    if session is None:
        print("FAIL T07 session missing after seed")
        sys.exit(1)
    rows = artifact_disposition_rows(session, root)
    if not rows or rows[0].get("disposition") != "metadata_only":
        print(f"FAIL artifact disposition rows: {rows!r}")
        sys.exit(1)
    print("artifact_disposition_metadata_only: ok")

    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/html",
    }
    detail_url = f"{BASE}/observe/sessions/{RUN_T07}"
    detail_code, _, detail_body = _http_request(detail_url, auth_headers)
    detail_text = detail_body.decode("utf-8", errors="replace")
    print(f"auth_detail_code: {detail_code}")
    if detail_code != 200:
        print("FAIL auth session detail expected 200")
        sys.exit(1)
    for marker in (
        "Escalate to human approval",
        "risk1 requires sign-off",
        "auto_approve",
        "metadata_only",
    ):
        if marker not in detail_text:
            print(f"FAIL panel missing marker: {marker}")
            sys.exit(1)
    print("decisions_panel_html: ok")

    view_url = f"{BASE}/observe/sessions/{RUN_T07}/artifacts/{artifact_id}/view"
    view_code, _, view_body = _http_request(view_url, auth_headers)
    view_text = view_body.decode("utf-8", errors="replace")
    print(f"artifact_view_code: {view_code}")
    if view_code != 200:
        print("FAIL artifact view expected 200")
        sys.exit(1)
    if secret in view_text:
        print("FAIL artifact view leaked secret")
        sys.exit(1)
    print("artifact_redacted_view: ok")

    traversal_url = f"{BASE}/observe/sessions/{RUN_T07}/artifacts/..%2F..%2F..%2Fetc%2Fpasswd/view"
    traversal_code, _, _ = _http_request(traversal_url, auth_headers)
    print(f"path_traversal_code: {traversal_code}")
    if traversal_code != 404:
        print("FAIL path traversal expected 404")
        sys.exit(1)
    print("path_traversal_rejected: ok")
    print("V9_T07_SMOKE_OK")


def _smoke_t08(settings: Settings, token: str) -> None:
    _seed_t08_ci(settings)
    store = ObserveStore(settings.observe_db_path)
    rows = store.list_events_for_run(RUN_T08)
    ci_rows = [r for r in rows if str(r.get("event_type", "")).startswith("agent.fix_ci_")]
    print(f"observe_ci_rows: {len(ci_rows)}")
    if not ci_rows:
        print("FAIL no agent.fix_ci_* rows in observe.sqlite")
        sys.exit(1)
    observed = [r for r in ci_rows if r["event_type"] == "agent.fix_ci_observed"]
    if not observed:
        print("FAIL missing agent.fix_ci_observed projection")
        sys.exit(1)
    if not observed[0].get("session_id"):
        print("FAIL fix_ci_observed missing session_id")
        sys.exit(1)
    print("projector_fix_ci_observed: ok")

    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/html",
    }
    detail_url = f"{BASE}/observe/sessions/{RUN_T08}"
    detail_code, _, detail_body = _http_request(detail_url, auth_headers)
    detail_text = detail_body.decode("utf-8", errors="replace")
    print(f"t08_detail_code: {detail_code}")
    if detail_code != 200:
        print("FAIL T08 session detail expected 200")
        sys.exit(1)
    if "agent.fix_ci_observed" not in detail_text and "[ci]" not in detail_text.lower():
        print("FAIL timeline missing CI category/event marker")
        sys.exit(1)
    print("timeline_ci_marker: ok")

    session = load_session_by_run(settings.agent_state_root, PROJECT, RUN_T08)
    if session is None:
        print("FAIL T08 session missing after CI verdict")
        sys.exit(1)
    if session.status != SessionStatus.FINISHED:
        print(f"FAIL T08 session expected FINISHED after verified verdict, got {session.status.value}")
        sys.exit(1)

    # Late duplicate failing verdict must not regress terminal session state.
    apply_ci_verdict_to_session(
        settings.agent_state_root,
        project=PROJECT,
        fix_run_id=RUN_T08,
        verdict="failing",
        previous_verdict="pending",
        expected_head_commit_sha="c" * 40,
        verdict_revision=1,
    )
    reloaded = load_session_by_run(settings.agent_state_root, PROJECT, RUN_T08)
    if reloaded is None or reloaded.status != SessionStatus.FINISHED:
        print(
            f"FAIL terminal regression: before={session.status.value} "
            f"after={reloaded.status.value if reloaded else None}"
        )
        sys.exit(1)
    print("terminal_no_regress: ok")

    print("V9_T08_SMOKE_OK")


def main() -> None:
    settings = Settings()
    token = _resolve_token(settings)
    if not token:
        print("FAIL shared token unavailable for auth smoke")
        sys.exit(1)
    print("SHARED_TOKEN_AVAILABLE=yes")
    _smoke_t07(settings, token)
    _smoke_t08(settings, token)
    print("V9_T07_T08_SMOKE_OK")


if __name__ == "__main__":
    main()
