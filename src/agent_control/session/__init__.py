"""CT103-authoritative typed agent sessions (Slice 5.4a + 5.4b + 5.5a + 5.6)."""

from agent_control.session.lifecycle import (
    INGEST_TERMINAL_OWNERS,
    PUBLISH_TERMINAL_OWNERS,
    TYPED_SESSION_COMMANDS,
    WORKER_EVENT_ALLOWLIST,
    SessionMismatchError,
    append_run_to_session,
    begin_and_block_typed_session,
    begin_typed_session,
    bind_session_to_job,
    create_session_record,
    finalize_enqueue_failure,
    finalize_session,
    finalize_session_blocked,
    handle_ingest_session_update,
    handle_publish_session_terminal,
    make_blocked_request_key,
    mark_session_running,
)
from agent_control.session.reasons import (
    SessionTerminalError,
    SessionTerminalReason,
    SessionTerminalStatus,
    classify_broker_reject,
    classify_unsuccessful_terminal,
    map_fix_evaluation_to_block_reason,
    normalize_terminal,
)
from agent_control.session.storage import (
    SessionStoreError,
    list_sessions,
    load_session,
    load_session_by_run,
    lookup_session_id_by_run,
)
from agent_control.queue import EnqueueResult

# prepare_dispatch / verification imported lazily via __getattr__ to avoid cycles.

__all__ = [
    "INGEST_TERMINAL_OWNERS",
    "PUBLISH_TERMINAL_OWNERS",
    "TYPED_SESSION_COMMANDS",
    "WORKER_EVENT_ALLOWLIST",
    "EnqueueResult",
    "IdentityInvariantError",
    "PreflightFatalError",
    "PreparedTypedDispatch",
    "SessionMismatchError",
    "SessionStoreError",
    "SessionTerminalError",
    "SessionTerminalReason",
    "SessionTerminalStatus",
    "append_run_to_session",
    "apply_ci_verdict_to_session",
    "attach_preflight_for_non_rlm_session",
    "begin_and_block_typed_session",
    "begin_typed_session",
    "bind_session_to_job",
    "classify_broker_reject",
    "classify_unsuccessful_terminal",
    "create_session_record",
    "emit_ingest_verification_missing",
    "finalize_enqueue_failure",
    "finalize_session",
    "finalize_session_blocked",
    "handle_ingest_session_update",
    "handle_publish_session_terminal",
    "list_sessions",
    "load_session",
    "load_session_by_run",
    "load_verification_claim",
    "lookup_session_id_by_run",
    "make_blocked_request_key",
    "map_fix_evaluation_to_block_reason",
    "mark_session_running",
    "normalize_terminal",
    "prepare_typed_rlm_dispatch",
    "request_session_verification",
]


def __getattr__(name: str):
    if name in {
        "IdentityInvariantError",
        "PreflightFatalError",
        "PreparedTypedDispatch",
        "attach_preflight_for_non_rlm_session",
        "prepare_typed_rlm_dispatch",
    }:
        from agent_control.session import prepare_dispatch as _pd

        return getattr(_pd, name)
    if name in {
        "apply_ci_verdict_to_session",
        "emit_ingest_verification_missing",
        "load_verification_claim",
        "request_session_verification",
    }:
        from agent_control.session import verification as _v

        return getattr(_v, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
