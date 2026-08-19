"""W0-C ExperienceVerificationResult contract, adapters, and schema digest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent_control.experience_verification_adapters import (
    from_eval_outcome,
    from_production_result,
    from_sandbox_result,
)
from agent_shared.models.ci import CiVerificationResult, RequiredWorkflow
from agent_shared.models.experience_verification import (
    SCHEMA_VERSION,
    ExperienceVerificationResult,
    VerificationLane,
)
from agent_shared.models.verification_claim import VerificationClaim

ACP_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ACP_ROOT / "src" / "agent_shared" / "schemas" / "experience_verification_result.v1.json"
)
DIGESTS_PATH = ACP_ROOT / "src" / "agent_shared" / "schemas" / "DIGESTS.md"

VALID_FIXTURE = {
    "schema_version": "experience_verification_result.v1",
    "verification_scope": "final",
    "authority_domain": "eval_harness",
    "official": {"commands": ["python -m pytest -q"], "pass": True},
    "additional": {"commands": ["ruff check ."], "pass": False},
    "verified_success": False,
    "failure_class": None,
    "normalized_failures": [],
    "evidence_refs": ["claim-abc"],
    "started_at": None,
    "finished_at": None,
}


def _pinned_digest(schema_name: str) -> str:
    lines = DIGESTS_PATH.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() == schema_name:
            nxt = lines[index + 1].strip()
            prefix = "sha256:"
            if not nxt.lower().startswith(prefix):
                raise AssertionError(f"digest line missing sha256: prefix: {nxt}")
            return nxt.split(":", 1)[1].strip()
    raise AssertionError(f"no digest pin for {schema_name}")


def _result(
    *,
    scope: str = "final",
    domain: str = "eval_harness",
    official_pass: bool = True,
    additional_pass: bool = False,
    verified_success: bool | None = None,
) -> ExperienceVerificationResult:
    return ExperienceVerificationResult(
        verification_scope=scope,  # type: ignore[arg-type]
        authority_domain=domain,  # type: ignore[arg-type]
        official=VerificationLane(commands=["pytest"], passed=official_pass),
        additional=VerificationLane(commands=["ruff"], passed=additional_pass),
        verified_success=official_pass if verified_success is None else verified_success,
        evidence_refs=["ref-1"],
    )


def test_schema_validates_fixture() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(VALID_FIXTURE)
    model = ExperienceVerificationResult.model_validate(VALID_FIXTURE)
    Draft202012Validator(schema).validate(model.to_schema_dict())
    assert "can_finalize_production_episode" not in model.to_schema_dict()


def test_schema_sha256_matches_pinned_digest() -> None:
    digest = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
    assert digest == _pinned_digest(SCHEMA_VERSION)


def test_can_finalize_is_derived_from_authority_domain() -> None:
    assert _result(domain="ct102_production").can_finalize_production_episode is True
    assert _result(domain="eval_harness").can_finalize_production_episode is False
    assert _result(domain="ct104_advisory", scope="fast").can_finalize_production_episode is False
    eval_final = _result(domain="eval_harness", scope="final")
    assert eval_final.verification_scope == "final"
    assert eval_final.can_finalize_production_episode is False


def test_can_finalize_is_not_an_input_field() -> None:
    with pytest.raises(ValidationError):
        ExperienceVerificationResult(
            verification_scope="final",
            authority_domain="eval_harness",
            official=VerificationLane(commands=[], passed=True),
            additional=VerificationLane(commands=[], passed=True),
            verified_success=True,
            can_finalize_production_episode=True,
        )


def test_official_and_additional_passes_are_independent() -> None:
    mixed = _result(official_pass=True, additional_pass=False, verified_success=True)
    assert mixed.official.passed is True
    assert mixed.additional.passed is False
    inverted = _result(official_pass=False, additional_pass=True, verified_success=False)
    assert inverted.official.passed is False
    assert inverted.additional.passed is True
    assert mixed.official.passed is not mixed.additional.passed
    assert inverted.official.passed is not inverted.additional.passed


def test_eval_outcome_adapter_preserves_lanes_and_claim_id() -> None:
    outcome = SimpleNamespace(
        official_pass=True,
        additional_pass=False,
        official_commands=(SimpleNamespace(command="python -m pytest -q"),),
        additional_commands=(SimpleNamespace(command="ruff check ."),),
        claim_id="sha256-claim-1",
        verified=False,
    )
    mapped = from_eval_outcome(outcome)
    assert mapped.verification_scope == "final"
    assert mapped.authority_domain == "eval_harness"
    assert mapped.can_finalize_production_episode is False
    assert mapped.official.passed is True
    assert mapped.additional.passed is False
    assert mapped.official.commands == ["python -m pytest -q"]
    assert mapped.additional.commands == ["ruff check ."]
    assert "sha256-claim-1" in mapped.evidence_refs

    payload = {
        "official_benchmark_pass": False,
        "v10_additional_verification_pass": True,
        "official_commands": [{"command": "pytest"}],
        "additional_commands": [{"command": "ruff"}],
        "claim_id": "claim-from-payload",
        "verified": False,
    }
    from_dict = from_eval_outcome(payload)
    assert from_dict.official.passed is False
    assert from_dict.additional.passed is True
    assert from_dict.evidence_refs == ["claim-from-payload"]


def test_sandbox_adapter_is_fast_advisory() -> None:
    payload = {
        "schema_version": "verification_result.v1",
        "status": "passed",
        "passed": True,
        "message": "ok",
        "commands": [{"command_id": "pytest_narrow", "exit_code": 0}],
        "sandbox": {"session_id": "sbx-1", "network": False},
    }
    mapped = from_sandbox_result(payload)
    assert mapped.verification_scope == "fast"
    assert mapped.authority_domain == "ct104_advisory"
    assert mapped.can_finalize_production_episode is False
    assert mapped.official.passed is True
    assert mapped.official.commands == ["pytest_narrow"]
    assert mapped.additional.passed is False
    assert mapped.evidence_refs == ["sbx-1"]


def test_production_ci_and_claim_adapters_are_ct102_final() -> None:
    ci = CiVerificationResult(
        fix_run_id="fix-1",
        repository="acme/widgets",
        expected_head_commit_sha="a" * 40,
        verdict="verified",
        required_workflows=[RequiredWorkflow(path=".gitea/workflows/ci.yaml")],
        evaluated_at="2026-08-18T00:00:00Z",
    )
    from_ci = from_production_result(ci)
    assert from_ci.verification_scope == "final"
    assert from_ci.authority_domain == "ct102_production"
    assert from_ci.can_finalize_production_episode is True
    assert from_ci.official.passed is True
    assert from_ci.official.commands == [".gitea/workflows/ci.yaml"]
    assert "fix-1" in from_ci.evidence_refs

    claim = VerificationClaim(
        session_id="sess-1",
        run_id="run-1",
        repo="acme/widgets",
        claim="ci verified",
        scope_commit_sha="a" * 40,
        source="ct102",
        status="passed",
        command_id="gitea_workflow",
        artifact_digest="deadbeef",
        created_at="2026-08-18T00:00:00Z",
        updated_at="2026-08-18T00:01:00Z",
    )
    from_claim = from_production_result(claim)
    assert from_claim.authority_domain == "ct102_production"
    assert from_claim.can_finalize_production_episode is True
    assert from_claim.official.commands == ["gitea_workflow"]
    assert "deadbeef" in from_claim.evidence_refs


def test_adapters_do_not_import_maintenance_evals() -> None:
    from agent_control import experience_verification_adapters as adapters

    source = Path(adapters.__file__).read_text(encoding="utf-8")
    assert "import maintenance_evals" not in source
    assert "from maintenance_evals" not in source
