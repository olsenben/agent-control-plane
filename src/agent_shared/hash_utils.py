"""Canonical content hashing for approval scoping."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from agent_shared.models.plan import PlanResult
from agent_shared.models.review import BlastRadiusContext


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_hash(data: Any) -> str:
    body = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_text(body)


def plan_result_for_hash(plan: PlanResult) -> dict[str, Any]:
    """PlanResult payload for plan_hash — excludes volatile / CT103-injected fields."""
    data = plan.model_dump(mode="json")
    data.pop("recommended_next_command", None)
    data.pop("prior_memory_used", None)
    data.pop("approval_target_id", None)
    data.pop("plan_alias", None)
    return data


def hash_plan_result(plan: PlanResult) -> str:
    return canonical_json_hash(plan_result_for_hash(plan))


def hash_blast_radius(blast_radius: BlastRadiusContext) -> str:
    return canonical_json_hash(blast_radius.model_dump(mode="json"))


def hash_command_text(text: str) -> str:
    return sha256_text(text.strip())
