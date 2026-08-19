"""W1-B Python symbol index and SymbolEvidenceProvider tests."""

from __future__ import annotations

import inspect
import shutil
import subprocess
from pathlib import Path

from agent_control.context.indexes.python_symbols import (
    PythonSymbolIndex,
    find_symbol,
    references_to,
    symbol_signature,
    symbols_in_file,
)
from agent_control.context.providers.symbols import SymbolEvidenceProvider
from agent_control.context.repo_snapshot import from_eval
from agent_shared.models.evidence_query import EvidenceQuery, compute_evidence_item_id
from agent_shared.models.repo_snapshot import RepoSnapshot

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vexp_mini_repo"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _git_copy_mini(tmp_path: Path) -> tuple[Path, str]:
    dest = tmp_path / "mini"
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    init = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    if init.returncode != 0:
        _git(dest, "init")
    _git(dest, "config", "user.name", "t")
    _git(dest, "config", "user.email", "t@t")
    _git(dest, "add", ".")
    _git(dest, "commit", "-m", "init")
    sha = _git(dest, "rev-parse", "HEAD").stdout.strip()
    return dest, sha


def _index(repo: Path, sha: str) -> PythonSymbolIndex:
    return PythonSymbolIndex.build(repo, sha, index_generation="0")


def test_find_symbol_foo_on_mini_fixture(tmp_path: Path) -> None:
    repo, sha = _git_copy_mini(tmp_path)
    index = _index(repo, sha)
    hits = find_symbol(index, "foo")
    assert hits
    assert any(h.name == "foo" and h.path == "src/pkg/foo.py" for h in hits)
    foo = next(h for h in hits if h.path == "src/pkg/foo.py")
    assert foo.kind == "function"
    assert "foo" in foo.signature
    assert sha in foo.symbol_id


def test_symbols_in_file_and_signature(tmp_path: Path) -> None:
    repo, sha = _git_copy_mini(tmp_path)
    index = _index(repo, sha)
    in_foo = symbols_in_file(index, "src/pkg/foo.py")
    assert [h.name for h in in_foo] == ["foo"]
    sig = symbol_signature(index, in_foo[0].symbol_id)
    assert sig is not None
    assert "def foo" in sig
    in_bar = symbols_in_file(index, "src/pkg/bar.py")
    assert any(h.name == "bar" for h in in_bar)


def test_references_to_foo_from_bar(tmp_path: Path) -> None:
    repo, sha = _git_copy_mini(tmp_path)
    index = _index(repo, sha)
    foo = find_symbol(index, "foo")[0]
    refs = references_to(index, foo.symbol_id)
    assert any(r.path == "src/pkg/bar.py" for r in refs)


def test_provider_query_maps_to_evidence_items_with_ids(tmp_path: Path) -> None:
    repo, sha = _git_copy_mini(tmp_path)
    snap = from_eval("vexp/mini", sha, repo)
    result = SymbolEvidenceProvider().query(
        snap,
        EvidenceQuery(query_text="fix foo", mentioned_symbols=["foo"]),
    )
    assert result.status == "ok"
    assert result.evidence
    assert all(item.id for item in result.evidence)
    sources = {item.source for item in result.evidence}
    assert "symbol.declaration" in sources
    assert "symbol.reference" in sources
    assert any("foo.py" in item.text for item in result.evidence)
    assert any("bar.py" in item.text for item in result.evidence)
    for item in result.evidence:
        assert "language_unsupported" not in item.text
        assert item.source.startswith("symbol.")
    decl = next(item for item in result.evidence if item.source == "symbol.declaration")
    expected = compute_evidence_item_id(
        snap.snapshot_id,
        "symbols",
        "declaration",
        "src/pkg/foo.py",
        (
            f"{snap.target_sha}:{snap.index_generation}:"
            f"declaration:foo:{next(h.start_line for h in find_symbol(_index(repo, sha), 'foo'))}:"
            f"{next(h.signature for h in find_symbol(_index(repo, sha), 'foo'))}"
        ),
    )
    assert decl.id == expected
    assert sha in str(decl.provenance)


def test_non_python_workspace_is_unsupported(tmp_path: Path) -> None:
    repo = tmp_path / "go-only"
    repo.mkdir()
    (repo / "main.go").write_text("package main\nfunc foo() {}\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    snap = from_eval("vexp/go-only", sha, repo)
    result = SymbolEvidenceProvider().query(
        snap,
        EvidenceQuery(mentioned_symbols=["foo"], mentioned_paths=["main.go"]),
    )
    assert result.status == "unsupported"
    assert result.evidence == []
    assert result.diagnostics["reason"] == "language_unsupported"
    dumped = result.model_dump(mode="json")
    assert dumped["evidence"] == []
    assert "language_unsupported" not in str(dumped["evidence"])


def test_non_python_query_path_unsupported_in_mixed_repo(tmp_path: Path) -> None:
    repo, sha = _git_copy_mini(tmp_path)
    (repo / "main.go").write_text("package main\n", encoding="utf-8")
    snap = from_eval("vexp/mini", sha, repo)
    result = SymbolEvidenceProvider().query(
        snap,
        EvidenceQuery(mentioned_paths=["main.go"], query_text="foo"),
    )
    assert result.status == "unsupported"
    assert result.evidence == []
    assert result.diagnostics["reason"] == "language_unsupported"


def test_sha_mismatch_is_error(tmp_path: Path) -> None:
    repo, sha = _git_copy_mini(tmp_path)
    wrong = "a" * 40
    assert wrong != sha
    snap = RepoSnapshot(
        repository_id="vexp/mini",
        repository_url_or_key="vexp/mini",
        target_sha=wrong,
        workspace_path=str(repo),
        source_kind="eval",
    )
    result = SymbolEvidenceProvider().query(snap, EvidenceQuery(mentioned_symbols=["foo"]))
    assert result.status == "error"
    assert result.evidence == []
    assert result.diagnostics["reason"] == "sha_mismatch"
    assert result.diagnostics["detail"]["actual"] == sha
    assert result.diagnostics["detail"]["requested"] == wrong


def test_query_does_not_mutate_git(tmp_path: Path) -> None:
    repo, sha = _git_copy_mini(tmp_path)
    snap = from_eval("vexp/mini", sha, repo)
    before_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    before_status = _git(repo, "status", "--porcelain").stdout
    SymbolEvidenceProvider().query(snap, EvidenceQuery(mentioned_symbols=["foo"]))
    after_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    after_status = _git(repo, "status", "--porcelain").stdout
    assert before_head == after_head == sha
    assert before_status == after_status


def test_provider_modules_do_not_checkout() -> None:
    import agent_control.context.indexes.python_symbols as index_mod
    import agent_control.context.providers.symbols as provider_mod

    for mod in (index_mod, provider_mod):
        source = inspect.getsource(mod)
        assert "git checkout" not in source
        assert "git reset" not in source
        assert "find_callers" not in source
        assert "state_predicate" not in source
