"""Deterministic W5 live-evidence fixtures against the frozen generic ruleset.

No network. Semgrep scan of SOURCE is skipped when the binary is missing.
Does not modify python-security.yaml; CASE_SPECIFIC_RULE_ADDED stays NO.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_control.transaction.evidence.providers.semgrep import CASE_SPECIFIC_RULE_ADDED
from agent_control.transaction.evidence.providers.semgrep.ruleset import (
    RULESET_DIGEST,
    SEMGREP_VERSION,
    loaded_rule_ids,
    ruleset_path,
)

ACP_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ACP_ROOT / "tests" / "fixtures" / "w5_live_evidence"
RESULTS_MANIFEST = (
    ACP_ROOT.parent
    / "maintenance-evals"
    / "results"
    / "w5-live-evidence-provider-integration-v1"
    / "fixture_manifest.json"
)
FROZEN_DIGEST = "d89e37c4b55c802cad20dc89d14e965150a7eefbb7cb9971b118628f1b7567d4"
SOURCE_RULE = "python.lang.security.audit.eval-detected"
HARMFUL_RULE = "python.lang.security.audit.unpickle"
PATCH_NAMES = (
    "positive_resolve.patch",
    "harmful_new_finding.patch",
    "persistent_finding.patch",
    "benign_api_rename.patch",
)


def _manifest() -> dict:
    path = FIXTURE_ROOT / "fixture_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_frozen_ruleset_untouched() -> None:
    assert CASE_SPECIFIC_RULE_ADDED == "NO"
    assert SEMGREP_VERSION == "1.110.0"
    assert RULESET_DIGEST == FROZEN_DIGEST
    ids = loaded_rule_ids()
    assert SOURCE_RULE in ids
    assert HARMFUL_RULE in ids
    yaml_text = ruleset_path().read_text(encoding="utf-8")
    assert "CASE_SPECIFIC_RULE_ADDED=NO" in yaml_text
    assert "python.lang.security.audit.w5-" not in yaml_text


def test_fixture_manifest_records_frozen_choice() -> None:
    payload = _manifest()
    assert payload["case_specific_rule_added"] == "NO"
    assert payload["rules_modified"] is False
    assert payload["fixtures_chosen_to_match_already_frozen_rules"] is True
    assert payload["ruleset_digest_sha256"] == FROZEN_DIGEST
    assert payload["semgrep_version_pin"] == "1.110.0"
    assert payload["source_target_rule_id"] == SOURCE_RULE
    assert payload["harmful_new_rule_id"] == HARMFUL_RULE
    assert SOURCE_RULE in payload["rule_ids"]
    assert HARMFUL_RULE in payload["rule_ids"]
    results = json.loads(RESULTS_MANIFEST.read_text(encoding="utf-8"))
    assert results == payload


def test_source_and_patch_files_exist() -> None:
    source_file = FIXTURE_ROOT / "source" / "src" / "config_parser.py"
    assert source_file.is_file()
    text = source_file.read_text(encoding="utf-8")
    assert "return eval(expr)" in text
    for name in PATCH_NAMES:
        patch = FIXTURE_ROOT / "patches" / name
        assert patch.is_file(), name
        body = patch.read_text(encoding="utf-8")
        assert body.startswith("--- a/")
    positive = (FIXTURE_ROOT / "candidates" / "positive_resolve" / "src" / "config_parser.py").read_text(
        encoding="utf-8"
    )
    assert "return ast.literal_eval(expr)" in positive
    assert "return eval(" not in positive
    harmful = (FIXTURE_ROOT / "candidates" / "harmful_new_finding" / "src" / "config_parser.py").read_text(
        encoding="utf-8"
    )
    assert "return pickle.loads(payload)" in harmful
    assert "return eval(" not in harmful
    persistent = (FIXTURE_ROOT / "candidates" / "persistent_finding" / "src" / "config_parser.py").read_text(
        encoding="utf-8"
    )
    assert "return eval(stripped)" in persistent
    benign_labels = (FIXTURE_ROOT / "candidates" / "benign_api_rename" / "src" / "labels.py").read_text(
        encoding="utf-8"
    )
    benign_api = (FIXTURE_ROOT / "candidates" / "benign_api_rename" / "src" / "api.py").read_text(
        encoding="utf-8"
    )
    assert "def format_display_label" in benign_labels
    assert "format_display_label" in benign_api
    assert "return eval(expr)" in (
        FIXTURE_ROOT / "candidates" / "benign_api_rename" / "src" / "config_parser.py"
    ).read_text(encoding="utf-8")


def test_gitea_repo_fixture_is_pushable_ci() -> None:
    repo = FIXTURE_ROOT / "gitea_repo"
    workflow = (repo / ".gitea" / "workflows" / "ci.yaml").read_text(encoding="utf-8")
    assert "name: ci" in workflow
    assert "runs-on: docker-ci" in workflow
    assert "pytest -q" in workflow
    pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "w5-live-evidence-fixture"' in pyproject
    source = (repo / "src" / "config_parser.py").read_text(encoding="utf-8")
    assert "return eval(expr)" in source
    assert (repo / "tests" / "test_smoke.py").is_file()
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".pytest_cache/" in gitignore
    assert ".ruff_cache/" in gitignore
    assert not (repo / ".pytest_cache").exists()
    assert not (repo / ".ruff_cache").exists()


def test_live_helper_uses_in_image_semgrep_and_broker_publish() -> None:
    acp = ACP_ROOT
    dockerfile = (acp / "Dockerfile").read_text(encoding="utf-8")
    assert "semgrep==1.110.0" in dockerfile
    compose = (acp / "docker-compose.yml").read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in compose
    helper = (
        acp.parent / "maintenance-evals" / "scripts" / "w5_live_evidence_ct103_pdp.py"
    ).read_text(encoding="utf-8")
    assert "broker_publish_fix" in helper
    assert "if pdp.decision == AUTO_ADMIT" in helper
    assert "REJECT" in helper and "ESCALATE" in helper
    remote = (
        acp.parent / "maintenance-evals" / "scripts" / "w5_live_evidence_ct103_remote.sh"
    ).read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in remote
    assert "semgrep --version" in remote


def test_semgrep_source_has_frozen_finding() -> None:
    """Confirm SOURCE matches an already-frozen rule. Skip if semgrep is absent.

    If this assertion fails, rewrite the fixture to a different existing id in
    python-security.yaml. Do not edit the ruleset.
    """
    semgrep = shutil.which("semgrep")
    if semgrep is None:
        pytest.skip("semgrep binary missing")
    ruleset = ruleset_path()
    completed = subprocess.run(  # noqa: S603 - argv is constructed internally
        [
            semgrep,
            "scan",
            "--config",
            str(ruleset),
            "--json",
            "--metrics",
            "off",
            "--disable-version-check",
            "--quiet",
            str(FIXTURE_ROOT / "source"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert "--config auto" not in " ".join(completed.args)
    stdout = completed.stdout or ""
    assert stdout.strip().startswith("{"), stdout[:200]
    payload = json.loads(stdout)
    check_ids = {str(item.get("check_id") or "") for item in payload.get("results") or []}
    assert SOURCE_RULE in check_ids, (
        f"SOURCE missed {SOURCE_RULE}; pick a different existing frozen rule. "
        f"Do not edit python-security.yaml. Observed={sorted(check_ids)}"
    )
