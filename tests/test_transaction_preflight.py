"""PDP preflight READY vs INCOMPLETE and G0 fail-closed wiring."""

from __future__ import annotations

from pathlib import Path

from agent_control.transaction.admission import (
    AUTO_ADMIT,
    FROZEN_C_HASH,
    HARNESS_SPECIFIC_CONTROL_LOGIC,
    REJECT,
    g0_violations,
    wrap_decide_c,
)
from agent_control.transaction.policy_bundle import (
    G0_LOAD_FAILED,
    G0_PRESENT_EXPLICIT_EMPTY,
    G0_PRESENT_NONEMPTY,
    G0_SCHEMA_INVALID,
    G0_UNBOUND,
    bind_g0_input,
    create_policy_bundle_receipt,
)
from agent_control.transaction.preflight import (
    DETERMINISTIC_PREFLIGHT_REVISIT,
    PDP_INPUT_INCOMPLETE,
    POLICY_UNAVAILABLE,
    PREFLIGHT_INCOMPLETE,
    PREFLIGHT_READY,
    evaluate_transaction_preflight,
)
from agent_shared.models.transaction.admission import PolicyFields

PIN = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"


def _policy() -> PolicyFields:
    return PolicyFields(
        policy_id="w5_evidence_policy.v1",
        policy_version="v1",
        policy_digest="a" * 64,
        admission_implementation_digest=PIN,
    )


def _verify() -> dict[str, bool]:
    return {"passed": True, "incomplete": False}


def _units(path: str = "src/pkg/core.py") -> list[dict[str, object]]:
    return [
        {
            "path": path,
            "element_key": f"file:{path}",
            "symbol": "foo",
            "change_kind": "changed",
            "receipts": ["TASK_NAMED"],
            "visibility": "private",
            "privileged": False,
            "local_creation": False,
            "callers": [],
            "side_effect_category": "NONE",
        }
    ]


def test_frozen_c_hash_unchanged() -> None:
    assert FROZEN_C_HASH == PIN
    assert HARNESS_SPECIFIC_CONTROL_LOGIC == "NO"
    assert DETERMINISTIC_PREFLIGHT_REVISIT == "YES"


def test_preflight_ready_when_inputs_and_g0_bound() -> None:
    g0 = bind_g0_input(["src/pkg/core.py"])
    receipt = create_policy_bundle_receipt(policy=_policy(), g0=g0, c_load_mode="vendored")
    result = evaluate_transaction_preflight(
        changed_paths=["src/pkg/core.py"],
        units=_units(),
        verification=_verify(),
        policy=_policy(),
        g0=g0,
        proposal_id="p1",
        patch_digest="b" * 64,
        policy_bundle_digest=receipt.bundle_digest,
    )
    assert result.status == PREFLIGHT_READY
    assert result.incomplete_reason is None
    assert result.missing_inputs == []
    assert result.g0_input_state == G0_PRESENT_NONEMPTY
    assert result.policy_bundle_digest == receipt.bundle_digest
    assert g0.violations == ()


def test_preflight_incomplete_when_required_input_missing() -> None:
    g0 = bind_g0_input(["src/pkg/core.py"])
    result = evaluate_transaction_preflight(
        changed_paths=["src/pkg/core.py"],
        units=_units(),
        verification=None,
        policy=_policy(),
        g0=g0,
        proposal_id="p1",
        patch_digest="b" * 64,
    )
    assert result.status == PREFLIGHT_INCOMPLETE
    assert result.incomplete_reason == PDP_INPUT_INCOMPLETE
    assert "verification" in result.missing_inputs


def test_g0_unbound_is_not_explicit_empty() -> None:
    g0 = bind_g0_input(["src/pkg/core.py"], bound=False)
    assert g0.state == G0_UNBOUND
    assert g0.state != G0_PRESENT_EXPLICIT_EMPTY
    assert g0.fail_closed is True
    result = evaluate_transaction_preflight(
        changed_paths=["src/pkg/core.py"],
        units=_units(),
        verification=_verify(),
        policy=_policy(),
        g0=g0,
        proposal_id="p1",
        patch_digest="b" * 64,
    )
    assert result.status == PREFLIGHT_INCOMPLETE
    assert result.incomplete_reason == PDP_INPUT_INCOMPLETE


def test_g0_load_failed_is_policy_unavailable() -> None:
    def _boom() -> None:
        raise RuntimeError("missing policy module")

    g0 = bind_g0_input(["src/pkg/core.py"], loader=_boom)
    assert g0.state == G0_LOAD_FAILED
    assert g0.state != G0_PRESENT_EXPLICIT_EMPTY
    result = evaluate_transaction_preflight(
        changed_paths=["src/pkg/core.py"],
        units=_units(),
        verification=_verify(),
        policy=_policy(),
        g0=g0,
        proposal_id="p1",
        patch_digest="b" * 64,
    )
    assert result.status == PREFLIGHT_INCOMPLETE
    assert result.incomplete_reason == POLICY_UNAVAILABLE


def test_g0_schema_invalid_wrong_digest() -> None:
    g0 = bind_g0_input(["src/pkg/core.py"], observed_c_hash="0" * 64)
    assert g0.state == G0_SCHEMA_INVALID
    assert g0.state != G0_PRESENT_EXPLICIT_EMPTY
    result = evaluate_transaction_preflight(
        changed_paths=["src/pkg/core.py"],
        units=_units(),
        verification=_verify(),
        policy=_policy(),
        g0=g0,
        proposal_id="p1",
        patch_digest="b" * 64,
    )
    assert result.status == PREFLIGHT_INCOMPLETE
    assert result.incomplete_reason == PDP_INPUT_INCOMPLETE


def test_g0_schema_invalid_payload() -> None:
    g0 = bind_g0_input(["src/pkg/core.py"], payload={"not": "g0"}, payload_provided=True)
    assert g0.state == G0_SCHEMA_INVALID
    assert g0.violations == ()


def test_g0_explicit_empty_ruleset_is_not_unbound() -> None:
    g0 = bind_g0_input(
        ["src/pkg/core.py"],
        payload={"G0_PREFIXES": (), "G0_NAMES": [], "G0_SUBSTRINGS": ()},
        payload_provided=True,
        observed_c_hash=PIN,
    )
    assert g0.state == G0_PRESENT_EXPLICIT_EMPTY
    assert g0.state != G0_UNBOUND
    assert g0.fail_closed is False


def test_g0_present_nonempty_empty_violation_list() -> None:
    g0 = bind_g0_input(["src/pkg/core.py"])
    assert g0.state == G0_PRESENT_NONEMPTY
    assert g0.ruleset_present is True
    assert list(g0.violations) == []


def test_g0_violations_deny_tests_prefix() -> None:
    hits = g0_violations(["tests/test_foo.py"])
    assert hits
    assert any("FORBIDDEN_PREFIX" in item for item in hits)
    g0 = bind_g0_input(["tests/test_foo.py"])
    assert g0.state == G0_PRESENT_NONEMPTY
    assert g0.violations == tuple(hits)


def test_g0_pass_through_src_path() -> None:
    assert g0_violations(["src/pkg/core.py"]) == []


def test_wrap_does_not_auto_admit_g0_deny() -> None:
    unit = _units("tests/test_foo.py")[0]
    g0 = bind_g0_input(["tests/test_foo.py"])
    decision = wrap_decide_c(
        units=[unit],
        changed_paths=["tests/test_foo.py"],
        decision={"writable_resources": [{"path": unit["path"], "element_key": unit["element_key"]}]},
        g0=list(g0.violations),
        verification=_verify(),
        policy=_policy(),
        proposal_id="p-g0",
        patch_digest="b" * 64,
        g0_input_state=g0.state,
        policy_bundle_digest="c" * 64,
    )
    assert decision.decision != AUTO_ADMIT
    assert decision.decision == REJECT
    assert any(item.startswith("G0:") for item in decision.reasons)
    assert decision.g0_input_state == G0_PRESENT_NONEMPTY


def test_fail_closed_g0_never_calls_c_for_auto_admit() -> None:
    g0 = bind_g0_input(["src/pkg/core.py"], bound=False)
    result = evaluate_transaction_preflight(
        changed_paths=["src/pkg/core.py"],
        units=_units(),
        verification=_verify(),
        policy=_policy(),
        g0=g0,
        proposal_id="p1",
        patch_digest="b" * 64,
    )
    assert result.status == PREFLIGHT_INCOMPLETE
    assert result.incomplete_reason == PDP_INPUT_INCOMPLETE
    assert g0.may_invoke_c is False
    assert g0.fail_closed is True


def test_pdp_live_path_does_not_pass_anonymous_g0() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agent_control"
        / "publish"
        / "pdp.py"
    ).read_text(encoding="utf-8")
    assert "g0=[]" not in text
    assert "bind_g0_input" in text
    assert "evaluate_transaction_preflight" in text


def test_pdp_g0_deny_tests_prefix(tmp_path: Path, monkeypatch) -> None:
    from agent_control.publish.pdp import run_publish_pdp
    from agent_shared.bundles.inbox import bundle_dir
    from tests.test_transaction_broker import PROJECT, BASE_SHA, _seed_publish

    forbidden = "tests/test_foo.py"
    state, manifest, _settings = _seed_publish(
        tmp_path, monkeypatch, run_id="run-g0-deny", files=[forbidden], patch_path=forbidden
    )
    root = bundle_dir(
        state, run_id="run-g0-deny", kind="fix", attempt_id="1", bundle_id=manifest.bundle_id
    )
    result = run_publish_pdp(
        state_root=state,
        project=PROJECT,
        run_id="run-g0-deny",
        bundle_id=manifest.bundle_id,
        bundle_root=root,
        manifest=manifest,
        authorized_files=[forbidden],
        source_sha=BASE_SHA,
        agent_branch="agent/run-g0-deny",
        invoked_by="ai-sdlc-lab",
    )
    assert result.decision != AUTO_ADMIT
    assert result.capability is None
    assert result.admission.g0_input_state == G0_PRESENT_NONEMPTY
    assert result.admission.policy_bundle_digest
    assert any("G0:" in item or item.startswith("G0:") for item in result.reasons)


def test_pdp_g0_pass_through_src(tmp_path: Path, monkeypatch) -> None:
    from agent_control.publish.pdp import run_publish_pdp
    from agent_shared.bundles.inbox import bundle_dir
    from tests.test_transaction_broker import PROJECT, BASE_SHA, CORE, _seed_publish

    state, manifest, _settings = _seed_publish(
        tmp_path, monkeypatch, run_id="run-g0-pass", files=[CORE], patch_path=CORE
    )
    root = bundle_dir(
        state, run_id="run-g0-pass", kind="fix", attempt_id="1", bundle_id=manifest.bundle_id
    )
    result = run_publish_pdp(
        state_root=state,
        project=PROJECT,
        run_id="run-g0-pass",
        bundle_id=manifest.bundle_id,
        bundle_root=root,
        manifest=manifest,
        authorized_files=[CORE],
        source_sha=BASE_SHA,
        agent_branch="agent/run-g0-pass",
        invoked_by="ai-sdlc-lab",
    )
    assert result.admission.g0_input_state == G0_PRESENT_NONEMPTY
    assert result.admission.policy_bundle_digest
    assert not any(item.startswith("G0:") for item in result.reasons)
    assert result.decision == AUTO_ADMIT
    assert result.capability is not None


def test_pdp_g0_load_failed_never_auto_admit(tmp_path: Path, monkeypatch) -> None:
    from agent_control.publish import pdp as pdp_mod
    from agent_control.publish.pdp import run_publish_pdp
    from agent_control.transaction.policy_bundle import G0InputBinding
    from agent_shared.bundles.inbox import bundle_dir
    from tests.test_transaction_broker import PROJECT, BASE_SHA, CORE, _seed_publish

    def _failed(_paths):
        return G0InputBinding(
            state=G0_LOAD_FAILED,
            violations=(),
            provenance_c_hash=None,
            source_identity=None,
            ruleset_present=False,
        )

    monkeypatch.setattr(pdp_mod, "bind_g0_input", _failed)
    state, manifest, _settings = _seed_publish(
        tmp_path, monkeypatch, run_id="run-g0-fail", files=[CORE], patch_path=CORE
    )
    root = bundle_dir(
        state, run_id="run-g0-fail", kind="fix", attempt_id="1", bundle_id=manifest.bundle_id
    )
    result = run_publish_pdp(
        state_root=state,
        project=PROJECT,
        run_id="run-g0-fail",
        bundle_id=manifest.bundle_id,
        bundle_root=root,
        manifest=manifest,
        authorized_files=[CORE],
        source_sha=BASE_SHA,
        agent_branch="agent/run-g0-fail",
        invoked_by="ai-sdlc-lab",
    )
    assert result.decision != AUTO_ADMIT
    assert result.capability is None
    assert POLICY_UNAVAILABLE in result.reasons
    assert result.admission.g0_input_state == G0_LOAD_FAILED
