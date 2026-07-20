"""5.4b homelab acceptance B: broker attestation deny -> session_blocked."""

from __future__ import annotations

import json
import sys
import uuid

from agent_control.config import get_settings
from agent_control.events import load_project_events
from agent_control.publish.broker import broker_publish_fix
from agent_control.publish.state import save_publish_record, try_enqueue_cas
from agent_control.session import begin_typed_session, load_session
from agent_shared.bundles import write_ready_bundle
from agent_shared.models.agent_session import SessionStatus
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.publish import PublishRecord

PROJECT = "ai-sdlc-lab/demo-app"
SUFFIX = uuid.uuid4().hex[:12]
RUN_ID = f"run-54b-late-{SUFFIX}"
ATTEMPT = "1"


def main() -> None:
    settings = get_settings()
    state = settings.agent_state_root

    session = begin_typed_session(
        state,
        project=PROJECT,
        command_kind="fix",
        run_id=RUN_ID,
        head_sha="0000000000000000000000000000000000000000",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="acceptance-bot",
            raw_body="/agent fix (5.4b late deny acceptance)",
            normalized_body="/agent fix",
        ),
    )

    patch = (
        b"diff --git a/README.md b/README.md\n"
        b"--- a/README.md\n+++ b/README.md\n"
        b"@@ -1 +1,2 @@\n"
        b" # demo\n"
        b"+# 5.4b late deny probe\n"
    )
    manifest = write_ready_bundle(
        state,
        run_id=RUN_ID,
        kind="fix",
        attempt_id=ATTEMPT,
        producer_base_sha="0000000000000000000000000000000000000000",
        patch_bytes=patch,
    )

    try_enqueue_cas(
        state,
        run_id=RUN_ID,
        kind="fix",
        attempt_id=ATTEMPT,
        bundle_id=manifest.bundle_id,
        project=PROJECT,
    )
    save_publish_record(
        state,
        PublishRecord(
            run_id=RUN_ID,
            bundle_id=manifest.bundle_id,
            kind="fix",
            attempt_id=ATTEMPT,
            publish_state="queued",
            project=PROJECT,
            approval_target_id=f"accept-54b-{SUFFIX}",
        ),
    )

    out = broker_publish_fix(
        state_root=state,
        run_id=RUN_ID,
        attempt_id=ATTEMPT,
        bundle_id=manifest.bundle_id,
    )
    if out.get("ok"):
        print("BROKER_UNEXPECTED_OK", json.dumps(out), file=sys.stderr)
        raise SystemExit(1)
    if out.get("reason") != "attestation_gate":
        print("BROKER_UNEXPECTED_REASON", json.dumps(out), file=sys.stderr)
        raise SystemExit(1)

    loaded = load_session(state, PROJECT, session.session_id)
    assert loaded is not None, "session missing"
    assert loaded.status == SessionStatus.BLOCKED, loaded.status
    assert loaded.terminal_reason_code == "sandbox_unavailable", loaded.terminal_reason_code

    terminal_raw = loaded.terminal_reason or ""
    if isinstance(terminal_raw, str) and terminal_raw.strip().startswith("{"):
        terminal = json.loads(terminal_raw)
    elif isinstance(terminal_raw, dict):
        terminal = terminal_raw
    else:
        terminal = {}
    domain = terminal.get("domain_reasons") or []
    attestation_codes = [
        c
        for c in domain
        if "attestation" in str(c).lower() or "sandbox" in str(c).lower()
    ]
    assert attestation_codes, f"expected attestation domain_reasons, got {domain!r}"

    events = load_project_events(state, PROJECT)
    sid = session.session_id
    blocked = [
        e
        for e in events
        if e.get("type") == "agent.session_blocked"
        and (e.get("payload") or {}).get("session_id") == sid
    ]
    finished = [
        e
        for e in events
        if e.get("type") == "agent.session_finished"
        and (e.get("payload") or {}).get("session_id") == sid
    ]
    assert len(blocked) == 1, blocked
    assert len(finished) == 0, finished

    print(
        "POSITIVE_OK",
        sid,
        RUN_ID,
        loaded.terminal_reason_code,
        "|".join(attestation_codes),
    )


if __name__ == "__main__":
    main()
