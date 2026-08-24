"""Repair prompt/input assembly (VExp W2-C)."""

from __future__ import annotations

import json
from typing import Any

from agent_shared.models.failure_evidence import FailureEvidence
from agent_shared.models.fix import FixResult
from agent_shared.models.repair import MAX_REPAIR_INPUT_CHARS, RepairContext

REPAIR_INSTRUCTION_ID = "repair_instruction.v1"
DEFAULT_REPAIR_INSTRUCTION = (
    "The previous patch failed the bounded verifier. Repair the implementation "
    "using the provided failure evidence. Preserve valid changes. Respect "
    "edit_policy. Return one FixResult in the existing format."
)


def build_repair_context(
    *,
    task_id: str,
    session_id: str,
    snapshot_sha: str,
    patch0_hash: str,
    context_pack_hash: str,
    edit_policy_hash: str,
    failure_evidence: FailureEvidence,
) -> RepairContext:
    return RepairContext(
        task_id=task_id,
        session_id=session_id,
        snapshot_sha=snapshot_sha,
        patch0_hash=patch0_hash,
        context_pack_hash=context_pack_hash,
        edit_policy_hash=edit_policy_hash,
        failure_evidence_hash=failure_evidence.evidence_hash,
        instruction_id=REPAIR_INSTRUCTION_ID,
        repair_instruction=DEFAULT_REPAIR_INSTRUCTION,
    )


def build_repair_input(
    *,
    task_text: str,
    context_pack_render: str,
    edit_policy_statement: str,
    patch0: FixResult,
    failure_evidence: FailureEvidence,
    repair_context: RepairContext,
) -> str:
    """Bounded repair model input; excludes raw logs, memory, and retrieval."""
    payload: dict[str, Any] = {
        "instruction_id": REPAIR_INSTRUCTION_ID,
        "task": task_text,
        "context_pack": context_pack_render,
        "edit_policy": edit_policy_statement,
        "patch0": patch0.model_dump(mode="json"),
        "failure_evidence": failure_evidence.to_prompt_projection(),
        "repair_instruction": repair_context.repair_instruction,
    }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    if len(text) > MAX_REPAIR_INPUT_CHARS:
        return text[: MAX_REPAIR_INPUT_CHARS - 3] + "..."
    return text
