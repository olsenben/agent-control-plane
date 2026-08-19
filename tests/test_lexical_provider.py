"""W1-A LexicalEvidenceProvider tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent_control.context.providers.lexical import (
    LexicalEvidenceProvider,
    normalize_query_terms,
)
from agent_control.context.repo_snapshot import from_eval
from agent_shared.models.evidence_query import EvidenceQuery
from agent_shared.models.repo_snapshot import RepoSnapshot

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vexp_mini_repo"


def _copy_init_eval(tmp_path: Path) -> RepoSnapshot:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    subprocess.check_call(["git", "init"], cwd=dest)
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "."],
        cwd=dest,
    )
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init"],
        cwd=dest,
    )
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=dest,
        text=True,
    ).strip()
    return from_eval("vexp/mini", head, dest)


def _query() -> EvidenceQuery:
    return EvidenceQuery(
        query_text="fix foo in pkg",
        failure_signature="AssertionError: foo",
        mentioned_paths=["src/pkg/foo.py"],
        mentioned_symbols=["bar"],
    )


def test_same_query_twice_same_ordered_ids(tmp_path: Path) -> None:
    if shutil.which("rg") is None:
        pytest.skip("rg not installed")
    snapshot = _copy_init_eval(tmp_path)
    provider = LexicalEvidenceProvider()
    request = _query()
    first = provider.query(snapshot, request)
    second = provider.query(snapshot, request)
    assert first.status == "ok"
    assert second.status == "ok"
    first_ids = [item.id for item in first.evidence]
    second_ids = [item.id for item in second.evidence]
    assert first_ids == second_ids
    assert first_ids
    assert all(item.source == "lexical.rg" for item in first.evidence)
    assert all(item.id for item in first.evidence)


def test_zero_hits_is_ok_not_unavailable(tmp_path: Path) -> None:
    if shutil.which("rg") is None:
        pytest.skip("rg not installed")
    snapshot = _copy_init_eval(tmp_path)
    result = LexicalEvidenceProvider().query(
        snapshot,
        EvidenceQuery(query_text="zzzznotfoundtermxyz"),
    )
    assert result.status == "ok"
    assert result.evidence == []
    assert result.diagnostics.get("reason") != "rg_unavailable"


def test_missing_rg_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    snapshot = _copy_init_eval(tmp_path)
    real_which = shutil.which

    def _which(name: str, *args: object, **kwargs: object) -> str | None:
        if name == "rg":
            return None
        return real_which(name, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", _which)
    result = LexicalEvidenceProvider().query(snapshot, _query())
    assert result.status == "unavailable"
    assert result.diagnostics.get("reason") == "rg_unavailable"
    assert result.evidence == []


def test_wrong_sha_is_error(tmp_path: Path) -> None:
    snapshot = _copy_init_eval(tmp_path)
    mismatched = RepoSnapshot(
        repository_id=snapshot.repository_id,
        repository_url_or_key=snapshot.repository_url_or_key,
        target_sha="c" * 40,
        workspace_path=snapshot.workspace_path,
        source_kind="eval",
    )
    result = LexicalEvidenceProvider().query(mismatched, _query())
    assert result.status == "error"
    assert result.diagnostics.get("reason") == "sha_mismatch"
    assert result.evidence == []


def test_quoted_path_and_symbols_preserved() -> None:
    terms = normalize_query_terms(
        EvidenceQuery(
            query_text='fix the leak in "src/pkg/foo.py"',
            failure_signature="bar failed",
            mentioned_symbols=["foo"],
        )
    )
    assert "src/pkg/foo.py" in terms
    assert "foo" in terms
    assert "bar" in terms
    assert "the" not in terms
    assert "in" not in terms
    assert terms.index("src/pkg/foo.py") < terms.index("bar")


def test_provider_does_not_mutate_git_head() -> None:
    import agent_control.context.providers.lexical as lexical_mod
    import agent_control.context.providers.rg as rg_mod

    for module in (lexical_mod, rg_mod):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert '["git", "checkout"' not in source
        assert '["git", "clone"' not in source
        assert '["git", "fetch"' not in source
        assert "rev-parse" in source or "rg" in source
