"""Adequacy profile models (Slice T04 / plan §7)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AdequacyStatus = Literal[
    "not_applicable",
    "pending",
    "passed",
    "failed",
    "incomplete",
]
AgentAuthoredTestsPolicy = Literal["not_applicable", "scoped_only", "required"]
CheckKind = Literal["ci_workflow", "agent_authored_tests", "deterministic", "other"]
VerificationOutcomeLabel = Literal[
    "verification_missing",
    "verification_failed",
    "ci_regression_passed",
    "fixed_verified",
    "local_checks_passed",
]


class AdequacyCheckSpec(BaseModel):
    id: str
    kind: CheckKind = "other"
    description: str = ""


class AdequacyCheckResult(BaseModel):
    id: str
    kind: CheckKind = "other"
    status: AdequacyStatus
    evidence: str = ""
    notes: str = ""


class AdequacyProfile(BaseModel):
    profile_id: str
    description: str = ""
    applies_to_commands: list[str] = Field(default_factory=list)
    required_checks: list[AdequacyCheckSpec] = Field(default_factory=list)
    optional_checks: list[AdequacyCheckSpec] = Field(default_factory=list)
    agent_authored_tests: AgentAuthoredTestsPolicy = "not_applicable"
    fixed_verified_allowed: bool = False
    default_limitations: str = ""
    require_agent_test_limitation_when_unknown: bool = False


class AdequacyEvaluation(BaseModel):
    schema_version: str = "adequacy_evaluation.v1"
    profile_id: str
    status: AdequacyStatus
    outcome_label: VerificationOutcomeLabel
    checks: list[AdequacyCheckResult] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    fixed_verified: bool = False
