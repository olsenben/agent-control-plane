"""Package dependency edges from pyproject.toml / package.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

from agent_control.graph.provenance import annotate_edge

_DEP_NAME_RE = re.compile(r"^([A-Za-z0-9_.-]+)")


def _dep_name(raw: str) -> str | None:
    text = raw.strip().strip("\"'")
    if not text or text.startswith("{"):
        return None
    # PEP 508 extras / markers: strip after ;
    text = text.split(";", 1)[0].strip()
    match = _DEP_NAME_RE.match(text)
    if not match:
        return None
    return match.group(1).lower().replace("_", "-")


def extract_package_edges(project: str, repo_root: Path) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    edges.extend(_from_pyproject(project, repo_root / "pyproject.toml"))
    edges.extend(_from_package_json(project, repo_root / "package.json"))
    return edges


def _from_pyproject(project: str, path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover — py<3.11
        try:
            import tomli as tomllib  # type: ignore
        except ModuleNotFoundError:
            return []

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    project_table = data.get("project") or {}
    pkg_name = str(project_table.get("name") or project.split("/")[-1]).lower()
    deps: list[str] = list(project_table.get("dependencies") or [])
    optional = project_table.get("optional-dependencies") or {}
    for group in optional.values():
        deps.extend(group or [])

    # Poetry fallback
    poetry = (data.get("tool") or {}).get("poetry") or {}
    if poetry.get("name"):
        pkg_name = str(poetry["name"]).lower()
    poetry_deps = poetry.get("dependencies") or {}
    for name, _spec in poetry_deps.items():
        if str(name).lower() == "python":
            continue
        deps.append(str(name))

    edges: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in deps:
        name = _dep_name(raw) if isinstance(raw, str) else _dep_name(str(raw))
        if not name or name in seen or name == pkg_name:
            continue
        seen.add(name)
        edges.append(
            annotate_edge(
                {
                    "kind": "package_depends_on_package",
                    "src_kind": "package",
                    "src": f"package:{pkg_name}",
                    "dst_kind": "package",
                    "dst": f"package:{name}",
                    "confidence": "high",
                },
                provenance="static_analysis",
            )
        )
    return edges


def _from_package_json(project: str, path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    pkg_name = str(data.get("name") or project.split("/")[-1]).lower()
    edges: list[dict[str, str]] = []
    seen: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for name in (data.get(section) or {}):
            dep = str(name).lower()
            if not dep or dep in seen:
                continue
            seen.add(dep)
            edges.append(
                annotate_edge(
                    {
                        "kind": "package_depends_on_package",
                        "src_kind": "package",
                        "src": f"package:{pkg_name}",
                        "dst_kind": "package",
                        "dst": f"package:{dep}",
                        "confidence": "high",
                    },
                    provenance="static_analysis",
                )
            )
    return edges
