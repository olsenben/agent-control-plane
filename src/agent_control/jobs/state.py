"""State queue job: replay project event ledger and persist logical state."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.approval.handlers import handle_approval_commands
from agent_control.config import get_settings
from agent_control.events import (
    clear_reduction_outbox,
    load_project_events,
    write_verification_state,
)
from agent_control.state_reducer import dispatch_for_event, reduce_event_only
from agent_control.workflows.dispatch import maybe_dispatch_rlm_root


def process_state_reduction(state_root: str, event_id: str, project: str) -> dict[str, Any]:
    """Replay all ledger events for project; write verification_state.json."""
    root = Path(state_root)
    events = load_project_events(root, project)
    state = reduce_event_only(events, project)

    if events:
        last = events[-1]
        state.last_event_id = last.get("event_id")
        state.last_event_type = last.get("type")
    state.event_count = len(events)
    state.last_reduced_at = datetime.now(timezone.utc).isoformat()

    state_path = write_verification_state(root, project, state)
    clear_reduction_outbox(root, event_id)

    dispatch_result: dict[str, Any] = {"dispatched": False}
    approval_result: dict[str, Any] = {"handled": False}
    ci_result: dict[str, Any] = {"handled": False}
    nl_result: dict[str, Any] = {"handled": False}
    if events:
        trigger = next((e for e in reversed(events) if e.get("event_id") == event_id), events[-1])
        trigger_intent, trigger_dispatch, trigger_kind = dispatch_for_event(trigger)
        settings = get_settings()

        from agent_control.nl_invocation_wire import (
            handoff_invocation_to_session,
            maybe_begin_nl_invocation,
        )

        nl_result = maybe_begin_nl_invocation(root, project, trigger, settings=settings)
        if nl_result.get("clarify"):
            return {
                "trigger_event_id": event_id,
                "project": project,
                "events_loaded": len(events),
                "state_path": str(state_path),
                "command_intent": trigger_intent.kind if trigger_intent else None,
                "dispatch_recommended": False,
                "snapshot_required": state.snapshot_required,
                "dispatch": {"dispatched": False, "reason": "nl_clarification"},
                "approval": approval_result,
                "ci": ci_result,
                "nl_invocation": nl_result,
            }

        if trigger_intent.activated and trigger_intent.kind in ("approve", "reject", "fix"):
            approval_result = handle_approval_commands(
                root,
                project,
                trigger,
                trigger_intent,
                settings=settings,
            )
        elif trigger_dispatch:
            dispatch_state = state.model_copy(
                update={
                    "command_intent": trigger_intent,
                    "dispatch_recommended": True,
                    "dispatch_kind": trigger_kind,
                }
            )
            try:
                dispatch_result = maybe_dispatch_rlm_root(
                    dispatch_state,
                    trigger,
                    settings.redis_url,
                    settings=settings,
                )
                if (
                    dispatch_result.get("dispatched")
                    and nl_result.get("invocation_id")
                    and dispatch_result.get("session_id")
                    and dispatch_result.get("run_id")
                ):
                    handoff_invocation_to_session(
                        root,
                        project=project,
                        invocation_id=nl_result.get("invocation_id"),
                        session_id=str(dispatch_result["session_id"]),
                        run_id=str(dispatch_result["run_id"]),
                        settings=settings,
                    )
            except Exception as exc:
                dispatch_result = {"dispatched": False, "error": str(exc)}

        # Slice 6E.1: correlate terminal workflow events to pending fixes
        if str(trigger.get("type", "")).startswith("gitea.workflow_"):
            from agent_control.ci.observe import handle_workflow_event

            try:
                ci_result = handle_workflow_event(root, trigger, settings=settings)
            except Exception as exc:
                ci_result = {"handled": False, "error": str(exc)}
            # Soft reconcile same repo (catch dropped webhooks; idempotent)
            if settings.fix_ci_observe_enabled:
                try:
                    from agent_control.ci.reconcile import reconcile_pending_ci

                    ci_result["reconcile"] = reconcile_pending_ci(
                        root, project=project, settings=settings
                    )
                except Exception as exc:
                    ci_result["reconcile_error"] = str(exc)

    intent = state.command_intent
    return {
        "trigger_event_id": event_id,
        "project": project,
        "events_loaded": len(events),
        "state_path": str(state_path),
        "command_intent": intent.kind if intent else None,
        "dispatch_recommended": state.dispatch_recommended,
        "snapshot_required": state.snapshot_required,
        "dispatch": dispatch_result,
        "approval": approval_result,
        "ci": ci_result,
        "nl_invocation": nl_result,
    }
