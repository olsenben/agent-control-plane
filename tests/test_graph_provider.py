"""W1-C graph provider: neighbors, affected_tests, dependency_envelope, SHA isolation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from agent_control.context.providers.graph import GraphProvider
from agent_control.graph.store import GraphStore
from agent_shared.models.evidence_query import EvidenceQuery, ProviderResult
from agent_shared.models.repo_snapshot import RepoSnapshot

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vexp_mini_repo"


class _ForbiddenStore:
    """Planted store that must not be read on SHA mismatch."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"GraphStore must not be read on SHA mismatch ({name})")


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _copy_fixture_git(tmp_path: Path) -> tuple[Path, str]:
    dest = tmp_path / "vexp-mini"
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns("__pycache__", ".git"))
    init = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    if init.returncode != 0:
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, text=True, check=True)
    _git(dest, "config", "user.name", "t")
    _git(dest, "config", "user.email", "t@t")
    _git(dest, "add", ".")
    _git(dest, "commit", "-m", "init")
    sha = _git(dest, "rev-parse", "HEAD")
    return dest, sha


def _snapshot(workspace: Path, target_sha: str) -> RepoSnapshot:
    return RepoSnapshot(
        repository_id="eval/vexp-mini-repo",
        repository_url_or_key="eval/vexp-mini-repo",
        target_sha=target_sha,
        workspace_path=str(workspace),
        source_kind="eval",
    )


def _query(**overrides: object) -> EvidenceQuery:
    payload: dict[str, object] = {
        "query_text": "fix foo",
        "mentioned_paths": ["src/pkg/foo.py"],
        "requested_classes": ["dependency_edges", "tests", "config"],
    }
    payload.update(overrides)
    return EvidenceQuery.model_validate(payload)


def test_query_returns_provider_result_with_graph_evidence(tmp_path: Path) -> None:
    workspace, sha = _copy_fixture_git(tmp_path)
    provider = GraphProvider()
    result = provider.query(_snapshot(workspace, sha), _query())
    assert isinstance(result, ProviderResult)
    assert result.status == "ok"
    assert result.evidence
    sources = {item.source for item in result.evidence}
    assert "graph.test_covers" in sources or "graph.import" in sources
    assert all(item.id for item in result.evidence)
    assert result.diagnostics.get("graph_source") == "ephemeral"


def test_import_or_test_edges_exist_and_affected_tests_nonempty(tmp_path: Path) -> None:
    workspace, sha = _copy_fixture_git(tmp_path)
    provider = GraphProvider()
    result = provider.query(_snapshot(workspace, sha), _query())
    assert result.status == "ok"
    blob = " ".join(item.text for item in result.evidence)
    assert "foo" in blob
    tests = provider.affected_tests(["file:src/pkg/foo.py"])
    assert tests
    assert any(path.endswith("tests/test_foo.py") or path == "tests/test_foo.py" for path in tests)
    neighbors = provider.neighbors("file:src/pkg/foo.py", ["file_imports_file", "test_covers_file"], 2)
    assert neighbors
    kinds = {n["kind"] for n in neighbors}
    assert "file_imports_file" in kinds or "test_covers_file" in kinds
    envelope = provider.dependency_envelope(["src/pkg/foo.py"])
    assert envelope["tests"]
    assert "tests/test_foo.py" in envelope["tests"]
    assert envelope["config"] == [] or "pyproject.toml" in envelope["config"]
    assert envelope["nodes"]


def test_bar_import_or_test_edges_exist(tmp_path: Path) -> None:
    workspace, sha = _copy_fixture_git(tmp_path)
    provider = GraphProvider()
    result = provider.query(
        _snapshot(workspace, sha),
        _query(mentioned_paths=["src/pkg/bar.py", "src/pkg/foo.py"]),
    )
    assert result.status == "ok"
    neighbors = provider.neighbors("file:src/pkg/bar.py", ["file_imports_file", "test_covers_file"], 2)
    neighbor_ids = {n["node_id"] for n in neighbors}
    assert neighbors
    assert "file:src/pkg/foo.py" in neighbor_ids or any("test_foo" in n["node_id"] for n in neighbors)


def test_sha_mismatch_error_does_not_read_store(tmp_path: Path) -> None:
    workspace, sha = _copy_fixture_git(tmp_path)
    planted = GraphStore(tmp_path / "planted.sqlite")
    planted.init_schema()
    planted.upsert_snapshot(
        "eval/vexp-mini-repo",
        files=["planted.py"],
        services=[],
        tests=[],
        adrs=[],
        edges=[
            {
                "kind": "file_imports_file",
                "src_kind": "file",
                "src": "file:planted.py",
                "dst_kind": "file",
                "dst": "file:stale.py",
                "confidence": "high",
                "provenance": "manual",
            }
        ],
        source_sha="deadbeef" * 5,
    )
    provider = GraphProvider(store=_ForbiddenStore())  # type: ignore[arg-type]
    wrong = "0" * 40
    assert wrong != sha
    result = provider.query(_snapshot(workspace, wrong), _query())
    assert result.status == "error"
    assert result.evidence == []
    assert result.diagnostics.get("reason") == "sha_mismatch"
    blob = " ".join(item.text for item in result.evidence)
    assert "planted.py" not in blob


def test_stale_store_source_sha_does_not_use_planted_edges(tmp_path: Path) -> None:
    workspace, sha = _copy_fixture_git(tmp_path)
    store = GraphStore(tmp_path / "stale.sqlite")
    store.init_schema()
    store.upsert_snapshot(
        "eval/vexp-mini-repo",
        files=["planted.py"],
        services=[],
        tests=["tests/test_planted.py"],
        adrs=[],
        edges=[
            {
                "kind": "file_imports_file",
                "src_kind": "file",
                "src": "file:planted.py",
                "dst_kind": "file",
                "dst": "file:stale.py",
                "confidence": "high",
                "provenance": "manual",
            },
            {
                "kind": "test_covers_file",
                "src_kind": "test",
                "src": "test:tests/test_planted.py",
                "dst_kind": "file",
                "dst": "file:src/pkg/foo.py",
                "confidence": "high",
                "provenance": "manual",
            },
        ],
        source_sha="not-the-workspace-head",
    )

    class _NoListStore(GraphStore):
        def list_edges(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            raise AssertionError("stale GraphStore.list_edges must not be used")

    provider = GraphProvider(store=_NoListStore(tmp_path / "stale.sqlite"))
    result = provider.query(_snapshot(workspace, sha), _query())
    assert result.status == "ok"
    assert result.diagnostics.get("graph_source") == "ephemeral"
    blob = " ".join(item.text for item in result.evidence) + " ".join(
        item.source for item in result.evidence
    )
    assert "planted.py" not in blob
    assert "test_planted" not in blob
    tests = provider.affected_tests(["file:src/pkg/foo.py"])
    assert "tests/test_foo.py" in tests
    assert "tests/test_planted.py" not in tests


def test_no_state_predicate_on_provider() -> None:
    assert not hasattr(GraphProvider, "state_predicate")
    assert "state_predicate" not in GraphProvider.__dict__


def test_provider_failure_is_provider_result_not_evidence(tmp_path: Path) -> None:
    missing = tmp_path / "no-git-here"
    missing.mkdir()
    snap = _snapshot(missing, "abc123")
    result = GraphProvider().query(snap, _query())
    assert result.status == "error"
    assert result.evidence == []
    assert isinstance(result, ProviderResult)
