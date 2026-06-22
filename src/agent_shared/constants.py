"""Queue names, schema versions, and enums shared across CT103/CT104."""

from __future__ import annotations

import os
from enum import Enum

QUEUE_PREFIX = os.environ.get("QUEUE_PREFIX", "")

QUEUE_STATE = "state"
QUEUE_RLM_ROOT = "rlm-root"
QUEUE_RLM_CHILD = "rlm-child"
QUEUE_VERIFY = "verify"
QUEUE_REPORT = "report"

FLOW_QUEUE_NAMES: tuple[str, ...] = (
    QUEUE_STATE,
    QUEUE_RLM_ROOT,
    QUEUE_RLM_CHILD,
    QUEUE_VERIFY,
    QUEUE_REPORT,
)

LEGACY_GPU_QUEUES: tuple[str, ...] = (
    "snapshot",
    "planner-3080",
    "reviewer-3080",
    "fixer-3080",
    "judge-3080",
    "rlm-3080",
    "worker-2070",
    "summarizer-2070",
    "testwriter-2070",
    "preview",
    "danger-lab",
)

ALL_QUEUE_NAMES: tuple[str, ...] = FLOW_QUEUE_NAMES + LEGACY_GPU_QUEUES

# Max chars of run summary posted to Gitea issue comments and stored on completion events.
GITEA_COMMENT_SUMMARY_MAX_CHARS = 4000
# Target budget for model-generated summaries (room below hard cap for comment wrapper text).
GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS = 3500


def prefixed_queue(name: str) -> str:
    if QUEUE_PREFIX:
        return f"{QUEUE_PREFIX}-{name}"
    return name


class RiskClass(str, Enum):
    READ_ONLY = "read_only"
    READ_ONLY_WITH_REPO_CONTEXT = "read_only_with_repo_context"
    PLANNING_ONLY = "planning_only"
    WRITE_PATCH = "write_patch"
    EXECUTES_UNTRUSTED_CODE = "executes_untrusted_code"


class RunStatus(str, Enum):
    CREATED = "created"
    POLICY_LOADED = "policy_loaded"
    RUNNING = "running"
    COMPLETED = "completed"
    REPORTING = "reporting"
    REPORTED = "reported"
    FAILED = "failed"


class SessionEventType(str, Enum):
    RUN_CREATED = "run_created"
    BOOTSTRAP_STARTED = "bootstrap_started"
    BOOTSTRAP_COMPLETED = "bootstrap_completed"
    POLICY_LOAD_STARTED = "policy_load_started"
    POLICY_LOAD_COMPLETED = "policy_load_completed"
    CAPABILITY_DETECTED = "capability_detected"
    CONTEXT_LOADED = "context_loaded"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_CALL_REJECTED = "tool_call_rejected"
    ASSISTANT_MESSAGE = "assistant_message"
    CHECKPOINT = "checkpoint"
    MODEL_CALL_STARTED = "model_call_started"
    MODEL_CALL_COMPLETED = "model_call_completed"
    FAKE_ENGINE_STARTED = "fake_engine_started"
    FAKE_ENGINE_COMPLETED = "fake_engine_completed"
    FIX_APPLY_STARTED = "fix_apply_started"
    FIX_APPLY_COMPLETED = "fix_apply_completed"
    POST_APPLY_DIFF_ASSERT = "post_apply_diff_assert"
    PATCH_ARTIFACT_WRITTEN = "patch_artifact_written"
    FIX_FAILED = "fix_failed"
    ARTIFACT_WRITTEN = "artifact_written"
    REPORT_STARTED = "report_started"
    REPORT_COMPLETED = "report_completed"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


INTENT_KIND_TO_FLOW: dict[str, tuple[str, str, RiskClass]] = {
    "inspect": ("inspect", "explainer", RiskClass.READ_ONLY),
    "explain": ("explain", "explainer", RiskClass.READ_ONLY),
    "review": ("review", "reviewer", RiskClass.READ_ONLY_WITH_REPO_CONTEXT),
    "verify": ("verify", "verifier", RiskClass.EXECUTES_UNTRUSTED_CODE),
    "fix": ("developer_flow", "developer", RiskClass.WRITE_PATCH),
    "plan": ("planner_flow", "planner", RiskClass.PLANNING_ONLY),
}

FLOW_VERSIONS: dict[str, dict[str, str]] = {
    "inspect": {
        "workflow_definition": "inspect/v1",
        "flow_config_id": "inspect",
        "flow_version": "0.1.0",
        "flow_config_schema_version": "v1",
    },
    "explain": {
        "workflow_definition": "explain/v1",
        "flow_config_id": "explain",
        "flow_version": "0.1.0",
        "flow_config_schema_version": "v1",
    },
    "review": {
        "workflow_definition": "code_review/v1",
        "flow_config_id": "code_review",
        "flow_version": "0.1.0",
        "flow_config_schema_version": "v1",
    },
    "planner_flow": {
        "workflow_definition": "planner/v1",
        "flow_config_id": "planner",
        "flow_version": "0.1.0",
        "flow_config_schema_version": "v1",
    },
    "developer_flow": {
        "workflow_definition": "developer/v1",
        "flow_config_id": "developer",
        "flow_version": "0.1.0",
        "flow_config_schema_version": "v1",
    },
    "verify": {
        "workflow_definition": "verify/v1",
        "flow_config_id": "verify",
        "flow_version": "0.1.0",
        "flow_config_schema_version": "v1",
    },
}
