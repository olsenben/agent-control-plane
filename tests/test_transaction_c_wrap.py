"""Frozen C wrap pin and decide_c WRAP tests."""

from __future__ import annotations

from pathlib import Path

from agent_control.transaction.admission import AUTO_ADMIT, ESCALATE, wrap_decide_c
from agent_control.transaction.admission.pin import FROZEN_C_HASH, verify_frozen_c_pin
from agent_shared.models.transaction.admission import PolicyFields

PIN = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"


def _policy(digest: str = "a" * 64) -> PolicyFields:
    return PolicyFields(
        policy_id="w5_evidence_policy.v1",
        policy_version="v1",
        policy_digest=digest,
        admission_implementation_digest=PIN,
    )


def _unit() -> dict:
    return {
        "path": "src/pkg/core.py",
        "element_key": "func:foo",
        "symbol": "foo",
        "change_kind": "changed",
        "receipts": ["TASK_NAMED", "FAILURE_DIRECT"],
        "visibility": "private",
        "privileged": False,
        "local_creation": False,
        "callers": [],
        "side_effect_category": "NONE",
    }


def test_frozen_c_hash_pin() -> None:
    result = verify_frozen_c_pin()
    assert result["expected"] == PIN
    assert result["actual"] == PIN
    assert result["hash_ok"] is True
    assert result["ast_ok"] is True
    assert result["mismatches"] == []
    assert FROZEN_C_HASH == PIN
    assert "sha256(vexp_w4_exp22.py bytes)" in result["method"]


def test_frozen_c_source_file_exists() -> None:
    frozen = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agent_control"
        / "transaction"
        / "admission"
        / "frozen_c.py"
    )
    assert frozen.is_file()
    text = frozen.read_text(encoding="utf-8")
    assert "def decide_c(" in text
    assert "def admit_proposal(" in text
    assert "def classify_units(" in text


def test_wrap_decide_c_auto_admit() -> None:
    unit = _unit()
    decision = wrap_decide_c(
        units=[unit],
        changed_paths=["src/pkg/core.py"],
        decision={"writable_resources": [{"path": unit["path"], "element_key": unit["element_key"]}]},
        g0=[],
        verification={"passed": True, "incomplete": False},
        policy=_policy(),
        proposal_id="p1",
        patch_digest="b" * 64,
        tenant_id="t",
        org_id="o",
        repository="org/repo",
    )
    assert decision.decision == AUTO_ADMIT
    assert decision.policy_id == "w5_evidence_policy.v1"
    assert decision.policy_digest == "a" * 64
    assert decision.admission_implementation_digest == PIN
    assert decision.arm == "TRANSACTIONAL_RELATIONAL_ADMISSION"


def test_wrap_decide_c_required_provider_fail_no_auto_admit() -> None:
    unit = _unit()
    decision = wrap_decide_c(
        units=[unit],
        changed_paths=["src/pkg/core.py"],
        decision={"writable_resources": [{"path": unit["path"], "element_key": unit["element_key"]}]},
        g0=[],
        verification={"passed": True, "incomplete": False},
        policy=_policy(),
        proposal_id="p1",
        patch_digest="b" * 64,
        required_provider_failed=True,
    )
    assert decision.decision != AUTO_ADMIT
    assert decision.decision == ESCALATE
    assert decision.verification.get("incomplete") is True
    assert decision.verification.get("passed") is False
