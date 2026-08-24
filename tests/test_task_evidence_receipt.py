"""Structured Gitea task receipts: parse, mismatch, unbound, missing, digest freeze."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from agent_control.transaction.admission import FROZEN_C_HASH, SCANNER_SPECIFIC_C_LOGIC
from agent_control.transaction.evidence.adapters import run_p4_task_finding
from agent_control.transaction.evidence.bus import run_evidence_bus
from agent_control.transaction.evidence.route import (
    REASON_PATCH_TOUCHES_SECURITY_SENSITIVE_CLASS,
    REASON_REPO_POLICY_REQUIRES_SAST,
    REASON_TASK_TYPE_SECURITY_REMEDIATION,
    REQUIRED,
    build_route,
    provider_run_reasons,
    routed_providers,
)
from agent_control.transaction.evidence.task_receipt import (
    UNBOUND_FINDING_MISMATCH,
    UNBOUND_MISSING_BLOCK,
    UNBOUND_TASK_EVIDENCE,
    derive_task_evidence_receipt,
    finding_in_source,
    freeze_gitea_issue,
    parse_structured_fence,
    parse_structured_issue,
)

PIN = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"
DIGEST = "c" * 64
SHA = "abc1234"
REPO = "org/repo"
FINDING = "FIND-EVAL-1"
RULE = "python.lang.security.audit.eval-detected"
SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent_shared"
    / "schemas"
    / "task_evidence_receipt.v1.json"
)

YAML_BLOCK = f"""```yaml
finding_id: {FINDING}
provider: semgrep-ce
rule_id: {RULE}
repository: {REPO}
source_sha: {SHA}
location: src/app.py:12
requested_action: REMEDIATE_FINDING
authorized_mutation_class: SECURITY_FINDING_TASK
initiator: alice
```
"""

JSON_BLOCK = f"""```json
{{
  "finding_id": "{FINDING}",
  "provider": "semgrep-ce",
  "rule_id": "{RULE}",
  "repository": "{REPO}",
  "source_sha": "{SHA}",
  "location": "src/app.py:12",
  "requested_action": "REMEDIATE_FINDING",
  "authorized_mutation_class": "SECURITY_FINDING_TASK",
  "initiator": "alice"
}}
```
"""


def _binding() -> dict:
    return {"repo": REPO, "source_sha": SHA, "patch_digest": DIGEST}


def _issue(body: str, *, number: int = 12, repo: str = REPO, labels: list | None = None) -> dict:
    owner, name = repo.split("/", 1)
    return {
        "number": number,
        "title": "Please remediate the eval finding in the login path",
        "body": body,
        "user": {"login": "alice"},
        "labels": labels or [],
        "html_url": f"http://gitea.local/{owner}/{name}/issues/{number}",
        "repository": {"full_name": repo},
    }


def _source_findings() -> list[dict]:
    return [
        {
            "finding_id": FINDING,
            "identity": FINDING,
            "rule_id": RULE,
            "location_path": "src/app.py",
        }
    ]


def _validate(receipt: dict) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(receipt)


def test_frozen_c_hash_unchanged() -> None:
    assert FROZEN_C_HASH == PIN
    assert SCANNER_SPECIFIC_C_LOGIC == "NO"


def test_structured_yaml_parse() -> None:
    parsed = parse_structured_fence(YAML_BLOCK)
    assert parsed is not None
    assert parsed["finding_id"] == FINDING
    assert parsed["rule_id"] == RULE
    assert parsed["requested_action"] == "REMEDIATE_FINDING"
    assert parsed["initiator"] == "alice"
    freeze = freeze_gitea_issue(_issue("Please fix eval.\n\n" + YAML_BLOCK))
    receipt = derive_task_evidence_receipt(
        freeze,
        binding=_binding(),
        expected_issue_id=12,
        source_findings=_source_findings(),
        source_findings_provided=True,
    )
    _validate(receipt)
    assert receipt["status"] == "BOUND"
    assert receipt["llm_parsed"] is False
    assert receipt["compiled_from"] == "GITEA_ISSUE_STRUCTURED_BLOCK"
    assert receipt["task_digest"] == freeze.digest
    assert receipt["human_initiator"] == "alice"
    assert receipt["source_sha"] == SHA


def test_structured_json_and_labels_parse() -> None:
    json_parsed = parse_structured_fence(JSON_BLOCK)
    assert json_parsed is not None
    assert json_parsed["finding_id"] == FINDING
    labels = [
        f"finding_id:{FINDING}",
        f"rule_id:{RULE}",
        "provider:semgrep-ce",
        f"repository:{REPO}",
        f"source_sha:{SHA}",
        "location:src/app.py:12",
        "requested_action:REMEDIATE_FINDING",
        "authorized_mutation_class:SECURITY_FINDING_TASK",
        "initiator:alice",
    ]
    labeled = parse_structured_issue(_issue("free text only", labels=labels))
    assert labeled["finding_id"] == FINDING
    assert labeled["requested_action"] == "REMEDIATE_FINDING"


def test_finding_match_either_rule_id_form() -> None:
    prefixed = f"rules.{RULE}"
    scan_only = {
        "finding_id": "sarif-eval-identity",
        "identity": "sarif-eval-identity",
        "rule_id": prefixed,
        "location_path": "src/config_parser.py",
    }
    freeze = freeze_gitea_issue(_issue(YAML_BLOCK))
    receipt = derive_task_evidence_receipt(
        freeze,
        binding=_binding(),
        expected_issue_id=12,
        source_findings=[scan_only],
        source_findings_provided=True,
    )
    _validate(receipt)
    assert receipt["status"] == "BOUND"
    assert finding_in_source(freeze.structured, [scan_only]) is True

    prefixed_issue = freeze_gitea_issue(
        _issue(YAML_BLOCK.replace(f"rule_id: {RULE}", f"rule_id: {prefixed}"))
    )
    canonical_scan = {
        "finding_id": "sarif-eval-identity",
        "identity": "sarif-eval-identity",
        "rule_id": RULE,
        "location_path": "src/config_parser.py",
    }
    reverse = derive_task_evidence_receipt(
        prefixed_issue,
        binding=_binding(),
        expected_issue_id=12,
        source_findings=[canonical_scan],
        source_findings_provided=True,
    )
    _validate(reverse)
    assert reverse["status"] == "BOUND"
    assert finding_in_source(prefixed_issue.structured, [canonical_scan]) is True


def test_prose_is_not_an_authorization() -> None:
    body = (
        "Please REMEDIATE_FINDING for eval in src/app.py at SHA abc1234. "
        f"finding_id {FINDING} rule_id {RULE} initiator alice."
    )
    freeze = freeze_gitea_issue(_issue(body))
    assert freeze.missing_structured_block is True
    receipt = derive_task_evidence_receipt(freeze, binding=_binding())
    _validate(receipt)
    assert receipt["unbound_reason"] == UNBOUND_MISSING_BLOCK
    assert receipt["status"] == "INCOMPLETE"
    assert receipt["llm_parsed"] is False
    assert receipt["free_text_authorization"] is False


def test_finding_mismatch_not_confirmed() -> None:
    freeze = freeze_gitea_issue(_issue(YAML_BLOCK))
    receipt = derive_task_evidence_receipt(
        freeze,
        binding=_binding(),
        expected_issue_id=12,
        source_findings=[{"finding_id": "OTHER", "rule_id": "other.rule", "location_path": "x.py"}],
        source_findings_provided=True,
    )
    _validate(receipt)
    assert receipt["unbound_reason"] == UNBOUND_FINDING_MISMATCH
    assert receipt["status"] == "UNBOUND"
    assert receipt["binding"]["bound"] is False
    result = run_p4_task_finding(
        binding=_binding(),
        issue=_issue(YAML_BLOCK),
        source_findings=[{"finding_id": "OTHER", "rule_id": "other.rule", "location_path": "x.py"}],
    )
    assert result["status"] != "OK"
    assert result["detail"] == UNBOUND_FINDING_MISMATCH
    for item in result["receipts"]:
        assert item.get("authorization_class") != "EXPLICIT" or item.get("result_status") != "PASS"


def test_wrong_task_unbound_no_auto_admit() -> None:
    route = build_route(
        ["PRODUCTION_SOURCE_CHANGE", "SECURITY_FINDING_TASK"],
        patch_digest=DIGEST,
        repository=REPO,
    )
    other_repo = run_p4_task_finding(
        binding=_binding(),
        issue=_issue(YAML_BLOCK.replace(f"repository: {REPO}", "repository: other/repo")),
        expected_repository=REPO,
        source_findings=_source_findings(),
    )
    other_task = run_p4_task_finding(
        binding=_binding(),
        issue=_issue(YAML_BLOCK, number=99),
        expected_issue_id=12,
        source_findings=_source_findings(),
    )
    wrong_sha = run_p4_task_finding(
        binding=_binding(),
        issue=_issue(YAML_BLOCK.replace(f"source_sha: {SHA}", "source_sha: deadbee")),
        expected_issue_id=12,
        source_findings=_source_findings(),
    )
    for result in (other_repo, other_task, wrong_sha):
        assert result["detail"] == UNBOUND_TASK_EVIDENCE
        assert result["status"] != "OK"
    bundle = run_evidence_bus(
        binding=_binding(),
        route=route,
        adapter_kwargs={
            "P1": {"verdict": {"passed": True}},
            "P2": {"findings": []},
            "P3": {},
            "P4": {
                "issue": _issue(YAML_BLOCK, number=99),
                "expected_issue_id": 12,
                "source_findings": _source_findings(),
            },
        },
    )
    assert bundle["auto_admit_blocked"] is True
    assert "P4" in bundle["required_provider_failures"]
    authorizing = [
        item
        for item in bundle["receipts"]
        if item.get("producer", {}).get("name") == "gitea_task_envelope_finding_adapter"
        and item.get("can_authorize")
    ]
    assert authorizing == []


def test_missing_structured_block_no_auto_admit_from_prose() -> None:
    route = build_route(
        ["PRODUCTION_SOURCE_CHANGE", "SECURITY_FINDING_TASK"],
        patch_digest=DIGEST,
        repository=REPO,
    )
    result = run_p4_task_finding(
        binding=_binding(),
        issue=_issue("please fix the security bug in src/app.py"),
        task={"authorized_files": ["src/app.py"]},
    )
    assert result["detail"] == UNBOUND_MISSING_BLOCK
    assert result["status"] != "OK"
    bundle = run_evidence_bus(
        binding=_binding(),
        route=route,
        adapter_kwargs={
            "P1": {"verdict": {"passed": True}},
            "P2": {"findings": []},
            "P3": {},
            "P4": {"issue": _issue("please fix the security bug in src/app.py")},
        },
    )
    assert bundle["auto_admit_blocked"] is True
    assert "P4" in bundle["required_provider_failures"]


def test_drift_digest_stability() -> None:
    original = _issue(YAML_BLOCK)
    freeze = freeze_gitea_issue(original)
    first = derive_task_evidence_receipt(
        freeze,
        binding=_binding(),
        expected_issue_id=12,
        source_findings=_source_findings(),
        source_findings_provided=True,
    )
    edited = _issue(YAML_BLOCK + "\n\nEdited after transaction creation.")
    later_freeze = freeze_gitea_issue(edited)
    still = derive_task_evidence_receipt(
        freeze,
        binding=_binding(),
        expected_issue_id=12,
        source_findings=_source_findings(),
        source_findings_provided=True,
    )
    assert first["task_digest"] == freeze.digest
    assert still["task_digest"] == freeze.digest
    assert later_freeze.digest != freeze.digest
    result = run_p4_task_finding(
        binding=_binding(),
        issue=edited,
        frozen_issue=freeze,
        source_findings=_source_findings(),
        expected_issue_id=12,
    )
    extra = result["receipts"][0]["extra"]["task_evidence_receipt"]
    assert extra["task_digest"] == freeze.digest


def test_security_remediation_route_requires_task_and_sast_with_reasons() -> None:
    route = build_route(
        ["PRODUCTION_SOURCE_CHANGE", "SECURITY_FINDING_TASK"],
        route_id="security_finding_remediation_v1",
        repository="ai-sdlc-lab/demo-app",
        patch_digest=DIGEST,
    )
    reasons = provider_run_reasons(route)
    assert reasons["P4"] == [REASON_TASK_TYPE_SECURITY_REMEDIATION]
    assert REASON_PATCH_TOUCHES_SECURITY_SENSITIVE_CLASS in reasons["P2"]
    assert REASON_REPO_POLICY_REQUIRES_SAST in reasons["P2"]
    providers = {item.provider_id: item.requirement_class for item in routed_providers(route)}
    assert providers["P1"] == REQUIRED
    assert providers["P2"] == REQUIRED
    assert providers["P4"] == REQUIRED
    assert route.llm_router is False
    payload = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "maintenance-evals"
            / "results"
            / "w5-live-evidence-provider-integration-v1"
            / "live_evidence_route.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "evidence_route.v1"
    assert payload["llm_router"] is False
    live_reasons = {
        provider["provider_id"]: provider.get("reasons") or []
        for rule in payload["rules"]
        for provider in rule["providers"]
    }
    assert REASON_TASK_TYPE_SECURITY_REMEDIATION in live_reasons["P4"]
    assert REASON_PATCH_TOUCHES_SECURITY_SENSITIVE_CLASS in live_reasons["P2"]
    assert REASON_REPO_POLICY_REQUIRES_SAST in live_reasons["P2"]
