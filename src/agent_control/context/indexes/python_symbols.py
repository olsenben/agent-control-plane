"""Parser-neutral Python symbol index (VExp W1-B).

Public facade: ``find_symbol``, ``symbols_in_file``, ``references_to``,
``symbol_signature``. Tree-sitter is preferred; regex is the fallback when the
parser cannot be constructed. Index identity includes ``target_sha``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_DIR_PARTS = frozenset({".git", ".hg", ".venv", "venv", "__pycache__", "node_modules"})

_FUNC_RE = re.compile(
    r"^([ \t]*)(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([^:]+))?\s*:",
    re.MULTILINE,
)
_CLASS_RE = re.compile(
    r"^([ \t]*)class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:",
    re.MULTILINE,
)
_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
_DEF_NAME_RE = re.compile(r"^(?:async\s+)?(?:def|class)\s+(\w+)\b")

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


@dataclass(frozen=True)
class SymbolHit:
    """One declaration in the exact-SHA Python index."""

    symbol_id: str
    name: str
    qualified_name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    signature: str
    enclosing_id: str | None = None


@dataclass(frozen=True)
class ReferenceHit:
    """One non-declaration use of a symbol."""

    symbol_id: str
    path: str
    start_line: int
    snippet: str
    kind: str = "reference"


@dataclass
class PythonSymbolIndex:
    """In-memory Python symbol index bound to a workspace SHA."""

    workspace: Path
    target_sha: str
    index_generation: str = "0"
    parser_backend: str = "tree-sitter"
    _symbols: list[SymbolHit] = field(default_factory=list)
    _by_id: dict[str, SymbolHit] = field(default_factory=dict)
    _by_path: dict[str, list[SymbolHit]] = field(default_factory=dict)
    _by_name: dict[str, list[SymbolHit]] = field(default_factory=dict)
    _refs: dict[str, list[ReferenceHit]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        workspace: str | Path,
        target_sha: str,
        *,
        index_generation: str = "0",
    ) -> PythonSymbolIndex:
        root = Path(workspace)
        backend = "tree-sitter" if _get_parser() is not None else "regex"
        index = cls(
            workspace=root,
            target_sha=target_sha,
            index_generation=index_generation,
            parser_backend=backend,
        )
        declarations: list[SymbolHit] = []
        file_bytes: list[tuple[str, bytes, str]] = []
        for path in _iter_python_files(root):
            rel = path.relative_to(root).as_posix()
            try:
                source = path.read_bytes()
            except OSError:
                continue
            text = source.decode("utf-8", errors="replace")
            file_bytes.append((rel, source, text))
            if backend == "tree-sitter":
                declarations.extend(_tree_sitter_declarations(source, rel, target_sha))
            else:
                declarations.extend(_regex_declarations(text, rel, target_sha))
        _install_declarations(index, declarations)
        names = {hit.name for hit in declarations}
        for rel, source, text in file_bytes:
            if backend == "tree-sitter":
                raw_refs = _tree_sitter_references(source, rel, names)
            else:
                raw_refs = _regex_references(text, rel, names)
            _bind_references(index, raw_refs)
        return index

    def find_symbol(self, name_or_query: str) -> list[SymbolHit]:
        query = (name_or_query or "").strip()
        if not query:
            return []
        hits: list[SymbolHit] = []
        seen: set[str] = set()
        for hit in self._symbols:
            if hit.name == query or hit.qualified_name == query or hit.symbol_id == query:
                if hit.symbol_id not in seen:
                    hits.append(hit)
                    seen.add(hit.symbol_id)
        return hits

    def symbols_in_file(self, path: str) -> list[SymbolHit]:
        rel = _normalize_repo_path(self.workspace, path)
        return list(self._by_path.get(rel, ()))

    def references_to(self, symbol_id: str) -> list[ReferenceHit]:
        return list(self._refs.get(symbol_id, ()))

    def symbol_signature(self, symbol_id: str) -> str | None:
        hit = self._by_id.get(symbol_id)
        if hit is None:
            return None
        return hit.signature


def find_symbol(index: PythonSymbolIndex, name_or_query: str) -> list[SymbolHit]:
    """Parser-neutral facade: locate declarations by name, qualified name, or id."""
    return index.find_symbol(name_or_query)


def symbols_in_file(index: PythonSymbolIndex, path: str) -> list[SymbolHit]:
    """Parser-neutral facade: declarations in a repo-relative file."""
    return index.symbols_in_file(path)


def references_to(index: PythonSymbolIndex, symbol_id: str) -> list[ReferenceHit]:
    """Parser-neutral facade: non-declaration uses of a symbol id."""
    return index.references_to(symbol_id)


def symbol_signature(index: PythonSymbolIndex, symbol_id: str) -> str | None:
    """Parser-neutral facade: source signature string for a symbol id."""
    return index.symbol_signature(symbol_id)


def iter_python_files(workspace: str | Path) -> list[str]:
    """Repo-relative POSIX paths of indexable ``.py`` files."""
    root = Path(workspace)
    return [p.relative_to(root).as_posix() for p in _iter_python_files(root)]


def _install_declarations(index: PythonSymbolIndex, declarations: list[SymbolHit]) -> None:
    index._symbols = sorted(declarations, key=lambda h: (h.path, h.start_line, h.symbol_id))
    index._by_id = {hit.symbol_id: hit for hit in index._symbols}
    by_path: dict[str, list[SymbolHit]] = {}
    by_name: dict[str, list[SymbolHit]] = {}
    for hit in index._symbols:
        by_path.setdefault(hit.path, []).append(hit)
        by_name.setdefault(hit.name, []).append(hit)
        if hit.qualified_name != hit.name:
            by_name.setdefault(hit.qualified_name, []).append(hit)
    index._by_path = by_path
    index._by_name = by_name
    index._refs = {hit.symbol_id: [] for hit in index._symbols}


def _bind_references(
    index: PythonSymbolIndex,
    raw_refs: list[tuple[str, str, int, str, str]],
) -> None:
    """raw_refs items: (path, name, start_line, snippet, kind)."""
    seen: set[tuple[str, str, int, str]] = set()
    for path, name, start_line, snippet, kind in raw_refs:
        for hit in index._by_name.get(name, ()):
            if hit.name != name:
                continue
            dedup = (hit.symbol_id, path, start_line, snippet)
            if dedup in seen:
                continue
            seen.add(dedup)
            index._refs.setdefault(hit.symbol_id, []).append(
                ReferenceHit(
                    symbol_id=hit.symbol_id,
                    path=path,
                    start_line=start_line,
                    snippet=snippet,
                    kind=kind,
                )
            )
    for symbol_id, refs in index._refs.items():
        index._refs[symbol_id] = sorted(refs, key=lambda r: (r.path, r.start_line, r.kind))


def _iter_python_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in root.rglob("*.py"):
        rel_parts = path.relative_to(root).parts
        if any(part in _SKIP_DIR_PARTS or part.startswith(".") for part in rel_parts):
            continue
        files.append(path)
    return sorted(files)


def _normalize_repo_path(workspace: Path, path: str) -> str:
    raw = path.replace("\\", "/")
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(workspace.resolve()).as_posix()
        except ValueError:
            return candidate.as_posix()
    return Path(raw).as_posix()


def _make_symbol_id(target_sha: str, path: str, qualified_name: str, start_line: int) -> str:
    return f"{target_sha}:{path}:{qualified_name}:{start_line}"


def _first_line_signature(text: str) -> str:
    line = text.splitlines()[0] if text else ""
    return line.rstrip().rstrip(":")


def _tree_sitter_declarations(source: bytes, rel: str, target_sha: str) -> list[SymbolHit]:
    parser = _get_parser()
    if parser is None:
        return []
    tree = parser.parse(source)
    hits: list[SymbolHit] = []

    def walk(node: object, enclosing: list[SymbolHit]) -> None:
        ntype = getattr(node, "type", "")
        if ntype in ("function_definition", "class_definition"):
            name_node = _child_by_field(node, "name")
            if name_node is None:
                for child in getattr(node, "children", []):
                    walk(child, enclosing)
                return
            name = _node_text(source, name_node)
            kind = "class" if ntype == "class_definition" else "function"
            start_line = int(getattr(node, "start_point", (0, 0))[0]) + 1
            end_line = int(getattr(node, "end_point", (0, 0))[0]) + 1
            qualified = ".".join([e.name for e in enclosing] + [name])
            enclosing_id = enclosing[-1].symbol_id if enclosing else None
            signature = _first_line_signature(_node_text(source, node))
            hit = SymbolHit(
                symbol_id=_make_symbol_id(target_sha, rel, qualified, start_line),
                name=name,
                qualified_name=qualified,
                kind=kind,
                path=rel,
                start_line=start_line,
                end_line=end_line,
                signature=signature,
                enclosing_id=enclosing_id,
            )
            hits.append(hit)
            nested = enclosing + [hit]
            for child in getattr(node, "children", []):
                walk(child, nested)
            return
        for child in getattr(node, "children", []):
            walk(child, enclosing)

    walk(tree.root_node, [])
    return hits


def _tree_sitter_references(
    source: bytes, rel: str, names: set[str]
) -> list[tuple[str, str, int, str, str]]:
    """Return (path, name, start_line, snippet, kind)."""
    parser = _get_parser()
    if parser is None or not names:
        return []
    tree = parser.parse(source)
    text = source.decode("utf-8", errors="replace")
    lines = text.splitlines()
    decl_spans: set[tuple[int, int]] = set()
    results: list[tuple[str, str, int, str, str]] = []

    def mark_decl_names(node: object) -> None:
        ntype = getattr(node, "type", "")
        if ntype in ("function_definition", "class_definition"):
            name_node = _child_by_field(node, "name")
            if name_node is not None:
                decl_spans.add(
                    (int(getattr(name_node, "start_byte", 0)), int(getattr(name_node, "end_byte", 0)))
                )
        for child in getattr(node, "children", []):
            mark_decl_names(child)

    def walk(node: object, parent: object | None) -> None:
        ntype = getattr(node, "type", "")
        if ntype == "identifier":
            start_byte = int(getattr(node, "start_byte", 0))
            end_byte = int(getattr(node, "end_byte", 0))
            if (start_byte, end_byte) in decl_spans:
                return
            name = _node_text(source, node)
            if name not in names:
                return
            start_line = int(getattr(node, "start_point", (0, 0))[0]) + 1
            snippet = lines[start_line - 1] if 0 < start_line <= len(lines) else name
            kind = "call" if _is_call_function(parent, node) else "reference"
            results.append((rel, name, start_line, snippet.strip(), kind))
            return
        for child in getattr(node, "children", []):
            walk(child, node)

    mark_decl_names(tree.root_node)
    walk(tree.root_node, None)
    return results


def _regex_declarations(text: str, rel: str, target_sha: str) -> list[SymbolHit]:
    hits: list[SymbolHit] = []
    stack: list[tuple[int, SymbolHit]] = []
    events: list[tuple[int, str, re.Match[str]]] = []
    for match in _CLASS_RE.finditer(text):
        events.append((match.start(), "class", match))
    for match in _FUNC_RE.finditer(text):
        events.append((match.start(), "function", match))
    events.sort(key=lambda item: item[0])
    for _pos, kind, match in events:
        indent = len(match.group(1).replace("\t", "    "))
        name = match.group(2)
        start_line = text[: match.start()].count("\n") + 1
        while stack and stack[-1][0] >= indent:
            stack.pop()
        enclosing = [item[1] for item in stack]
        qualified = ".".join([e.name for e in enclosing] + [name])
        enclosing_id = enclosing[-1].symbol_id if enclosing else None
        signature = _first_line_signature(match.group(0))
        hit = SymbolHit(
            symbol_id=_make_symbol_id(target_sha, rel, qualified, start_line),
            name=name,
            qualified_name=qualified,
            kind=kind,
            path=rel,
            start_line=start_line,
            end_line=start_line,
            signature=signature,
            enclosing_id=enclosing_id,
        )
        hits.append(hit)
        stack.append((indent, hit))
    return hits


def _regex_references(
    text: str, rel: str, names: set[str]
) -> list[tuple[str, str, int, str, str]]:
    if not names:
        return []
    results: list[tuple[str, str, int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        def_match = _DEF_NAME_RE.match(stripped)
        skip_name = def_match.group(1) if def_match else None
        for match in _IDENT_RE.finditer(line):
            name = match.group(1)
            if name not in names:
                continue
            if name == skip_name:
                continue
            kind = "call" if re.search(rf"\b{re.escape(name)}\s*\(", line) else "reference"
            results.append((rel, name, line_no, line.strip(), kind))
    return results


def _child_by_field(node: object, field: str) -> object | None:
    getter = getattr(node, "child_by_field_name", None)
    if callable(getter):
        found = getter(field)
        if found is not None:
            return found
    return None


def _node_text(source: bytes, node: object) -> str:
    start = int(getattr(node, "start_byte", 0))
    end = int(getattr(node, "end_byte", 0))
    return source[start:end].decode("utf-8", errors="replace")


def _is_call_function(parent: object | None, node: object) -> bool:
    if parent is None or getattr(parent, "type", "") != "call":
        return False
    fn = _child_by_field(parent, "function")
    if fn is None:
        return False
    return getattr(fn, "start_byte", None) == getattr(node, "start_byte", None) and getattr(
        fn, "end_byte", None
    ) == getattr(node, "end_byte", None)
