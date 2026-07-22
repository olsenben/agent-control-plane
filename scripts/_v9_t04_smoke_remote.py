"""Remote smoke for V9 T04 deploy verify — run inside control-plane container."""
from __future__ import annotations

import sys
import urllib.error
import urllib.request

from agent_control.config import Settings
from agent_control.observe.auth import resolve_observe_shared_token
from agent_control.observe.events import append_control_decision
from agent_control.observe.ui import TIMELINE_PAGE_SIZE
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus

PROJECT = "ai-sdlc-lab/demo-app"
RUN_ID = "run-v9t04-smoke"
SESSION_ID = "sess-v9t04-smoke"
BASE = "http://127.0.0.1:8080"

PANEL_MARKERS = (
    "1. Current state",
    "2. Decision timeline",
    "3. Decisions and evidence",
    "4. Live logs",
    "5. Artifacts",
)


def _resolve_token(settings: Settings) -> str | None:
    token = resolve_observe_shared_token(settings).strip()
    return token or None


def _seed_session(settings: Settings) -> None:
    root = settings.agent_state_root
    session = AgentSession(
        session_id=SESSION_ID,
        project=PROJECT,
        repo=PROJECT.split("/", 1)[1],
        subject_kind="issue",
        subject_number=99004,
        command_kind="plan",
        status=SessionStatus.QUEUED,
        run_ids=[RUN_ID],
        correlation_id="corr-v9t04-smoke",
        trace_id="tr-v9t04-smoke",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        invoked_by="v9t04-smoke",
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:00:00+00:00",
    )
    persist_session_with_run_index(root, session)


def _http_request(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    follow_redirect: bool = True,
) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers=headers or {})
    if not follow_redirect:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(req, timeout=15) as resp:
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, resp_headers, resp.read()
        except urllib.error.HTTPError as exc:
            resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
            return exc.code, resp_headers, exc.read()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp_headers, resp.read()
    except urllib.error.HTTPError as exc:
        resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        return exc.code, resp_headers, exc.read()


def main() -> None:
    settings = Settings()
    token = _resolve_token(settings)
    if not token:
        print("FAIL shared token unavailable for auth smoke")
        sys.exit(1)
    print("SHARED_TOKEN_AVAILABLE=yes")

    detail_url = f"{BASE}/observe/sessions/{RUN_ID}"

    # Unauth HTML -> 302 redirect to oauth login (T05 matrix preserved).
    unauth_code, unauth_headers, _ = _http_request(
        detail_url,
        {"Accept": "text/html"},
        follow_redirect=False,
    )
    location = unauth_headers.get("location", "")
    print(f"unauth_html_code: {unauth_code}")
    print(f"unauth_html_location: {location}")
    if unauth_code != 302 or not location.startswith("/observe/oauth/login?next="):
        print("FAIL unauth HTML expected 302 redirect to oauth login")
        sys.exit(1)

    # Seed session + enough timeline events for no-JS pagination link.
    _seed_session(settings)
    total_events = TIMELINE_PAGE_SIZE + 3
    for i in range(total_events):
        append_control_decision(
            settings.agent_state_root,
            project=PROJECT,
            kind="other",
            summary=f"v9t04-decision-{i}",
            session_id=SESSION_ID,
            run_id=RUN_ID,
            trace_id="tr-v9t04-smoke",
        )

    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/html",
    }
    auth_code, _, body_bytes = _http_request(detail_url, auth_headers)
    body = body_bytes.decode("utf-8", errors="replace")
    print(f"auth_detail_code: {auth_code}")
    if auth_code != 200:
        print("FAIL auth session detail expected 200")
        sys.exit(1)

    for marker in PANEL_MARKERS:
        if marker not in body:
            print(f"FAIL missing panel marker: {marker}")
            sys.exit(1)
    print("five_panels: ok")

    cursor = f"after_sequence={TIMELINE_PAGE_SIZE}"
    if cursor not in body:
        print(f"FAIL no-JS timeline pagination link missing ({cursor})")
        sys.exit(1)
    print("no_js_timeline_pagination: ok")

    if "v9t04-decision-0" not in body:
        print("FAIL expected timeline row on first page")
        sys.exit(1)

    page2_url = f"{detail_url}?after_sequence={TIMELINE_PAGE_SIZE}"
    page2_code, _, page2_bytes = _http_request(page2_url, auth_headers)
    page2 = page2_bytes.decode("utf-8", errors="replace")
    print(f"auth_timeline_page2_code: {page2_code}")
    if page2_code != 200:
        print("FAIL timeline page 2 expected 200")
        sys.exit(1)
    if f"v9t04-decision-{TIMELINE_PAGE_SIZE}" not in page2:
        print("FAIL timeline page 2 missing expected row")
        sys.exit(1)
    if "back to start" not in page2:
        print("FAIL timeline page 2 missing back-to-start link")
        sys.exit(1)
    print("timeline_page2: ok")

    print("V9_T04_SMOKE_OK")


if __name__ == "__main__":
    main()
