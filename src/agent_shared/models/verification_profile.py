"""verification_profile.v1 — required CI workflow identity per repository."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProfileRequiredWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    display_name: str = ""
    source: Literal["verification_profile"] = "verification_profile"


class VerificationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["verification_profile.v1"] = "verification_profile.v1"
    profile_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    required_workflows: list[ProfileRequiredWorkflow] = Field(min_length=1)
    notes: str | None = None


class VerificationProfileCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["verification_profiles.v1"] = "verification_profiles.v1"
    profiles: list[VerificationProfile] = Field(min_length=1)
