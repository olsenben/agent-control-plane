"""Live Semgrep P2 provider: SARIF, delta, fail-closed, no C retune."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_control.transaction.admission import FROZEN_C_HASH, SCANNER_SPECIFIC_C_LOGIC
from agent_control.transaction.evidence.adapters import run_p2_sast
from agent_control.transaction.evidence.bus import run_evidence_bus
from agent_control.transaction.evidence.delta import compute_security_evidence_delta
from agent_control.transaction.evidence.providers.semgrep import (
    CASE_SPECIFIC_RULE_ADDED,
    PROVIDER_DURABLE_AUTHORITY,
    SEMGREP_VERSION,
)
from agent_control.transaction.evidence.providers.semgrep.ruleset import (
    RULESET_DIGEST,
    compute_ruleset_digest,
    loaded_rule_ids,
    ruleset_path,
)
from agent_control.transaction.evidence.receipts import (
    STATUS_MALFORMED,
    STATUS_NEW_FINDING,
    STATUS_PASS,
    STATUS_REQUIRED_EVIDENCE_UNAVAILABLE,
    STATUS_TIMEOUT,
    STATUS_TOOL_FAILURE,
)
from agent_control.transaction.evidence.route import build_route
from agent_control.transaction.evidence.sarif import (
    canonicalize_rule_id,
    finding_identity,
    loaded_sarif_rule_ids,
    parse_sarif_findings,
)
from agent_shared.models.transaction.evidence import EvidenceProvider

PIN = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"
DIGEST = "c" * 64
SHA = "abc1234"
RULE = "python.lang.security.audit.eval-detected"
PREFIXED_RULE = "rules.python.lang.security.audit.eval-detected"
LIVE_SOURCE_SARIF = (
    Path(__file__).resolve().parents[2]
    / "maintenance-evals"
    / "results"
    / "w5-live-evidence-provider-integration-v1"
    / "raw_sarif"
    / "fixture_source_preconfirm.sarif.json"
)


def _binding(**overrides: Any) -> dict[str, Any]:
    payload = {"repo": "org/repo", "source_sha": SHA, "patch_digest": DIGEST}
    payload.update(overrides)
    return payload


def _sarif(results: list[dict[str, Any]], *, rules: list[str] | None = None) -> dict[str, Any]:
    rule_ids = rules if rules is not None else sorted({str(item["ruleId"]) for item in results} or [RULE])
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "semgrep",
                        "rules": [{"id": rid, "name": rid} for rid in rule_ids],
                    }
                },
                "results": results,
            }
        ],
    }


def _result(rule_id: str, uri: str, line: int, fp: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ruleId": rule_id,
        "level": "error",
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": line, "startColumn": 1},
                }
            }
        ],
        "properties": {"cwe": "CWE-95"},
    }
    if fp:
        item["partialFingerprints"] = {"primaryLocationLineHash": fp}
    return item


def _trees(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    (source / "app.py").write_text("x = 1\n", encoding="utf-8")
    (candidate / "app.py").write_text("x = 1\n", encoding="utf-8")
    return source, candidate


def test_frozen_c_hash_unchanged() -> None:
    assert FROZEN_C_HASH == PIN
    assert SCANNER_SPECIFIC_C_LOGIC == "NO"
    assert CASE_SPECIFIC_RULE_ADDED == "NO"
    assert PROVIDER_DURABLE_AUTHORITY == "NONE"


def test_no_semgrep_branch_in_admission_c_or_bus() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "agent_control"
    forbidden = ('if provider == "semgrep"', "if provider == 'semgrep'")
    paths = [
        root / "transaction" / "evidence" / "bus.py",
        root / "transaction" / "evidence" / "project.py",
        root / "transaction" / "admission" / "frozen_c.py",
        root / "transaction" / "admission" / "__init__.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, path


def test_sarif_parse_and_finding_match() -> None:
    payload = _sarif(
        [_result(RULE, "src/app.py", 4, fp="fp-eval-1")],
        rules=[RULE],
    )
    findings = parse_sarif_findings(payload)
    assert len(findings) == 1
    row = findings[0]
    assert row["rule_id"] == RULE
    assert row["location_path"] == "src/app.py"
    assert row["start_line"] == 4
    expected = finding_identity(
        rule_id=RULE,
        location_path="src/app.py",
        start_line=4,
        start_column=1,
        fingerprints={"primaryLocationLineHash": "fp-eval-1"},
    )
    assert row["identity"] == expected
    again = parse_sarif_findings(payload)
    assert again[0]["identity"] == row["identity"]


def test_sarif_rules_prefix_canonicalizes_to_yaml_id() -> None:
    assert canonicalize_rule_id(PREFIXED_RULE) == RULE
    assert canonicalize_rule_id(RULE) == RULE
    loc = "src/src/config_parser.py"
    assert finding_identity(
        rule_id=PREFIXED_RULE,
        location_path=loc,
        start_line=8,
        start_column=12,
    ) == finding_identity(
        rule_id=RULE,
        location_path=loc,
        start_line=8,
        start_column=12,
    )
    payload = json.loads(LIVE_SOURCE_SARIF.read_text(encoding="utf-8"))
    raw_id = str(payload["runs"][0]["results"][0]["ruleId"])
    assert raw_id == PREFIXED_RULE
    findings = parse_sarif_findings(payload)
    row = next(item for item in findings if item["rule_id"].endswith("eval-detected"))
    assert row["rule_id"] == RULE
    sarif_ids = loaded_sarif_rule_ids(payload)
    assert RULE in sarif_ids
    assert PREFIXED_RULE not in sarif_ids
    assert row["identity"] == finding_identity(
        rule_id=PREFIXED_RULE,
        location_path=row["location_path"],
        start_line=row["start_line"],
        start_column=row["start_column"],
        fingerprints=row.get("fingerprints") or {},
    )
    source = parse_sarif_findings(
        _sarif([_result(PREFIXED_RULE, "app.py", 3, fp="same")], rules=[PREFIXED_RULE])
    )
    candidate = parse_sarif_findings(_sarif([_result(RULE, "app.py", 3, fp="same")], rules=[RULE]))
    delta = compute_security_evidence_delta(source, candidate)
    assert source[0]["rule_id"] == RULE
    assert candidate[0]["identity"] == source[0]["identity"]
    assert delta["counts"]["persisting"] == 1
    assert delta["counts"]["new"] == 0
    assert delta["counts"]["resolved"] == 0


def test_idempotent_digest_identity() -> None:
    payload = _sarif([_result(RULE, "a.py", 2, fp="stable")])
    first = parse_sarif_findings(payload)
    second = parse_sarif_findings(payload)
    assert first[0]["identity"] == second[0]["identity"]
    delta_a = compute_security_evidence_delta(first, second)
    delta_b = compute_security_evidence_delta(first, second)
    assert delta_a["digest"] == delta_b["digest"]
    assert delta_a["counts"]["persisting"] == 1
    assert delta_a["counts"]["new"] == 0
    assert delta_a["counts"]["resolved"] == 0


def test_delta_resolved_new_persisting() -> None:
    source = parse_sarif_findings(
        _sarif(
            [
                _result(RULE, "keep.py", 1, fp="keep"),
                _result(RULE, "gone.py", 2, fp="gone"),
            ]
        )
    )
    candidate = parse_sarif_findings(
        _sarif(
            [
                _result(RULE, "keep.py", 1, fp="keep"),
                _result(RULE, "new.py", 3, fp="new"),
            ]
        )
    )
    delta = compute_security_evidence_delta(source, candidate)
    assert [item["location_path"] for item in delta["resolved"]] == ["gone.py"]
    assert [item["location_path"] for item in delta["new"]] == ["new.py"]
    assert [item["location_path"] for item in delta["persisting"]] == ["keep.py"]


def test_malformed_sarif_fail_closed(tmp_path: Path) -> None:
    source, candidate = _trees(tmp_path)
    result = run_p2_sast(
        binding=_binding(),
        source_root=str(source),
        candidate_root=str(candidate),
        raw_source_sarif="{not-json",
        raw_candidate_sarif="{not-json",
    )
    assert result["status"] in {STATUS_MALFORMED, STATUS_TOOL_FAILURE}
    assert result["receipts"]
    assert result["receipts"][0]["result_status"] != STATUS_PASS
    route = build_route(["SECURITY_FINDING_TASK"], patch_digest=DIGEST, repository="org/repo")
    bundle = run_evidence_bus(
        binding=_binding(),
        route=route,
        adapter_kwargs={
            "P2": {
                "source_root": str(source),
                "candidate_root": str(candidate),
                "raw_source_sarif": "{not-json",
                "raw_candidate_sarif": "{not-json",
            },
            "P3": {"force_failure": False},
        },
    )
    assert bundle["auto_admit_blocked"] is True
    assert "P2" in bundle["required_provider_failures"]


def test_timeout_and_crash_mapping(tmp_path: Path) -> None:
    source, candidate = _trees(tmp_path)

    def timeout_exec(argv, *, env, timeout_sec, cwd=None):  # noqa: ANN001
        assert "GITEA_BOT_TOKEN" not in env
        assert "--config auto" not in " ".join(argv)
        return {
            "exit_code": None,
            "timed_out": True,
            "stdout": "",
            "stderr": "timeout",
            "duration_ms": 1.0,
        }

    timed = run_p2_sast(
        binding=_binding(),
        source_root=str(source),
        candidate_root=str(candidate),
        executor=timeout_exec,
    )
    assert timed["status"] == STATUS_TIMEOUT
    assert timed["receipts"][0]["result_status"] in {STATUS_TIMEOUT, STATUS_TOOL_FAILURE}

    def crash_exec(argv, *, env, timeout_sec, cwd=None):  # noqa: ANN001
        return {
            "exit_code": 2,
            "timed_out": False,
            "stdout": "",
            "stderr": "boom",
            "duration_ms": 1.0,
        }

    crashed = run_p2_sast(
        binding=_binding(),
        source_root=str(source),
        candidate_root=str(candidate),
        executor=crash_exec,
    )
    assert crashed["status"] == STATUS_TOOL_FAILURE
    assert crashed["receipts"][0]["result_status"] != STATUS_PASS


def test_zero_rules_fail_closed(tmp_path: Path) -> None:
    source, candidate = _trees(tmp_path)
    empty = {
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "semgrep", "rules": []}}, "results": []}],
    }
    result = run_p2_sast(
        binding=_binding(),
        source_root=str(source),
        candidate_root=str(candidate),
        raw_source_sarif=empty,
        raw_candidate_sarif=empty,
    )
    assert result["status"] == STATUS_TOOL_FAILURE
    assert result["receipts"][0]["result_status"] != STATUS_PASS
    assert result["detail"] == "ZERO_RULES"


def test_empty_kwargs_not_synthetic_pass() -> None:
    result = run_p2_sast(binding=_binding())
    assert result["status"] != "OK"
    statuses = {item.get("result_status") for item in result["receipts"]}
    assert STATUS_PASS not in statuses
    assert STATUS_REQUIRED_EVIDENCE_UNAVAILABLE in statuses or STATUS_TOOL_FAILURE in statuses
    route = build_route(["SECURITY_FINDING_TASK"], patch_digest=DIGEST, repository="org/repo")
    bundle = run_evidence_bus(binding=_binding(), route=route, adapter_kwargs={"P2": {}, "P3": {}})
    assert bundle["auto_admit_blocked"] is True
    assert "P2" in bundle["required_provider_failures"]


def test_exit_zero_with_findings_is_findings_present(tmp_path: Path) -> None:
    source, candidate = _trees(tmp_path)
    source_sarif = _sarif([], rules=[RULE])
    candidate_sarif = _sarif([_result(RULE, "app.py", 3, fp="new-eval")], rules=[RULE])
    result = run_p2_sast(
        binding=_binding(),
        source_root=str(source),
        candidate_root=str(candidate),
        raw_source_sarif=source_sarif,
        raw_candidate_sarif=candidate_sarif,
    )
    assert result["status"] == "OK"
    assert result["detail"] == "FINDINGS_PRESENT"
    extra = result["receipts"][0]["extra"]
    assert extra["execution"]["candidate"]["outcome"] == "FINDINGS_PRESENT"
    assert extra["delta"]["counts"]["new"] == 1
    assert extra["raw_sarif_preserved"] is True
    statuses = {item["result_status"] for item in result["receipts"]}
    assert STATUS_NEW_FINDING in statuses
    assert STATUS_PASS not in statuses


def test_source_candidate_delta_receipts(tmp_path: Path) -> None:
    source, candidate = _trees(tmp_path)
    source_sarif = _sarif(
        [_result(RULE, "keep.py", 1, fp="keep"), _result(RULE, "old.py", 2, fp="old")],
        rules=[RULE],
    )
    candidate_sarif = _sarif(
        [_result(RULE, "keep.py", 1, fp="keep"), _result(RULE, "fresh.py", 4, fp="fresh")],
        rules=[RULE],
    )
    result = run_p2_sast(
        binding=_binding(),
        source_root=str(source),
        candidate_root=str(candidate),
        raw_source_sarif=source_sarif,
        raw_candidate_sarif=candidate_sarif,
    )
    extra = result["receipts"][0]["extra"]
    delta = extra["delta"]
    assert delta["schema_version"] == "security_evidence_delta.v1"
    assert delta["counts"]["resolved"] == 1
    assert delta["counts"]["new"] == 1
    assert delta["counts"]["persisting"] == 1
    buckets = {item["extra"].get("delta_bucket") for item in result["receipts"] if item.get("extra")}
    assert {"new", "persisting", "resolved"} <= buckets


def test_stale_wrong_source_wrong_patch_binding(tmp_path: Path) -> None:
    source, candidate = _trees(tmp_path)
    clean = _sarif([], rules=[RULE])
    live = run_p2_sast(
        binding=_binding(),
        source_root=str(source),
        candidate_root=str(candidate),
        raw_source_sarif=clean,
        raw_candidate_sarif=clean,
    )
    route = build_route(["SECURITY_FINDING_TASK"], patch_digest=DIGEST, repository="org/repo")
    wrong_source = run_evidence_bus(
        binding=_binding(source_sha="zzzzzzz"),
        route=route,
        extra_receipts=live["receipts"],
        adapter_kwargs={"P2": {"force_failure": True}, "P3": {}},
    )
    assert wrong_source["auto_admit_blocked"] is True
    reasons = [r for item in wrong_source["invalid_receipts"] for r in (item.get("binding_reasons") or [])]
    assert "WRONG_SOURCE" in reasons

    wrong_patch = run_evidence_bus(
        binding=_binding(patch_digest="d" * 64),
        route=route,
        extra_receipts=live["receipts"],
        adapter_kwargs={"P2": {"force_failure": True}, "P3": {}},
    )
    patch_reasons = [r for item in wrong_patch["invalid_receipts"] for r in (item.get("binding_reasons") or [])]
    assert "WRONG_PATCH" in patch_reasons

    stale = run_evidence_bus(
        binding=_binding(candidate_digest="e" * 64),
        route=route,
        extra_receipts=[
            {
                **live["receipts"][0],
                "binding": {
                    **live["receipts"][0]["binding"],
                    "candidate_digest": "f" * 64,
                },
                "candidate_digest": "f" * 64,
            }
        ],
        adapter_kwargs={"P2": {"force_failure": True}, "P3": {}},
    )
    stale_reasons = [r for item in stale["invalid_receipts"] for r in (item.get("binding_reasons") or [])]
    assert "STALE" in stale_reasons


def test_unbound_live_path_fail_closed() -> None:
    result = run_p2_sast(binding={"repo": "org/repo"})
    assert result["receipts"][0]["result_status"] in {
        STATUS_REQUIRED_EVIDENCE_UNAVAILABLE,
        STATUS_TOOL_FAILURE,
    }
    assert result["status"] != "OK"


def test_provider_descriptor_and_ruleset_digest() -> None:
    assert SEMGREP_VERSION == "1.110.0"
    assert ruleset_path().is_file()
    assert compute_ruleset_digest() == RULESET_DIGEST
    assert len(loaded_rule_ids()) >= 1
    descriptor = EvidenceProvider.model_validate_json(
        (
            Path(__file__).resolve().parents[1]
            / "src"
            / "agent_control"
            / "transaction"
            / "evidence"
            / "providers"
            / "semgrep"
            / "provider.json"
        ).read_text(encoding="utf-8")
    )
    assert descriptor.imports_admission_controller is False
    assert descriptor.trust_inferred_from_format is False
    assert descriptor.baseline_and_candidate_required is True


def test_sanitized_env_strips_credentials() -> None:
    from agent_control.transaction.evidence.providers.semgrep.runner import sanitized_env

    env = sanitized_env(
        {
            "PATH": "/bin",
            "GITEA_BOT_TOKEN": "secret",
            "CAPABILITY_SIGNING_KEY": "k",
            "BROKER_PASSWORD": "p",
            "OPENAI_API_KEY": "sk",
        }
    )
    assert "GITEA_BOT_TOKEN" not in env
    assert "CAPABILITY_SIGNING_KEY" not in env
    assert "BROKER_PASSWORD" not in env
    assert "OPENAI_API_KEY" not in env
    assert env["PATH"] == "/bin"


def test_in_process_kwargs_omit_synthetic_p2_pass() -> None:
    from types import SimpleNamespace

    from agent_control.publish.pdp import in_process_adapter_kwargs

    envelope = SimpleNamespace(
        authorized_files=["src/a.py"],
        authorized_surfaces=[],
        authorized_change_classes=["PRODUCTION_SOURCE_CHANGE"],
    )
    kwargs = in_process_adapter_kwargs(envelope=envelope, units=[])
    assert "P2" not in kwargs
