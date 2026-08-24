"""State witness typed failures."""

from __future__ import annotations

import pytest

from agent_control.transaction.witness import StateWitnessError, check_state_witness

BASE = {
    "source_sha": "abc1234",
    "patch_digest": "a" * 64,
    "policy_digest": "b" * 64,
    "evidence_bundle_digest": "c" * 64,
    "allowed_target_branch": "agent/admitted",
    "repo": "org/repo",
}


def test_source_drift() -> None:
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(expected=BASE, observed={**BASE, "source_sha": "ffff000"})
    assert exc.value.code == "SOURCE_DRIFT"


def test_patch_drift() -> None:
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(expected=BASE, observed={**BASE, "patch_digest": "d" * 64})
    assert exc.value.code == "PATCH_DRIFT"


def test_policy_drift() -> None:
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(expected=BASE, observed={**BASE, "policy_digest": "e" * 64})
    assert exc.value.code == "POLICY_DRIFT"


def test_evidence_stale() -> None:
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(
            expected=BASE, observed={**BASE, "evidence_bundle_digest": "f" * 64}
        )
    assert exc.value.code == "EVIDENCE_STALE"
    with pytest.raises(StateWitnessError) as exc2:
        check_state_witness(expected=BASE, observed={**BASE, "evidence_stale": True})
    assert exc2.value.code == "EVIDENCE_STALE"


def test_capability_replay() -> None:
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(expected=BASE, observed=BASE, consumed=True)
    assert exc.value.code == "CAPABILITY_REPLAY"


def test_target_mismatch_branch_and_repo() -> None:
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(
            expected=BASE, observed={**BASE, "allowed_target_branch": "main"}
        )
    assert exc.value.code == "TARGET_MISMATCH"
    with pytest.raises(StateWitnessError) as exc2:
        check_state_witness(expected=BASE, observed={**BASE, "repo": "other/repo"})
    assert exc2.value.code == "TARGET_MISMATCH"


def test_matching_state_passes() -> None:
    check_state_witness(expected=BASE, observed=dict(BASE))
