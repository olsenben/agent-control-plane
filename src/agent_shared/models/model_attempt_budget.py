"""Shared model attempt budget (V6 T04).

All retry layers (gateway, completion wrapper, schema repair, quality loop)
consume the same budget so call trees cannot explode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

BudgetKind = Literal[
    "infrastructure",
    "provider_route",
    "schema_repair",
    "quality_retry",
    "completion",
]


class ModelAttemptBudget(BaseModel):
    schema_version: str = "model_attempt_budget.v1"
    max_infrastructure_attempts: int = 3
    max_provider_routes: int = 2
    max_schema_repair_attempts: int = 1
    max_quality_retries: int = 1
    max_total_completion_attempts: int = 5


@dataclass
class AttemptBudgetTracker:
    """Mutable runtime counter for one completion tree."""

    limits: ModelAttemptBudget = field(default_factory=ModelAttemptBudget)
    infrastructure_attempts: int = 0
    provider_routes: int = 0
    schema_repair_attempts: int = 0
    quality_retries: int = 0
    total_completion_attempts: int = 0

    def remaining_total(self) -> int:
        return max(0, self.limits.max_total_completion_attempts - self.total_completion_attempts)

    def can_consume(self, kind: BudgetKind) -> bool:
        if self.total_completion_attempts >= self.limits.max_total_completion_attempts:
            return False
        if kind == "infrastructure":
            return self.infrastructure_attempts < self.limits.max_infrastructure_attempts
        if kind == "provider_route":
            return self.provider_routes < self.limits.max_provider_routes
        if kind == "schema_repair":
            return self.schema_repair_attempts < self.limits.max_schema_repair_attempts
        if kind == "quality_retry":
            return self.quality_retries < self.limits.max_quality_retries
        return True

    def consume(self, kind: BudgetKind) -> bool:
        if not self.can_consume(kind):
            return False
        self.total_completion_attempts += 1
        if kind == "infrastructure":
            self.infrastructure_attempts += 1
        elif kind == "provider_route":
            self.provider_routes += 1
        elif kind == "schema_repair":
            self.schema_repair_attempts += 1
        elif kind == "quality_retry":
            self.quality_retries += 1
        return True

    def as_dict(self) -> dict:
        return {
            "schema_version": self.limits.schema_version,
            "infrastructure_attempts": self.infrastructure_attempts,
            "provider_routes": self.provider_routes,
            "schema_repair_attempts": self.schema_repair_attempts,
            "quality_retries": self.quality_retries,
            "total_completion_attempts": self.total_completion_attempts,
            "max_total_completion_attempts": self.limits.max_total_completion_attempts,
            "exhausted": self.remaining_total() == 0,
        }


def budget_from_env() -> AttemptBudgetTracker:
    """Build tracker from env overrides when present."""
    import os

    def _int(name: str, default: int) -> int:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return max(0, int(raw))
        except ValueError:
            return default

    limits = ModelAttemptBudget(
        max_infrastructure_attempts=_int("MODEL_BUDGET_MAX_INFRA", 3),
        max_provider_routes=_int("MODEL_BUDGET_MAX_ROUTES", 2),
        max_schema_repair_attempts=_int("MODEL_BUDGET_MAX_SCHEMA_REPAIR", 1),
        max_quality_retries=_int("MODEL_BUDGET_MAX_QUALITY", 1),
        max_total_completion_attempts=_int("MODEL_BUDGET_MAX_TOTAL", 5),
    )
    return AttemptBudgetTracker(limits=limits)
