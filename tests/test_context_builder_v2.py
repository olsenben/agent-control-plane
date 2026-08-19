"""W1-D ContextBuilderV2 tests against fake providers. No real W1-A/B/C imports."""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import pytest

from agent_control.context.builder import ContextBuilder, recheck_exact_sha
from agent_control.context.repo_snapshot import from_eval
from agent_control.context.v1_adapter import render_v2
from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.context_pack_v2 import EvidenceItem
from agent_shared.models.evidence_query import (
    ContextBuildResult,
    ContextTaskSpec,
    EvidenceBudget,
    EvidenceQuery,
    ProviderResult,
    compute_evidence_item_id,
)
from agent_shared.models.repo_snapshot import RepoSnapshot
from agent_shared.protocols.context import ContextBuilderV2

SHA_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
RG_UNAVAILABLE = "rg_unavailable"


class FakeProvider:
    def __init__(self, result: ProviderResult) -> None:
        self.result = result
        self.calls: list[EvidenceQuery] = []

    def query(self, snapshot: RepoSnapshot, request: EvidenceQuery) -> ProviderResult:
        del snapshot
        self.calls.append(request)
        return self.result


def _budget(**overrides: object) -> EvidenceBudget:
    payload: dict[str, object] = {
        "max_items_by_class": {
            "lexical": 8,
            "symbols": 8,
            "dependency_edges": 8,
            "tests": 8,
            "config": 8,
            "architecture": 8,
        },
        "max_chars_total": 4000,
        "max_snippet_chars": 400,
    }
    payload.update(overrides)
    return EvidenceBudget.model_validate(payload)


def _task(**overrides: object) -> ContextTaskSpec:
    payload: dict[str, object] = {
        "project": "acme/widgets",
        "issue_text": "Fix `foo` in src/pkg/foo.py",
        "failure_signature": "AssertionError: foo",
    }
    payload.update(overrides)
    return ContextTaskSpec.model_validate(payload)


def _snapshot(*, workspace_path: str = "/tmp/ws-missing-vexp-w1d") -> RepoSnapshot:
    return RepoSnapshot(
        repository_id="acme/widgets",
        repository_url_or_key="https://gitea.example/acme/widgets",
        target_sha=SHA_A,
        workspace_path=workspace_path,
        lineage_id="lin-w1d",
        source_kind="eval",
        index_generation="0",
    )


def _item(
    snapshot: RepoSnapshot,
    *,
    provider: str,
    evidence_type: str,
    path_or_node: str,
    text: str,
    source: str,
) -> EvidenceItem:
    return EvidenceItem(
        text=text,
        source=source,
        provenance=[provider],
        id=compute_evidence_item_id(
            snapshot.snapshot_id, provider, evidence_type, path_or_node, text
        ),
    )


def _ok_lexical(snapshot: RepoSnapshot, text: str = "def foo(): pass") -> FakeProvider:
    return FakeProvider(
        ProviderResult(
            status="ok",
            evidence=[
                _item(
                    snapshot,
                    provider="lexical",
                    evidence_type="hit",
                    path_or_node="src/pkg/foo.py",
                    text=text,
                    source="lexical",
                )
            ],
        )
    )


def _pass_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent_control.context.builder.recheck_exact_sha", lambda _snapshot: None)


def _init_repo(path: Path) -> str:
    path.mkdir(parents=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.check_call(["git", "init"], cwd=path)
    subprocess.check_call(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "."], cwd=path)
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init"],
        cwd=path,
    )
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def test_build_returns_context_build_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _pass_sha(monkeypatch)
    snapshot = _snapshot()
    lexical = _ok_lexical(snapshot)
    result = ContextBuilder(lexical=lexical).build(snapshot, _task(), _budget())
    assert isinstance(result, ContextBuildResult)
    assert result.context_pack.schema_version == "context-pack.v2"
    assert result.context_pack.current_evidence.lexical
    assert result.context_pack.current_evidence.lexical[0].id
    assert result.build_trace.providers_invoked == ["lexical"]
    assert result.build_trace.provider_statuses["lexical"] == "ok"
    assert result.build_trace.selected_counts["lexical"] == 1
    assert result.build_trace.selected_evidence_ids == [
        result.context_pack.current_evidence.lexical[0].id
    ]


def test_same_inputs_same_pack_hash_and_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    _pass_sha(monkeypatch)
    snapshot = _snapshot()
    item = _item(
        snapshot,
        provider="lexical",
        evidence_type="hit",
        path_or_node="src/pkg/foo.py",
        text="def foo(): pass",
        source="lexical",
    )
    builder = ContextBuilder(lexical=FakeProvider(ProviderResult(status="ok", evidence=[item])))
    task = _task()
    budget = _budget()
    first = builder.build(snapshot, task, budget)
    second = builder.build(snapshot, task, budget)
    first_hash = canonical_json_hash(first.context_pack.model_dump(mode="json"))
    second_hash = canonical_json_hash(second.context_pack.model_dump(mode="json"))
    assert first_hash == second_hash
    assert first.build_trace.model_dump(mode="json") == second.build_trace.model_dump(mode="json")
    assert first.context_pack.experience.authorized_records == []


def test_unavailable_lexical_does_not_put_rg_unavailable_in_render_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pass_sha(monkeypatch)
    snapshot = _snapshot()
    leaked = EvidenceItem(
        text=f"should-not-surface {RG_UNAVAILABLE}",
        source="lexical",
        id=compute_evidence_item_id(snapshot.snapshot_id, "lexical", "hit", "x", "y"),
    )
    lexical = FakeProvider(
        ProviderResult(
            status="unavailable",
            evidence=[leaked],
            diagnostics={"reason": RG_UNAVAILABLE},
        )
    )
    result = ContextBuilder(lexical=lexical).build(
        snapshot,
        _task(issue_text="Fix the timeout handler"),
        _budget(),
    )
    assert result.context_pack.current_evidence.lexical == []
    assert result.build_trace.provider_statuses["lexical"] == "unavailable"
    visible = render_v2(result.context_pack)
    assert RG_UNAVAILABLE not in visible
    assert "legacy_prior_memory" not in visible


def test_budget_drop_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    _pass_sha(monkeypatch)
    snapshot = _snapshot()
    items = [
        _item(
            snapshot,
            provider="lexical",
            evidence_type="hit",
            path_or_node=f"src/pkg/foo{i}.py",
            text=f"item-{i}-" + ("x" * 20),
            source="lexical",
        )
        for i in range(3)
    ]
    lexical = FakeProvider(ProviderResult(status="ok", evidence=items))
    result = ContextBuilder(lexical=lexical).build(
        snapshot,
        _task(),
        _budget(max_items_by_class={"lexical": 1}, max_chars_total=4000, max_snippet_chars=400),
    )
    assert len(result.context_pack.current_evidence.lexical) == 1
    assert result.build_trace.candidate_counts["lexical"] == 3
    assert result.build_trace.selected_counts["lexical"] == 1
    assert result.build_trace.dropped_by_budget["lexical"] == 2
    assert result.build_trace.chars_by_class["lexical"] == len(items[0].text)
    assert result.build_trace.total_chars == len(items[0].text)


def test_char_budget_drops_overflow(monkeypatch: pytest.MonkeyPatch) -> None:
    _pass_sha(monkeypatch)
    snapshot = _snapshot()
    items = [
        _item(
            snapshot,
            provider="lexical",
            evidence_type="hit",
            path_or_node=f"src/a{i}.py",
            text="a" * 100,
            source="lexical",
        )
        for i in range(3)
    ]
    lexical = FakeProvider(ProviderResult(status="ok", evidence=items))
    result = ContextBuilder(lexical=lexical).build(
        snapshot,
        _task(),
        _budget(max_items_by_class={"lexical": 8}, max_chars_total=150, max_snippet_chars=100),
    )
    assert result.build_trace.selected_counts["lexical"] == 1
    assert result.build_trace.dropped_by_budget["lexical"] == 2
    assert result.build_trace.total_chars == 100


def test_authorized_records_empty_even_when_sequence_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pass_sha(monkeypatch)
    snapshot = _snapshot()
    result = ContextBuilder(lexical=_ok_lexical(snapshot)).build(
        snapshot,
        _task(),
        _budget(),
        authorized_experience=({"id": "should-not-authorize"},),
    )
    assert result.context_pack.experience.authorized_records == []
    assert result.context_pack.experience.candidates_considered == []
    assert result.context_pack.experience.rejected_records == []
    assert result.context_pack.experience.compatibility.legacy_prior_memory == []
    assert result.context_pack.recursive_evidence == []
    visible = render_v2(result.context_pack)
    assert "should-not-authorize" not in visible
    assert "legacy_prior_memory" not in visible


def test_missing_workspace_fails_closed_without_crash() -> None:
    snapshot = _snapshot(workspace_path="")
    result = ContextBuilder(lexical=_ok_lexical(snapshot)).build(snapshot, _task(), _budget())
    assert result.context_pack.current_evidence.lexical == []
    assert result.build_trace.provider_statuses.get("exact_sha") == "error"
    assert result.build_trace.providers_invoked == []
    assert result.context_pack.experience.authorized_records == []


def test_from_eval_git_fixture_sha_recheck(tmp_path: Path) -> None:
    repo = tmp_path / "eval-repo"
    head = _init_repo(repo)
    snapshot = from_eval("acme/widgets", head, repo)
    lexical = _ok_lexical(snapshot)
    result = ContextBuilder(lexical=lexical).build(snapshot, _task(), _budget())
    assert result.build_trace.provider_statuses["lexical"] == "ok"
    assert result.context_pack.current_evidence.lexical
    assert result.context_pack.task.source_sha == head


def test_head_mismatch_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "eval-repo"
    _init_repo(repo)
    snapshot = RepoSnapshot(
        repository_id="acme/widgets",
        repository_url_or_key="acme/widgets",
        target_sha="c" * 40,
        workspace_path=str(repo),
        source_kind="eval",
    )
    result = ContextBuilder(lexical=_ok_lexical(snapshot)).build(snapshot, _task(), _budget())
    assert result.context_pack.current_evidence.lexical == []
    assert result.build_trace.provider_statuses.get("exact_sha") == "error"


def test_non_ok_statuses_do_not_fill_current_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    _pass_sha(monkeypatch)
    snapshot = _snapshot()
    symbol = FakeProvider(
        ProviderResult(
            status="unsupported",
            evidence=[
                _item(
                    snapshot,
                    provider="symbol",
                    evidence_type="decl",
                    path_or_node="src/pkg/foo.py",
                    text="language_unsupported",
                    source="symbols",
                )
            ],
            diagnostics={"reason": "language_unsupported"},
        )
    )
    graph = FakeProvider(
        ProviderResult(
            status="error",
            evidence=[
                _item(
                    snapshot,
                    provider="graph",
                    evidence_type="edge",
                    path_or_node="src/pkg/foo.py",
                    text="graph exploded",
                    source="dependency_edges",
                )
            ],
            diagnostics={"reason": "boom"},
        )
    )
    result = ContextBuilder(symbol=symbol, graph=graph).build(snapshot, _task(), _budget())
    assert result.context_pack.current_evidence.symbols == []
    assert result.context_pack.current_evidence.dependency_edges == []
    assert result.build_trace.provider_statuses["symbol"] == "unsupported"
    assert result.build_trace.provider_statuses["graph"] == "error"
    visible = render_v2(result.context_pack)
    assert "language_unsupported" not in visible
    assert "graph exploded" not in visible


def test_callable_providers_and_class_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    _pass_sha(monkeypatch)
    snapshot = _snapshot()

    def lexical_fn(_snapshot: RepoSnapshot, _request: EvidenceQuery) -> ProviderResult:
        return ProviderResult(
            status="ok",
            evidence=[
                _item(
                    snapshot,
                    provider="lexical",
                    evidence_type="hit",
                    path_or_node="src/pkg/foo.py",
                    text="lexical-hit",
                    source="lexical",
                )
            ],
        )

    def symbol_fn(_snapshot: RepoSnapshot, _request: EvidenceQuery) -> ProviderResult:
        return ProviderResult(
            status="ok",
            evidence=[
                _item(
                    snapshot,
                    provider="symbol",
                    evidence_type="decl",
                    path_or_node="src/pkg/foo.py",
                    text="symbol-hit",
                    source="symbols",
                )
            ],
        )

    def graph_fn(_snapshot: RepoSnapshot, _request: EvidenceQuery) -> ProviderResult:
        return ProviderResult(
            status="ok",
            evidence=[
                _item(
                    snapshot,
                    provider="graph",
                    evidence_type="edge",
                    path_or_node="src/pkg/foo.py",
                    text="dep-hit",
                    source="dependency_edges",
                ),
                _item(
                    snapshot,
                    provider="graph",
                    evidence_type="test",
                    path_or_node="tests/test_foo.py",
                    text="test-hit",
                    source="tests",
                ),
                _item(
                    snapshot,
                    provider="graph",
                    evidence_type="config",
                    path_or_node="pyproject.toml",
                    text="config-hit",
                    source="config",
                ),
                _item(
                    snapshot,
                    provider="graph",
                    evidence_type="adr",
                    path_or_node="docs/adr/0001.md",
                    text="arch-hit",
                    source="architecture",
                ),
            ],
        )

    result = ContextBuilder(lexical=lexical_fn, symbol=symbol_fn, graph=graph_fn).build(
        snapshot, _task(), _budget()
    )
    evidence = result.context_pack.current_evidence
    assert [item.text for item in evidence.lexical] == ["lexical-hit"]
    assert [item.text for item in evidence.symbols] == ["symbol-hit"]
    assert [item.text for item in evidence.dependency_edges] == ["dep-hit"]
    assert [item.text for item in evidence.tests] == ["test-hit"]
    assert [item.text for item in evidence.config] == ["config-hit"]
    assert [item.text for item in evidence.architecture] == ["arch-hit"]
    assert result.build_trace.providers_invoked == ["lexical", "symbol", "graph"]


def test_builder_is_pure_and_matches_protocol() -> None:
    from typing import get_type_hints

    hints = inspect.signature(ContextBuilder.build)
    assert "authorized_experience" in hints.parameters
    type_hints = get_type_hints(ContextBuilder.build)
    assert type_hints["return"] is ContextBuildResult
    module_source = Path(inspect.getfile(ContextBuilder)).read_text(encoding="utf-8")
    assert "emit_experience_event" not in module_source
    assert "agent_control.context.providers" not in module_source
    assert "agent_control.telemetry" not in module_source
    builder: ContextBuilderV2 = ContextBuilder()
    assert callable(builder.build)


def test_recheck_exact_sha_missing_path() -> None:
    snapshot = _snapshot(workspace_path="   ")
    assert recheck_exact_sha(snapshot) == "workspace_path_missing"
