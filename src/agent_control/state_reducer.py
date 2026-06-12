"""Event-only and snapshot-aware state reduction."""

from __future__ import annotations

from typing import Any

from enum import Enum

from agent_control.intent_parser import parse_command_intent
from agent_shared.constants import INTENT_KIND_TO_FLOW, RiskClass
from agent_shared.models.intent import CommandIntent
from agent_shared.models.state import SafetyState, VerificationState


def _label_names(payload: dict[str, Any]) -> list[str]:
    issue = payload.get("issue") or {}
    label = payload.get("label")
    labels: list[str] = []
    if label and label.get("name"):
        labels.append(label["name"])
    for item in issue.get("labels") or []:
        if isinstance(item, dict) and item.get("name"):
            labels.append(item["name"])
    return labels


def _comment_body(payload: dict[str, Any]) -> str:
    return payload.get("comment", {}).get("body", "")


def _should_dispatch(intent: CommandIntent) -> tuple[bool, str | None]:
    if not intent.activated or not intent.kind:
        return False, None
    if intent.kind in ("approve", "reject", "run"):
        return False, None
    if intent.kind not in INTENT_KIND_TO_FLOW:
        return False, None
    flow, _agent, risk = INTENT_KIND_TO_FLOW[intent.kind]
    if risk in (RiskClass.WRITE_PATCH, RiskClass.EXECUTES_UNTRUSTED_CODE):
        return False, None
    return True, flow


def reduce_event_only(events: list[dict[str, Any]], project: str) -> VerificationState:
    """Update logical state from normalized events without a local checkout."""
    state = VerificationState(project=project, reduction_mode="event_only")
    for event in events:
        etype = event.get("type", "")
        payload = event.get("payload", {})

        if etype == "gitea.push":
            state.ref = payload.get("ref")
            state.head_sha = payload.get("after")

        elif etype == "gitea.issue_opened":
            issue = payload.get("issue") or {}
            state.issue_state = {
                "number": issue.get("number"),
                "title": issue.get("title"),
                "state": issue.get("state"),
            }

        elif etype == "gitea.issue_labeled":
            state.labels = _label_names(payload)

        elif etype in ("gitea.issue_comment", "gitea.pr_comment"):
            body = _comment_body(payload)
            intent = parse_command_intent(body)
            state.command_intent = intent
            dispatch, kind = _should_dispatch(intent)
            state.dispatch_recommended = dispatch
            state.dispatch_kind = kind
            if intent.kind in ("fix", "review", "plan", "inspect", "explain", "verify"):
                state.safety = SafetyState(requires_manual_approval=intent.kind in ("fix", "plan"))

        elif etype == "gitea.pr_opened":
            pr = payload.get("pull_request") or {}
            state.pr_state = {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
            }
            state.ref = pr.get("head", {}).get("ref") or pr.get("base", {}).get("ref")
            state.head_sha = pr.get("head", {}).get("sha")

        elif etype == "gitea.pr_synchronized":
            state.snapshot_required = True
            pr = payload.get("pull_request") or {}
            state.ref = pr.get("head", {}).get("ref") or state.ref
            state.head_sha = pr.get("head", {}).get("sha") or state.head_sha

        elif etype.startswith("gitea.workflow_"):
            state.pipeline_status = etype.replace("gitea.workflow_", "")

    return state


# Backward compatibility alias
LogicalState = VerificationState


class ReductionMode(str, Enum):
    EVENT_ONLY = "event_only"
    SNAPSHOT_AWARE = "snapshot_aware"
