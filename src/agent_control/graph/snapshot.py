"""Graph snapshot indexer."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git import GitCommandError, Repo

from agent_control.adr_compiler import compile_adrs
from agent_control.config import Settings, get_settings
from agent_control.git_auth import git_non_interactive_env, resolve_authenticated_repo_url
from agent_control.graph.catalog import ingest_catalog
from agent_control.graph.extractors.packages import extract_package_edges
from agent_control.graph.extractors.python_imports import extract_file_import_edges
from agent_control.graph.extractors.sdlc_evidence import (
    extract_adr_constrain_edges,
    extract_event_sdlc_edges,
    extract_pipeline_edges,
    extract_test_covers_edges,
)
from agent_control.graph.provenance import (
    EXTRACTOR_VERSION,
    LANGUAGES_SUPPORTED,
    annotate_edge,
    edge_kind_counts,
    provenance_counts,
)
from agent_control.graph.store import GraphStore
from agent_control.project_registry import load_project_registry, resolve_project


def _sync_cached_repo(repo: Repo, branch: str, git_env: dict[str, str]) -> None:
    """Refresh shallow cache to match origin without merge/rebase prompts."""
    repo.remotes.origin.fetch(depth=1, env=git_env)
    repo.git.checkout(branch)
    repo.git.reset("--hard", f"origin/{branch}")


def _clone_or_update(project: str, dest: Path, settings: Settings) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cfg = resolve_project(project, settings=settings)
    clone_url = resolve_authenticated_repo_url(cfg.repo_url, settings)
    git_env = git_non_interactive_env(settings, repo_url=clone_url)
    try:
        if dest.exists() and (dest / ".git").exists():
            try:
                repo = Repo(dest)
                if clone_url != repo.remotes.origin.url:
                    repo.remotes.origin.set_url(clone_url)
                _sync_cached_repo(repo, cfg.default_branch, git_env)
                return dest
            except (GitCommandError, OSError, ValueError):
                shutil.rmtree(dest, ignore_errors=True)
        if dest.exists():
            shutil.rmtree(dest)
        try:
            Repo.clone_from(
                clone_url,
                dest,
                depth=1,
                branch=cfg.default_branch,
                env=git_env,
            )
        except GitCommandError as branch_exc:
            stderr = (branch_exc.stderr or str(branch_exc)).lower()
            if "remote branch" not in stderr and "not found in upstream origin" not in stderr:
                raise
            if dest.exists():
                shutil.rmtree(dest)
            Repo.clone_from(clone_url, dest, depth=1, env=git_env)
            repo = Repo(dest)
            if not repo.heads:
                raise RuntimeError(
                    f"repository has no commits or no branch {cfg.default_branch!r}: {project}"
                ) from branch_exc
        return dest
    except GitCommandError as exc:
        shutil.rmtree(dest, ignore_errors=True)
        hint = (
            "Set GITEA_BOT_TOKEN in .env, mount deploy ~/.git-credentials on control-plane "
            "(see docker-compose.yml), or pass --local-path to index a checkout on disk."
        )
        raise RuntimeError(f"git clone/fetch failed for {project}: {exc.stderr or exc}. {hint}") from exc
    except RuntimeError:
        shutil.rmtree(dest, ignore_errors=True)
        raise


def _resolve_source_sha(repo_root: Path) -> str:
    try:
        return Repo(repo_root).head.commit.hexsha
    except Exception:  # noqa: BLE001 — snapshot still useful without SHA
        return ""


def ingest_repo_path(
    project: str,
    repo_root: Path,
    store: GraphStore,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    warnings: list[str] = []
    component, catalog_edge_rows = ingest_catalog(project, repo_root)
    services: list[str] = []
    if component:
        services.append(component.name)

    adr_dir = repo_root / "docs" / "adr"
    adr_facts = compile_adrs(adr_dir)
    adrs = [
        {
            "adr_id": f["adr_id"],
            "title": f.get("title", ""),
            "source_path": f.get("source_path", ""),
        }
        for f in adr_facts
    ]

    py_files, import_edges, import_warnings = extract_file_import_edges(project, repo_root)
    warnings.extend(import_warnings)

    tests: list[str] = []
    edges: list[dict[str, str]] = list(catalog_edge_rows)
    edges.extend(import_edges)

    for path in py_files:
        edges.append(
            annotate_edge(
                {
                    "kind": "repo_contains_file",
                    "src_kind": "repo",
                    "src": f"repo:{project}",
                    "dst_kind": "file",
                    "dst": f"file:{path}",
                    "confidence": "high",
                },
                provenance="static_analysis",
            )
        )
        if component:
            edges.append(
                annotate_edge(
                    {
                        "kind": "service_owns_file",
                        "src_kind": "service",
                        "src": f"service:{component.name}",
                        "dst_kind": "file",
                        "dst": f"file:{path}",
                        "confidence": "medium",
                    },
                    provenance="catalog",
                )
            )

    if component:
        for ref in component.verified_by:
            if ref.endswith(".py") or "/test" in ref:
                tests.append(ref)
                edges.append(
                    annotate_edge(
                        {
                            "kind": "file_tested_by_test",
                            "src_kind": "file",
                            "src": f"file:{ref}",
                            "dst_kind": "test",
                            "dst": f"test:{ref}",
                            "confidence": "high",
                        },
                        provenance="catalog",
                    )
                )

    # Also discover tests/ tree for coverage heuristics.
    tests_dir = repo_root / "tests"
    if tests_dir.is_dir():
        for path in tests_dir.rglob("test_*.py"):
            rel = path.relative_to(repo_root).as_posix()
            if rel not in tests:
                tests.append(rel)

    known_files = set(py_files)
    edges.extend(
        extract_adr_constrain_edges(project, adr_facts, known_files=known_files)
    )
    edges.extend(extract_test_covers_edges(project, files=py_files, tests=tests))
    edges.extend(extract_pipeline_edges(project, repo_root))
    edges.extend(extract_package_edges(project, repo_root))

    event_edges, event_warnings = extract_event_sdlc_edges(
        project,
        state_root=settings.agent_state_root,
        memory_db_path=settings.memory_db_path,
    )
    edges.extend(event_edges)
    warnings.extend(event_warnings)

    source_sha = _resolve_source_sha(repo_root)
    store.upsert_snapshot(
        project,
        files=py_files,
        services=services,
        tests=tests,
        adrs=adrs,
        edges=edges,
        source_sha=source_sha,
        extractor_version=EXTRACTOR_VERSION,
        files_indexed=len(py_files),
        files_skipped=0,
        languages_supported=",".join(LANGUAGES_SUPPORTED),
    )

    return {
        "project": project,
        "files": len(py_files),
        "services": len(services),
        "tests": len(tests),
        "adrs": len(adrs),
        "edges": len(edges),
        "edge_kinds": edge_kind_counts(edges),
        "provenance_counts": provenance_counts(edges),
        "source_sha": source_sha,
        "extractor_version": EXTRACTOR_VERSION,
        "languages_supported": list(LANGUAGES_SUPPORTED),
        "warnings": warnings,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }


def snapshot_project(
    project: str,
    settings: Settings | None = None,
    *,
    local_path: Path | None = None,
    store: GraphStore | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = store or GraphStore(settings.graph_db_path)
    store.init_schema()

    if local_path is not None:
        repo_root = local_path.resolve()
    else:
        cache = settings.graph_snapshot_cache / project.replace("/", "__")
        repo_root = _clone_or_update(project, cache, settings)

    return ingest_repo_path(project, repo_root, store, settings=settings)


def snapshot_all(
    settings: Settings | None = None,
    *,
    repo: str | None = None,
    local_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = GraphStore(settings.graph_db_path)
    store.init_schema()

    override = settings.graph_snapshot_repos_list()
    if repo:
        projects = [repo]
    elif override:
        projects = override
    else:
        projects = list(load_project_registry().keys())

    results: list[dict[str, Any]] = []
    for project in projects:
        local = (local_paths or {}).get(project)
        try:
            results.append(snapshot_project(project, settings=settings, local_path=local, store=store))
        except Exception as exc:
            results.append({"project": project, "error": str(exc), "status": "failed"})

    summary = store.summary()
    return {
        "summary": summary,
        "extractor_version": EXTRACTOR_VERSION,
        "projects": results,
    }
