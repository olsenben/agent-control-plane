"""Extract Python import edges."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from agent_control.graph.provenance import annotate_edge

_STDLIB_MODULES = sys.stdlib_module_names

IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)", re.MULTILINE)

_PARSER = None
_PARSER_FAILED = False


def _get_parser():
    global _PARSER, _PARSER_FAILED
    if _PARSER_FAILED:
        return None
    if _PARSER is not None:
        return _PARSER
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser

        lang = Language(tspython.language())
        parser = Parser(lang)
        _PARSER = parser
        return parser
    except Exception:
        _PARSER_FAILED = True
        return None


def _walk_imports_tree_sitter(source: bytes) -> list[str]:
    parser = _get_parser()
    if parser is None:
        return []
    tree = parser.parse(source)
    names: list[str] = []

    def walk(node: object) -> None:
        ntype = getattr(node, "type", "")
        if ntype in ("import_statement", "import_from_statement"):
            text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
            match = IMPORT_RE.match(text)
            if match:
                names.append(match.group(1))
        for child in getattr(node, "children", []):
            walk(child)

    walk(tree.root_node)
    return names


def extract_imports(path: Path) -> list[str]:
    try:
        source = path.read_bytes()
    except OSError:
        return []
    names = _walk_imports_tree_sitter(source)
    if names:
        return names
    text = source.decode("utf-8", errors="replace")
    return list({m.group(1) for m in IMPORT_RE.finditer(text)})


def module_to_file_candidates(module: str, repo_root: Path) -> list[str]:
    """Map import module to possible repo-relative file paths."""
    parts = module.split(".")
    candidates: list[str] = []

    if parts[0] == "agent_control" or parts[0] == "agent_workers" or parts[0] == "agent_shared":
        rel = Path("src") / Path(*parts)
        candidates.append(str(rel.with_suffix(".py")).replace("\\", "/"))
        candidates.append(str((rel / "__init__.py")).replace("\\", "/"))

    rel = Path(*parts)
    candidates.append(str(rel.with_suffix(".py")).replace("\\", "/"))
    candidates.append(str((rel / "__init__.py")).replace("\\", "/"))
    return candidates


def extract_file_import_edges(
    project: str,
    repo_root: Path,
    *,
    python_paths: set[str] | None = None,
) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """Return (file_paths, edges, warnings)."""
    files: list[str] = []
    edges: list[dict[str, str]] = []
    warnings: list[str] = []
    if _get_parser() is None:
        warnings.append("tree-sitter unavailable; using regex import fallback")

    src = repo_root / "src"
    search_roots = [src] if src.is_dir() else [repo_root]
    py_files: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part.startswith(".") for part in path.parts):
                continue
            rel = path.relative_to(repo_root).as_posix()
            if python_paths is not None and rel not in python_paths:
                continue
            py_files.append(path)

    path_set = {p.relative_to(repo_root).as_posix() for p in py_files}
    for path in py_files:
        rel = path.relative_to(repo_root).as_posix()
        files.append(rel)
        for module in extract_imports(path):
            resolved = False
            for candidate in module_to_file_candidates(module, repo_root):
                if candidate in path_set:
                    edges.append(
                        annotate_edge(
                            {
                                "kind": "file_imports_file",
                                "src_kind": "file",
                                "src": f"file:{rel}",
                                "dst_kind": "file",
                                "dst": f"file:{candidate}",
                                "confidence": "medium",
                            },
                            provenance="static_analysis",
                        )
                    )
                    resolved = True
                    break
            if not resolved and "." in module:
                root = module.split(".", 1)[0]
                if root not in _STDLIB_MODULES:
                    warnings.append(f"unresolved import {module} in {rel}")

    return files, edges, warnings
