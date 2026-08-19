"""W1-0 EvidenceQuery / EvidenceBudget / ProviderResult / protocol signature tests."""

from __future__ import annotations

from typing import get_type_hints

import pytest
from pydantic import ValidationError

from agent_shared.models.context_pack_v2 import ContextPackV2, EvidenceItem
from agent_shared.models.evidence_query import (
    ContextBuildResult,
    ContextBuildTrace,
    ContextTaskSpec,
    EvidenceBudget,
    EvidenceQuery,
    ProviderResult,
    compute_evidence_item_id,
)
from agent_shared.models.repo_snapshot import RepoSnapshot
from agent_shared.protocols import ContextBuilderV2, RepositoryEvidenceProvider
from agent_shared.protocols.context import ContextBuilderV2 as ContextBuilderV2Direct


def _budget(**overrides: object) -> EvidenceBudget:
    payload: dict[str, object] = {
        "max_items_by_class": {"lexical": 8, "symbols": 4},
        "max_chars_total": 4000,
        "max_snippet_chars": 400,
    }
    payload.update(overrides)
    return EvidenceBudget.model_validate(payload)


def test_evidence_query_round_trip() -> None:
    query = EvidenceQuery(
        query_text="fix foo",
        failure_signature="AssertionError: foo",
        mentioned_paths=["src/pkg/foo.py"],
        mentioned_symbols=["foo"],
        requested_classes=["lexical", "tests"],
    )
    dumped = query.model_dump(mode="json")
    restored = EvidenceQuery.model_validate(dumped)
    assert restored.model_dump(mode="json") == dumped


def test_evidence_budget_round_trip() -> None:
    budget = _budget()
    dumped = budget.model_dump(mode="json")
    restored = EvidenceBudget.model_validate(dumped)
    assert restored.model_dump(mode="json") == dumped


def test_provider_result_and_build_result_round_trip() -> None:
    item_id = compute_evidence_item_id("snap", "lexical", "hit", "src/pkg/foo.py", "def foo")
    result = ProviderResult(
        evidence=[EvidenceItem(text="def foo", source="lexical", id=item_id)],
        status="ok",
        diagnostics={},
    )
    dumped = result.model_dump(mode="json")
    restored = ProviderResult.model_validate(dumped)
    assert restored.model_dump(mode="json") == dumped

    build = ContextBuildResult(
        context_pack=ContextPackV2(),
        build_trace=ContextBuildTrace(
            providers_invoked=["lexical"],
            provider_statuses={"lexical": "ok"},
            candidate_counts={"lexical": 1},
            selected_counts={"lexical": 1},
            selected_evidence_ids=[item_id],
            dropped_by_budget={"lexical": 0},
            chars_by_class={"lexical": 7},
            total_chars=7,
        ),
    )
    build_dump = build.model_dump(mode="json")
    assert ContextBuildResult.model_validate(build_dump).model_dump(mode="json") == build_dump

    spec = ContextTaskSpec(project="acme/widgets", issue_text="fix foo")
    spec_dump = spec.model_dump(mode="json")
    assert ContextTaskSpec.model_validate(spec_dump).model_dump(mode="json") == spec_dump


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        EvidenceQuery(query_text="x", unexpected=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        EvidenceBudget(max_chars_total=10, max_snippet_chars=5, extra_cap=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ProviderResult(status="ok", diagnostics={}, surprise=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        EvidenceItem(text="hit", source="lexical", rg_unavailable=True)  # type: ignore[call-arg]


def test_budget_invariants() -> None:
    with pytest.raises(ValidationError):
        _budget(max_chars_total=0)
    with pytest.raises(ValidationError):
        _budget(max_chars_total=-1)
    with pytest.raises(ValidationError):
        _budget(max_snippet_chars=-1)
    with pytest.raises(ValidationError):
        _budget(max_chars_total=100, max_snippet_chars=101)
    with pytest.raises(ValidationError):
        _budget(max_items_by_class={"lexical": -1})
    ok = _budget(max_items_by_class={"lexical": 0}, max_chars_total=1, max_snippet_chars=1)
    assert ok.max_items_by_class["lexical"] == 0


def test_unknown_evidence_class_rejected() -> None:
    with pytest.raises(ValidationError):
        _budget(max_items_by_class={"dependancy": 4})
    with pytest.raises(ValidationError):
        EvidenceQuery(requested_classes=["dependancy"])  # type: ignore[list-item]


def test_provider_result_diagnostics_are_not_evidence_items() -> None:
    result = ProviderResult(
        evidence=[],
        status="unavailable",
        diagnostics={"reason": "rg_unavailable"},
    )
    assert result.evidence == []
    assert result.diagnostics["reason"] == "rg_unavailable"
    dumped = result.model_dump(mode="json")
    assert dumped["evidence"] == []
    assert "rg_unavailable" not in str(dumped["evidence"])
    unsupported = ProviderResult(
        status="unsupported",
        diagnostics={"reason": "language_unsupported", "detail": {"lang": "go"}},
    )
    assert unsupported.evidence == []
    assert not isinstance(unsupported.diagnostics, EvidenceItem)


def test_evidence_item_id_defaults_empty() -> None:
    item = EvidenceItem(text="hit", source="lexical")
    assert item.id == ""


def test_compute_evidence_item_id_stable() -> None:
    first = compute_evidence_item_id("snap", "lexical", "hit", "src/pkg/foo.py", "def foo")
    second = compute_evidence_item_id("snap", "lexical", "hit", "src/pkg/foo.py", "def foo")
    assert first == second
    assert len(first) == 64
    other = compute_evidence_item_id("snap", "lexical", "hit", "src/pkg/bar.py", "def foo")
    assert first != other


def test_protocol_signatures_importable() -> None:
    assert ContextBuilderV2 is ContextBuilderV2Direct
    query_hints = get_type_hints(RepositoryEvidenceProvider.query)
    assert query_hints["snapshot"] is RepoSnapshot
    assert query_hints["request"] is EvidenceQuery
    assert query_hints["return"] is ProviderResult
    build_hints = get_type_hints(ContextBuilderV2.build)
    assert build_hints["snapshot"] is RepoSnapshot
    assert build_hints["task"] is ContextTaskSpec
    assert build_hints["evidence_budget"] is EvidenceBudget
    assert build_hints["return"] is ContextBuildResult
    assert build_hints["return"] is not ContextPackV2
