"""Lexical evidence provider (VExp W1-A).

Query-term normalization is frozen in this module. The Protocol signature is
``query(snapshot, request) -> ProviderResult``. Snippet truncation uses
``DEFAULT_SNIPPET_CHARS`` (optional keyword-only override); ``EvidenceBudget``
is not part of this seam.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from agent_control.context.providers import rg as ripgrep
from agent_shared.models.context_pack_v2 import EvidenceItem
from agent_shared.models.evidence_query import (
    EvidenceQuery,
    ProviderResult,
    compute_evidence_item_id,
)
from agent_shared.models.repo_snapshot import RepoSnapshot

PROVIDER_NAME = "lexical"
EVIDENCE_TYPE = "rg_hit"
EVIDENCE_SOURCE = "lexical.rg"

MAX_TERM_COUNT = 8
MIN_TERM_LEN = 2
DEFAULT_SNIPPET_CHARS = 240
MAX_EVIDENCE_ITEMS = 24
HEAD_TIMEOUT_SECONDS = 15.0

# Frozen stopword list. Quoted spans, mentioned_paths, and mentioned_symbols
# bypass this filter. Identifiers such as foo/bar (length >= MIN_TERM_LEN)
# are kept. Do not treat diagnostics as evidence.
STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "not",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "it",
        "this",
        "that",
        "these",
        "those",
        "if",
        "then",
        "else",
        "when",
        "while",
        "where",
        "which",
        "who",
        "what",
        "how",
        "why",
        "do",
        "does",
        "did",
        "can",
        "could",
        "should",
        "would",
        "will",
        "has",
        "have",
        "had",
        "but",
        "so",
        "than",
        "too",
        "very",
        "just",
        "also",
        "into",
        "over",
        "after",
        "before",
        "between",
        "because",
        "about",
        "up",
        "out",
        "no",
        "yes",
        "we",
        "you",
        "they",
        "he",
        "she",
        "i",
        "me",
        "my",
        "our",
        "your",
        "please",
        "need",
        "needs",
        "using",
        "used",
        "use",
    }
)

_QUOTED = re.compile(r"(?P<q>['\"])(?P<body>.*?)(?P=q)")
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class LexicalEvidenceProvider:
    """Exact-SHA lexical search over ``snapshot.workspace_path`` via rg."""

    def query(
        self,
        snapshot: RepoSnapshot,
        request: EvidenceQuery,
        *,
        snippet_chars: int = DEFAULT_SNIPPET_CHARS,
    ) -> ProviderResult:
        actual = _read_head_sha(Path(snapshot.workspace_path))
        if actual != snapshot.target_sha:
            return ProviderResult(
                evidence=[],
                status="error",
                diagnostics={
                    "reason": "sha_mismatch",
                    "expected_sha": snapshot.target_sha,
                    "actual_sha": actual,
                },
            )
        if not ripgrep.ripgrep_available():
            return ProviderResult(
                evidence=[],
                status="unavailable",
                diagnostics={"reason": "rg_unavailable"},
            )
        terms = normalize_query_terms(request)
        cap = snippet_chars if snippet_chars >= 0 else DEFAULT_SNIPPET_CHARS
        if not terms:
            return ProviderResult(
                evidence=[],
                status="ok",
                diagnostics={"terms": [], "snippet_chars": cap, "hit_count": 0},
            )
        try:
            matches = ripgrep.search_workspace(Path(snapshot.workspace_path), terms)
        except ripgrep.RipgrepError as exc:
            return ProviderResult(
                evidence=[],
                status="error",
                diagnostics={"reason": "rg_error", "detail": str(exc)},
            )
        ordered = _sorted_unique_matches(matches)[:MAX_EVIDENCE_ITEMS]
        evidence = [_to_item(snapshot.snapshot_id, match, cap) for match in ordered]
        return ProviderResult(
            evidence=evidence,
            status="ok",
            diagnostics={
                "terms": list(terms),
                "snippet_chars": cap,
                "hit_count": len(evidence),
            },
        )


def normalize_query_terms(request: EvidenceQuery) -> tuple[str, ...]:
    """Frozen query normalization. Uses query_text and failure_signature only."""
    seen: set[str] = set()
    terms: list[str] = []

    def add(term: str, *, preserve: bool) -> None:
        if len(terms) >= MAX_TERM_COUNT:
            return
        cleaned = term.strip()
        if not cleaned:
            return
        if preserve:
            cleaned = cleaned.replace("\\", "/")
            key = cleaned.casefold()
        else:
            if len(cleaned) < MIN_TERM_LEN:
                return
            cleaned = cleaned.casefold()
            if cleaned in STOPWORDS:
                return
            key = cleaned
        if key in seen:
            return
        seen.add(key)
        terms.append(cleaned)

    for path in request.mentioned_paths:
        add(path, preserve=True)
    for symbol in request.mentioned_symbols:
        add(symbol, preserve=True)

    for blob in (request.query_text, request.failure_signature):
        quoted, remainder = _extract_quoted(blob)
        for span in quoted:
            add(span, preserve=True)
        for token in _TOKEN.findall(remainder):
            add(token, preserve=False)

    return tuple(terms)


def _extract_quoted(text: str) -> tuple[list[str], str]:
    quoted: list[str] = []
    parts: list[str] = []
    cursor = 0
    for match in _QUOTED.finditer(text):
        parts.append(text[cursor : match.start()])
        quoted.append(match.group("body"))
        cursor = match.end()
    parts.append(text[cursor:])
    return quoted, " ".join(parts)


def _read_head_sha(workspace: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=HEAD_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _sorted_unique_matches(matches: list[ripgrep.RipgrepMatch]) -> list[ripgrep.RipgrepMatch]:
    unique: dict[tuple[str, int], ripgrep.RipgrepMatch] = {}
    for match in matches:
        key = (match.path, match.line_number)
        previous = unique.get(key)
        if previous is None or match.line_text < previous.line_text:
            unique[key] = match
    return sorted(unique.values(), key=lambda item: (item.path, item.line_number, item.line_text))


def _to_item(snapshot_id: str, match: ripgrep.RipgrepMatch, snippet_chars: int) -> EvidenceItem:
    fact_line = match.line_text.strip()
    text = _truncate(fact_line, snippet_chars)
    item_id = compute_evidence_item_id(
        snapshot_id,
        PROVIDER_NAME,
        EVIDENCE_TYPE,
        match.path,
        f"{match.line_number}:{fact_line}",
    )
    return EvidenceItem(
        text=text,
        source=EVIDENCE_SOURCE,
        provenance=[f"{match.path}:{match.line_number}"],
        id=item_id,
    )


def _truncate(text: str, cap: int) -> str:
    if cap <= 0:
        return ""
    if len(text) <= cap:
        return text
    return text[:cap]
