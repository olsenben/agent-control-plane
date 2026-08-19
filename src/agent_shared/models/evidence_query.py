"""W1-0 query, budget, and provider/builder result types.

Diagnostics such as ``rg_unavailable`` and ``language_unsupported`` live on
``ProviderResult.status`` / ``ProviderResult.diagnostics``. They are never
``EvidenceItem`` fields and must not enter ``current_evidence``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.context_pack_v2 import ContextPackV2, EvidenceItem

EvidenceClass = Literal[
    "lexical",
    "symbols",
    "dependency_edges",
    "tests",
    "config",
    "architecture",
]
ProviderStatus = Literal["ok", "unavailable", "unsupported", "error"]

EVIDENCE_CLASSES: tuple[EvidenceClass, ...] = (
    "lexical",
    "symbols",
    "dependency_edges",
    "tests",
    "config",
    "architecture",
)
EVIDENCE_CLASS_SET: frozenset[str] = frozenset(EVIDENCE_CLASSES)
PROVIDER_STATUSES: tuple[ProviderStatus, ...] = ("ok", "unavailable", "unsupported", "error")


def compute_evidence_item_id(
    snapshot_id: str,
    provider: str,
    evidence_type: str,
    path_or_node: str,
    normalized_fact: str,
) -> str:
    """Canonical id for an evidence item. Identity is the hashed tuple only."""
    return canonical_json_hash(
        {
            "snapshot_id": snapshot_id,
            "provider": provider,
            "evidence_type": evidence_type,
            "path_or_node": path_or_node,
            "normalized_fact": normalized_fact,
        }
    )


class EvidenceQuery(BaseModel):
    """Provider request. Query-term normalization is owned by W1-A, not this schema."""

    model_config = ConfigDict(extra="forbid")

    query_text: str = ""
    failure_signature: str = ""
    mentioned_paths: list[str] = Field(default_factory=list)
    mentioned_symbols: list[str] = Field(default_factory=list)
    requested_classes: list[EvidenceClass] = Field(default_factory=list)


class EvidenceBudget(BaseModel):
    """Typed per-class item caps plus character limits. Unknown class keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    max_items_by_class: dict[EvidenceClass, int] = Field(default_factory=dict)
    max_chars_total: int
    max_snippet_chars: int

    @field_validator("max_items_by_class")
    @classmethod
    def _known_class_keys(cls, value: dict[str, int]) -> dict[str, int]:
        unknown = sorted(key for key in value if key not in EVIDENCE_CLASS_SET)
        if unknown:
            raise ValueError(f"unknown evidence class keys: {unknown}")
        return value

    @model_validator(mode="after")
    def _budget_invariants(self) -> EvidenceBudget:
        if self.max_chars_total <= 0:
            raise ValueError("max_chars_total must be > 0")
        if self.max_snippet_chars < 0:
            raise ValueError("max_snippet_chars must be >= 0")
        if self.max_snippet_chars > self.max_chars_total:
            raise ValueError("max_snippet_chars must be <= max_chars_total")
        for key, limit in self.max_items_by_class.items():
            if limit < 0:
                raise ValueError(f"max_items_by_class[{key!r}] must be >= 0")
        return self


class ProviderResult(BaseModel):
    """Provider outcome. Diagnostics stay off the model-visible evidence list."""

    model_config = ConfigDict(extra="forbid")

    evidence: list[EvidenceItem] = Field(default_factory=list)
    status: ProviderStatus
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ContextBuildTrace(BaseModel):
    """Pure build accounting. Telemetry I/O is owned by integration, not the builder."""

    model_config = ConfigDict(extra="forbid")

    providers_invoked: list[str] = Field(default_factory=list)
    provider_statuses: dict[str, ProviderStatus] = Field(default_factory=dict)
    candidate_counts: dict[str, int] = Field(default_factory=dict)
    selected_counts: dict[str, int] = Field(default_factory=dict)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    dropped_by_budget: dict[str, int] = Field(default_factory=dict)
    chars_by_class: dict[str, int] = Field(default_factory=dict)
    total_chars: int = 0


class ContextBuildResult(BaseModel):
    """Builder return value: pack plus trace. Not ContextPackV2 alone."""

    model_config = ConfigDict(extra="forbid")

    context_pack: ContextPackV2
    build_trace: ContextBuildTrace


class ContextTaskSpec(BaseModel):
    """Task identity passed into ContextBuilderV2.build. Distinct from pack ContextTask."""

    model_config = ConfigDict(extra="forbid")

    project: str
    issue_text: str
    failure_signature: str = ""
