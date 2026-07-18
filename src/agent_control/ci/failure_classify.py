"""Classify CI failure for repair budget decisions (Slice 6F.2)."""

from __future__ import annotations

import re

from agent_shared.models.ci import FailureClass

_TEST = re.compile(r"(?i)(pytest|unittest|FAIL:|AssertionError|tests? failed|test session)")
# Require failure-ish context so a green "ruff check ." step in the same log does not win.
_LINT = re.compile(
    r"(?i)((ruff|flake8|eslint|pylint).{0,80}(error|failed|fail\b)|lint error|would reformat)"
)
_TYPE = re.compile(r"(?i)(typecheck|tsc\b|pyright|mypy:)")
_BUILD = re.compile(r"(?i)(build failed|compilation failed|cargo build|npm run build|webpack)")
_CHECKOUT = re.compile(r"(?i)(checkout failed|fatal: repository|could not read from remote)")
_RUNNER = re.compile(r"(?i)(runner.*(unavailable|offline)|no runners? available)")
_REGISTRY = re.compile(r"(?i)(registry.*(timeout|unavailable)|pip.*(connection|timeout)|npm ERR! network)")
_INFRA = re.compile(r"(?i)(internal server error|service unavailable|502|503|504)")
_TIMEOUT = re.compile(r"(?i)(timed?\s*out|timeout)")
_CANCEL = re.compile(r"(?i)(cancelled|canceled|superseded)")


def classify_failure(
    retained_log_text: str,
    *,
    observation_conclusion: str | None = None,
) -> FailureClass:
    """Heuristic classifier; timeouts → unknown (not auto-repairable)."""
    conclusion = (observation_conclusion or "").lower()
    if conclusion in ("cancelled", "canceled"):
        return "cancelled_or_superseded"
    text = retained_log_text or ""
    if _CANCEL.search(text):
        return "cancelled_or_superseded"
    if _TIMEOUT.search(text) or conclusion in ("timed_out", "timeout"):
        return "unknown"
    if _RUNNER.search(text):
        return "runner_unavailable"
    if _CHECKOUT.search(text):
        return "checkout_failure"
    if _REGISTRY.search(text):
        return "dependency_registry_unavailable"
    if _INFRA.search(text):
        return "infrastructure_failure"
    # Prefer test signals before lint: CI often runs ruff then pytest in one job log.
    if _TEST.search(text):
        return "test_failure"
    if _TYPE.search(text):
        return "deterministic_typecheck_failure"
    if _LINT.search(text):
        return "lint_failure"
    if _BUILD.search(text):
        return "build_failure"
    if conclusion == "failure":
        return "unknown"
    return "unknown"
