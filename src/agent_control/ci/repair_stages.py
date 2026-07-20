"""T09 staged non-demo 6F.2 expand helpers (ACP allowlist only).

Stages (observe → repair-no-publish → one-class publish) are policy knobs on
Settings / CT103 .env. This module reports stage readiness without mutating policy.
"""

from __future__ import annotations

from typing import Any

from agent_control.ci.repair_policy import (
    DEFAULT_REPAIR_ALLOWED_CLASSES,
    decide_repair_repository,
    intentional_fail_heuristic_allowed,
    normalize_repository,
    parse_repair_allowlist,
    parse_repair_classes,
)
from agent_control.config import Settings, get_settings

ACP_REPO = "ai-sdlc-lab/agent-control-plane"
DEMO_REPO = "ai-sdlc-lab/demo-app"


def repair_stage_status(settings: Settings | None = None) -> dict[str, Any]:
    """Report Observe / repair-no-publish / one-class-publish readiness for ACP."""
    settings = settings or get_settings()
    allowlist = parse_repair_allowlist(settings.fix_ci_repair_allowed_repos)
    classes = parse_repair_classes(settings.fix_ci_repair_allowed_classes)
    acp = normalize_repository(ACP_REPO)
    acp_listed = acp in allowlist

    observe = {
        "ready": bool(settings.fix_ci_observe_enabled),
        "repair_master_enabled": bool(settings.fix_ci_repair_enabled),
        "evidence_enabled": bool(settings.fix_ci_failure_evidence_enabled),
        "notes": [],
    }
    if not settings.fix_ci_observe_enabled:
        observe["notes"].append("observe_disabled")
    if not settings.fix_ci_failure_evidence_enabled:
        observe["notes"].append("failure_evidence_disabled")
    if not settings.fix_ci_repair_enabled:
        observe["notes"].append("repair_master_disabled")
    observe["stage_ok"] = bool(
        settings.fix_ci_observe_enabled and settings.fix_ci_failure_evidence_enabled
    )

    # Stage 2: allowlist ACP + lint class; publish still off for "no-publish" proof
    d_enqueue = decide_repair_repository(
        ACP_REPO,
        failure_class="lint_failure",
        allowlist_raw=settings.fix_ci_repair_allowed_repos,
        allowed_classes_raw=settings.fix_ci_repair_allowed_classes,
        publish_enabled=False,
        for_publish=False,
    )
    d_publish_off = decide_repair_repository(
        ACP_REPO,
        failure_class="lint_failure",
        allowlist_raw=settings.fix_ci_repair_allowed_repos,
        allowed_classes_raw=settings.fix_ci_repair_allowed_classes,
        publish_enabled=False,
        for_publish=True,
    )
    d_demo = decide_repair_repository(
        DEMO_REPO,
        failure_class="lint_failure",
        allowlist_raw=settings.fix_ci_repair_allowed_repos,
        allowed_classes_raw=settings.fix_ci_repair_allowed_classes,
        publish_enabled=settings.fix_ci_repair_publish_enabled,
        for_publish=False,
    )
    d_test_fail = decide_repair_repository(
        ACP_REPO,
        failure_class="test_failure",
        allowlist_raw=settings.fix_ci_repair_allowed_repos,
        allowed_classes_raw=settings.fix_ci_repair_allowed_classes,
        publish_enabled=settings.fix_ci_repair_publish_enabled,
        for_publish=False,
    )

    repair_no_publish = {
        "acp_listed": acp_listed,
        "enqueue_lint_allowed": d_enqueue.allowed,
        "publish_denied_when_flag_off": not d_publish_off.allowed
        and d_publish_off.reason_code == "repair_publish_disabled",
        "demo_denied": not d_demo.allowed,
        "non_lint_denied": not d_test_fail.allowed,
        "demo_heuristic_blocked_for_acp": not intentional_fail_heuristic_allowed(ACP_REPO),
        "allowed_classes": sorted(classes),
        "default_class": DEFAULT_REPAIR_ALLOWED_CLASSES[0],
    }
    repair_no_publish["stage_ok"] = all(
        [
            repair_no_publish["acp_listed"] or not settings.fix_ci_repair_enabled,
            # When repair enabled, require ACP listed + enqueue ok + class fence
            (not settings.fix_ci_repair_enabled)
            or (
                repair_no_publish["acp_listed"]
                and repair_no_publish["enqueue_lint_allowed"]
                and repair_no_publish["demo_denied"]
                and repair_no_publish["non_lint_denied"]
                and repair_no_publish["demo_heuristic_blocked_for_acp"]
            ),
        ]
    )

    d_publish_on = decide_repair_repository(
        ACP_REPO,
        failure_class="lint_failure",
        allowlist_raw=settings.fix_ci_repair_allowed_repos,
        allowed_classes_raw=settings.fix_ci_repair_allowed_classes,
        publish_enabled=True,
        for_publish=True,
    )
    one_class_publish = {
        "publish_flag": bool(settings.fix_ci_repair_publish_enabled),
        "publish_allowed_when_flag_on": d_publish_on.allowed,
        "live_publish_decision_allowed": decide_repair_repository(
            ACP_REPO,
            failure_class="lint_failure",
            allowlist_raw=settings.fix_ci_repair_allowed_repos,
            allowed_classes_raw=settings.fix_ci_repair_allowed_classes,
            publish_enabled=settings.fix_ci_repair_publish_enabled,
            for_publish=True,
        ).allowed
        if settings.fix_ci_repair_publish_enabled
        else False,
        "scope": "acp_lint_failure_only",
        "scope_widened": sorted(classes) != ["lint_failure"] or len(allowlist) > 1,
    }
    one_class_publish["stage_ok"] = (
        one_class_publish["publish_flag"]
        and one_class_publish["live_publish_decision_allowed"]
        and not one_class_publish["scope_widened"]
        and repair_no_publish["stage_ok"]
    )

    return {
        "schema": "repair_stage_status.v1",
        "ticket": "T09",
        "repository_focus": ACP_REPO,
        "allowlist": allowlist,
        "stages": {
            "observe": observe,
            "repair_no_publish": repair_no_publish,
            "one_class_publish": one_class_publish,
        },
        "t09_complete": bool(
            observe["stage_ok"]
            and repair_no_publish["stage_ok"]
            and settings.fix_ci_repair_enabled
            and acp_listed
            and (
                one_class_publish["stage_ok"]
                or repair_no_publish["publish_denied_when_flag_off"]
            )
        ),
        "adr": "ADR-0009 (no new ADR — scope not widened beyond ACP + lint_failure)",
    }
