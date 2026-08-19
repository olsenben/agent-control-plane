"""Exact-SHA Python symbol evidence provider (VExp W1-B).

``query`` rechecks ``HEAD == snapshot.target_sha`` and never mutates git.
Non-Python-only workspaces (or non-``.py`` query paths) return
``status=unsupported`` with ``diagnostics.reason=language_unsupported`` and
empty evidence. ``language_unsupported`` is never an EvidenceItem.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from agent_control.context.indexes.python_symbols import (
    PythonSymbolIndex,
    ReferenceHit,
    SymbolHit,
    iter_python_files,
)
from agent_shared.models.context_pack_v2 import EvidenceItem
from agent_shared.models.evidence_query import (
    EvidenceQuery,
    ProviderResult,
    compute_evidence_item_id,
)
from agent_shared.models.repo_snapshot import RepoSnapshot

_PROVIDER = "symbols"
_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
_KEYWORDS = frozenset(
    {
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "False",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "None",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "True",
        "try",
        "while",
        "with",
        "yield",
        "fix",
        "the",
        "a",
        "an",
    }
)


class SymbolEvidenceProvider:
    """RepositoryEvidenceProvider for Python declarations and references."""

    def query(self, snapshot: RepoSnapshot, request: EvidenceQuery) -> ProviderResult:
        mismatch = _head_mismatch(snapshot)
        if mismatch is not None:
            return ProviderResult(
                evidence=[],
                status="error",
                diagnostics={"reason": "sha_mismatch", "detail": mismatch},
            )

        root = Path(snapshot.workspace_path)
        py_files = iter_python_files(root)
        mentioned = [p.replace("\\", "/") for p in request.mentioned_paths]
        py_mentioned = [p for p in mentioned if p.endswith(".py")]
        non_py_mentioned = [p for p in mentioned if not p.endswith(".py")]

        if mentioned and not py_mentioned:
            return _unsupported(
                {
                    "reason": "language_unsupported",
                    "detail": {"paths": non_py_mentioned},
                }
            )
        if not py_files:
            return _unsupported(
                {
                    "reason": "language_unsupported",
                    "detail": {"lang": "non-python"},
                }
            )

        index = PythonSymbolIndex.build(
            root,
            snapshot.target_sha,
            index_generation=snapshot.index_generation,
        )
        names = _query_names(request)
        evidence: list[EvidenceItem] = []
        seen: set[str] = set()
        for name in names:
            for hit in index.find_symbol(name):
                decl = _declaration_item(snapshot, hit)
                if decl.id not in seen:
                    evidence.append(decl)
                    seen.add(decl.id)
                for ref in index.references_to(hit.symbol_id):
                    item = _reference_item(snapshot, hit, ref)
                    if item.id not in seen:
                        evidence.append(item)
                        seen.add(item.id)

        evidence.sort(key=lambda item: (item.source, item.text, item.id))
        diagnostics: dict[str, object] = {}
        if index.parser_backend == "regex":
            diagnostics["parser"] = "regex_fallback"
        return ProviderResult(evidence=evidence, status="ok", diagnostics=diagnostics)


def _unsupported(diagnostics: dict[str, object]) -> ProviderResult:
    return ProviderResult(evidence=[], status="unsupported", diagnostics=diagnostics)


def _head_mismatch(snapshot: RepoSnapshot) -> dict[str, str] | None:
    """Return mismatch detail when workspace HEAD is not ``target_sha``.

    Reads ``git rev-parse HEAD`` only. Never checkout, reset, or mutate.
    """
    requested = (snapshot.target_sha or "").strip()
    workspace = Path(snapshot.workspace_path)
    try:
        actual = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return {
            "requested": requested,
            "actual": "",
            "error": str(exc),
        }
    if actual != requested:
        return {"requested": requested, "actual": actual}
    return None


def _query_names(request: EvidenceQuery) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw in request.mentioned_symbols:
        name = raw.strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    for match in _IDENT_RE.finditer(request.query_text or ""):
        token = match.group(1)
        if token in _KEYWORDS or token in seen:
            continue
        names.append(token)
        seen.add(token)
    return names


def _declaration_item(snapshot: RepoSnapshot, hit: SymbolHit) -> EvidenceItem:
    fact = (
        f"{snapshot.target_sha}:{snapshot.index_generation}:"
        f"declaration:{hit.qualified_name}:{hit.start_line}:{hit.signature}"
    )
    text = f"{hit.path}:{hit.start_line} {hit.signature}"
    return EvidenceItem(
        text=text,
        source="symbol.declaration",
        provenance=["python_symbols", snapshot.target_sha],
        id=compute_evidence_item_id(
            snapshot.snapshot_id,
            _PROVIDER,
            "declaration",
            hit.path,
            fact,
        ),
    )


def _reference_item(snapshot: RepoSnapshot, hit: SymbolHit, ref: ReferenceHit) -> EvidenceItem:
    fact = (
        f"{snapshot.target_sha}:{snapshot.index_generation}:"
        f"reference:{hit.qualified_name}:{ref.path}:{ref.start_line}:{ref.snippet}"
    )
    text = f"{ref.path}:{ref.start_line} {ref.snippet}"
    return EvidenceItem(
        text=text,
        source="symbol.reference",
        provenance=["python_symbols", snapshot.target_sha],
        id=compute_evidence_item_id(
            snapshot.snapshot_id,
            _PROVIDER,
            "reference",
            ref.path,
            fact,
        ),
    )
