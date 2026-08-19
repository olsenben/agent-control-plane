"""W0-A RepoSnapshot identity and adapter tests."""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import pytest

from agent_control.context.repo_snapshot import (
    RepoSnapshotError,
    from_eval,
    from_production,
)
from agent_control.project_registry import RefResolution
from agent_control.repo_snapshot import snapshot_repo
from agent_shared.models.repo_snapshot import RepoSnapshot, compute_snapshot_id

SHA_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _refs(target_sha: str | None) -> RefResolution:
    return RefResolution(
        policy_ref="main",
        policy_sha=None,
        task_ref="HEAD",
        task_sha=None,
        base_ref="main",
        target_sha=target_sha,
        primary_branch="main",
    )


def _snapshot(
    *,
    repository_id: str = "acme/widgets",
    target_sha: str = SHA_A,
    workspace_path: str = "/tmp/ws-a",
    index_generation: str = "0",
    source_kind: str = "gitea",
) -> RepoSnapshot:
    return RepoSnapshot(
        repository_id=repository_id,
        repository_url_or_key=f"https://gitea.example/{repository_id}",
        target_sha=target_sha,
        workspace_path=workspace_path,
        lineage_id="lin-1",
        source_kind=source_kind,  # type: ignore[arg-type]
        index_generation=index_generation,
    )


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


def test_same_repo_and_sha_same_snapshot_id() -> None:
    first = _snapshot()
    second = _snapshot()
    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_id == compute_snapshot_id("acme/widgets", SHA_A)
    assert len(first.snapshot_id) == 64


def test_different_sha_different_snapshot_id() -> None:
    assert _snapshot(target_sha=SHA_A).snapshot_id != _snapshot(target_sha=SHA_B).snapshot_id


def test_workspace_path_does_not_affect_snapshot_id() -> None:
    left = _snapshot(workspace_path="/tmp/checkout-a")
    right = _snapshot(workspace_path="/var/other/checkout-b")
    assert left.repository_id == right.repository_id
    assert left.target_sha == right.target_sha
    assert left.workspace_path != right.workspace_path
    assert left.snapshot_id == right.snapshot_id


def test_different_repository_id_different_snapshot_id() -> None:
    left = _snapshot(repository_id="acme/widgets")
    right = _snapshot(repository_id="acme/gadgets")
    assert left.target_sha == right.target_sha
    assert left.snapshot_id != right.snapshot_id


def test_index_generation_does_not_affect_snapshot_id() -> None:
    left = _snapshot(index_generation="0")
    right = _snapshot(index_generation="9")
    assert left.index_generation != right.index_generation
    assert left.snapshot_id == right.snapshot_id


def test_eval_adapter_raises_on_head_mismatch(tmp_path: Path) -> None:
    repo = tmp_path / "eval-repo"
    head = _init_repo(repo)
    future = "c" * 40
    assert head != future
    with pytest.raises(RepoSnapshotError, match="exact-SHA invariant failed"):
        from_eval("synthlab/retry-toolkit", future, repo)


def test_eval_adapter_accepts_matching_head(tmp_path: Path) -> None:
    repo = tmp_path / "eval-repo"
    head = _init_repo(repo)
    snap = from_eval("synthlab/retry-toolkit", head, repo, index_generation="3")
    assert snap.source_kind == "eval"
    assert snap.target_sha == head
    assert snap.snapshot_id == compute_snapshot_id("synthlab/retry-toolkit", head)
    assert snap.workspace_path == str(repo)


def test_production_adapter_uses_target_sha_and_skips_missing() -> None:
    snap = from_production(
        "acme/widgets",
        _refs(SHA_A),
        "/mnt/cache/acme-widgets",
        repository_url_or_key="https://gitea.example/acme/widgets",
    )
    assert snap.source_kind == "gitea"
    assert snap.target_sha == SHA_A
    assert snap.snapshot_id == compute_snapshot_id("acme/widgets", SHA_A)
    with pytest.raises(RepoSnapshotError, match="target_sha missing"):
        from_production("acme/widgets", _refs(None), "/mnt/cache/acme-widgets")


def test_production_adapter_module_source_has_no_eval_package_name() -> None:
    import agent_control.context.repo_snapshot as adapter

    source = inspect.getsource(adapter)
    assert "maintenance_evals" not in source
    assert "maintenance_evals" not in Path(adapter.__file__).read_text(encoding="utf-8")


def test_constructing_snapshot_does_not_call_compile_context_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent_control.context.repo_snapshot as adapter
    import agent_shared.models.repo_snapshot as model

    assert "compile_context_pack" not in inspect.getsource(adapter)
    assert "compile_context_pack" not in inspect.getsource(model)

    called = {"n": 0}

    def _boom(*_args: object, **_kwargs: object) -> None:
        called["n"] += 1
        raise AssertionError("compile_context_pack must not run during snapshot construction")

    monkeypatch.setattr("agent_control.graph.context_pack.compile_context_pack", _boom)
    snap = _snapshot()
    prod = from_production("acme/widgets", _refs(SHA_A), "/tmp/ws-prod")
    assert snap.snapshot_id
    assert prod.snapshot_id == snap.snapshot_id
    assert called["n"] == 0


def test_snapshot_stub(tmp_path: Path) -> None:
    result = snapshot_repo("ai-sdlc-lab", "demo-app", "main", tmp_path)
    assert result["owner"] == "ai-sdlc-lab"
    assert result["status"] == "stub"
