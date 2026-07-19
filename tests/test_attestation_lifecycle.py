"""V4.1.1 PR3 — dual attestation lifecycle + publish eligibility."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent_control.aci.backends.base import ProbeResult, SandboxAttestation
from agent_control.publish.eligibility import evaluate_publish_eligible
from agent_shared.git_hygiene import hygienic_clone_env, scrub_clone_credentials
from agent_shared.models.attestation import CapabilityTestResult
from agent_workers.executor.lifecycle import (
    EXECUTION_ATTESTATION_FILENAME,
    SANDBOX_ATTESTATION_FILENAME,
    ExecutorLifecycle,
    issue_ct103_nonce,
    resolve_runtime_attestation,
)


def _git_init(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "README.md").write_text("# t\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=dest,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=dest,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=dest,
        check=True,
        capture_output=True,
    )


def test_resolve_runtime_attestation_simulation_fallback(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _git_init(ws)
    att = resolve_runtime_attestation(ws, backend_name="deny", allow_simulation=True)
    assert att.strong_ok
    assert att.backend == "simulation"


def test_lifecycle_durable_bundle_before_teardown(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    ws = tmp_path / "workspace"
    _git_init(ws)
    # Inject a token-looking remote for scrub
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://oauth2:sekret@example.com/org/repo.git",
        ],
        cwd=ws,
        check=True,
        capture_output=True,
    )

    nonce = issue_ct103_nonce()
    life = ExecutorLifecycle(
        run_id="run-attest-1",
        job_id="job-1",
        ct103_nonce=nonce,
        policy_source_repo="org/repo",
        policy_source_sha="abc123",
        target_source_sha="def456",
        command_registry_hash="reg",
        effective_command_policy_hash="eff",
        durable_root=state,
        quarantine_root=state / "quarantine",
    )
    scrub = life.mark_workspace_prepared(ws, scrub=True)
    assert scrub.token_bearing_remote_cleared
    cfg = (ws / ".git" / "config").read_text(encoding="utf-8")
    assert "sekret" not in cfg

    runtime = SandboxAttestation(
        backend="simulation",
        backend_version="sim-1",
        mode="strong",
        policy_hash="ph",
        probes=[ProbeResult(name="canary", passed=True)],
    )
    art = tmp_path / "artifacts"
    life.write_sandbox_attestation(
        art,
        runtime_attestation=runtime,
        capability_tests=[CapabilityTestResult(name="canary", passed=True)],
    )
    assert life.sandbox_attestation is not None
    assert life.sandbox_attestation.ready_verdict == "ready"
    assert (art / SANDBOX_ATTESTATION_FILENAME).is_file()

    life.mark_work_started()
    life.record_command("pytest_narrow")
    patch = b"diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1,2 @@\n # t\n+line\n"
    manifest = life.finalize_durable_bundle(
        state,
        kind="fix",
        attempt_id="1",
        producer_base_sha="def456",
        patch_bytes=patch,
        artifact_dir=art,
    )
    assert life.state == "bundle_finalized"
    assert life.bundle_dir is not None
    assert (life.bundle_dir / SANDBOX_ATTESTATION_FILENAME).is_file()
    assert (life.bundle_dir / "READY").is_file()

    status = life.teardown_workspace()
    assert status == "destroyed"
    assert not ws.exists()

    exec_attest = life.write_execution_attestation(artifact_dir=art)
    assert exec_attest.teardown_status == "destroyed"
    assert exec_attest.ct103_nonce == nonce
    assert (life.bundle_dir / EXECUTION_ATTESTATION_FILENAME).is_file()
    assert (art / EXECUTION_ATTESTATION_FILENAME).is_file()

    elig = evaluate_publish_eligible(
        bundle_dir=life.bundle_dir,
        manifest=manifest,
        expected_nonce=nonce,
        require_attestations=True,
    )
    assert elig.eligible, elig.reason_codes

    # Reload manifest after execution attest update
    man = json.loads((life.bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert man.get("execution_attestation_filename") == EXECUTION_ATTESTATION_FILENAME
    assert man.get("execution_attestation_sha256")


def test_publish_eligibility_denies_quarantined(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    ws = tmp_path / "workspace"
    _git_init(ws)
    # Make teardown fail by replacing workspace with a file after prepare
    nonce = "nonce-q"
    life = ExecutorLifecycle(
        run_id="run-q",
        ct103_nonce=nonce,
        durable_root=state,
        quarantine_root=state / "quarantine",
    )
    life.mark_workspace_prepared(ws, scrub=False)
    runtime = SandboxAttestation(
        backend="simulation",
        backend_version="1",
        mode="strong",
        policy_hash="p",
        probes=[ProbeResult(name="c", passed=True)],
    )
    art = tmp_path / "a"
    life.write_sandbox_attestation(
        art,
        runtime_attestation=runtime,
        capability_tests=[CapabilityTestResult(name="c", passed=True)],
    )
    life.mark_work_started()
    patch = b"diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -0,0 +1 @@\n+x\n"
    # Ensure patch is non-empty and valid enough for inbox
    manifest = life.finalize_durable_bundle(
        state,
        kind="fix",
        attempt_id="1",
        producer_base_sha="base",
        patch_bytes=patch,
        artifact_dir=art,
    )
    # Force quarantine path: remove then recreate as undeletable via monkeypatch
    life.teardown_status = "quarantined"
    life.state = "workspace_quarantined"
    life.quarantine_reason = "forced"
    life.quarantine_location = str(state / "quarantine" / "run-q")
    # Still destroy for cleanliness
    if ws.exists():
        import shutil

        shutil.rmtree(ws, ignore_errors=True)
    life.write_execution_attestation(artifact_dir=art)

    elig = evaluate_publish_eligible(
        bundle_dir=life.bundle_dir,  # type: ignore[arg-type]
        manifest=manifest,
        expected_nonce=nonce,
    )
    assert not elig.eligible
    assert "workspace_quarantined" in elig.reason_codes


def test_publish_eligibility_denies_missing_attestations(tmp_path: Path) -> None:
    from agent_shared.bundles import write_ready_bundle

    state = tmp_path / "state"
    state.mkdir()
    manifest = write_ready_bundle(
        state,
        run_id="run-bare",
        kind="fix",
        attempt_id="1",
        producer_base_sha="base",
        patch_bytes=b"diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -0,0 +1 @@\n+a\n",
    )
    from agent_shared.bundles.inbox import bundle_dir

    root = bundle_dir(
        state,
        run_id="run-bare",
        kind="fix",
        attempt_id="1",
        bundle_id=manifest.bundle_id,
    )
    elig = evaluate_publish_eligible(bundle_dir=root, manifest=manifest)
    assert not elig.eligible
    assert "sandbox_attestation_missing" in elig.reason_codes
    assert "execution_attestation_missing" in elig.reason_codes


def test_hygienic_clone_env_disables_helpers() -> None:
    env = hygienic_clone_env("https://example.com/r.git")
    assert env.get("GIT_CONFIG_NOSYSTEM") == "1"
    assert env.get("GIT_TERMINAL_PROMPT") == "0"
    count = int(env["GIT_CONFIG_COUNT"])
    keys = {env[f"GIT_CONFIG_KEY_{i}"] for i in range(count)}
    assert "core.hooksPath" in keys
    assert "credential.helper" in keys


def test_sandbox_attestation_not_ready_without_nonce(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _git_init(ws)
    life = ExecutorLifecycle(run_id="run-nn", ct103_nonce="")
    life.mark_workspace_prepared(ws, scrub=False)
    runtime = SandboxAttestation(
        backend="simulation",
        backend_version="1",
        mode="strong",
        policy_hash="p",
        probes=[ProbeResult(name="c", passed=True)],
    )
    with pytest.raises(RuntimeError, match="sandbox_attestation_not_ready"):
        life.write_sandbox_attestation(tmp_path / "a", runtime_attestation=runtime)


def test_scrub_clone_credentials_report(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _git_init(ws)
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://user:tok@host/repo.git",
        ],
        cwd=ws,
        check=True,
        capture_output=True,
    )
    report = scrub_clone_credentials(ws)
    assert report.token_bearing_remote_cleared
    assert "remote_url_credentials" in report.categories_removed
    assert "tok" not in (ws / ".git" / "config").read_text(encoding="utf-8")
