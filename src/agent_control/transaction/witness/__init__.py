"""State witness typed failures. No publish on mismatch."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

WitnessCode = Literal[
    "SOURCE_DRIFT",
    "PATCH_DRIFT",
    "POLICY_DRIFT",
    "EVIDENCE_STALE",
    "CAPABILITY_REPLAY",
    "TARGET_MISMATCH",
    "OTHER_TYPED",
]


class StateWitnessError(RuntimeError):
    def __init__(self, code: WitnessCode, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def check_state_witness(
    *,
    expected: Mapping[str, object],
    observed: Mapping[str, object],
    consumed: bool = False,
) -> None:
    """Fail closed on any identity mismatch. Order is stable for tests."""
    if consumed or observed.get("consumed") is True:
        raise StateWitnessError("CAPABILITY_REPLAY")
    if str(observed.get("source_sha") or "") != str(expected.get("source_sha") or ""):
        raise StateWitnessError("SOURCE_DRIFT")
    if str(observed.get("patch_digest") or "") != str(expected.get("patch_digest") or ""):
        raise StateWitnessError("PATCH_DRIFT")
    if str(observed.get("policy_digest") or "") != str(expected.get("policy_digest") or ""):
        raise StateWitnessError("POLICY_DRIFT")
    expected_bundle = expected.get("evidence_bundle_digest")
    observed_bundle = observed.get("evidence_bundle_digest")
    if expected_bundle and str(observed_bundle or "") != str(expected_bundle):
        raise StateWitnessError("EVIDENCE_STALE")
    if observed.get("evidence_stale") is True:
        raise StateWitnessError("EVIDENCE_STALE")
    expected_target = expected.get("allowed_target_branch") or expected.get("target_ref")
    observed_target = observed.get("allowed_target_branch") or observed.get("target_ref")
    if expected_target and str(observed_target or "") != str(expected_target):
        raise StateWitnessError("TARGET_MISMATCH")
    expected_repo = expected.get("repo") or expected.get("repository")
    observed_repo = observed.get("repo") or observed.get("repository")
    if expected_repo and str(observed_repo or "") != str(expected_repo):
        raise StateWitnessError("TARGET_MISMATCH")
