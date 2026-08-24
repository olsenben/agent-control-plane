"""CT104 worker patch_proposal.v1: sealed in READY bundle, immutable after finalize."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from agent_control.transaction.proposal import ProposalImmutableError, finalize_proposal
from agent_shared.bundles.inbox import (
    PATCH_PROPOSAL_FILENAME,
    BundleError,
    load_ready_bundle,
    write_ready_bundle,
)
from agent_shared.models.transaction.proposal import PatchProposal
from agent_workers.jobs.report import process_report
from agent_workers.transaction.proposal import (
    WorkerProposalContext,
    WorkerProposalError,
    build_finalized_worker_proposal,
    build_patch_proposal,
    new_proposal_for_patch,
    proposal_json_bytes,
    refuse_mutate_finalized,
    sha256_bytes,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent_shared"
    / "schemas"
    / "patch_proposal.v1.json"
)
PROPOSAL_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
PATCH_A = b"diff --git a/src/pkg/core.py b/src/pkg/core.py\n--- a/src/pkg/core.py\n+++ b/src/pkg/core.py\n@@ -1 +1,2 @@\n x\n+y\n"
PATCH_B = b"diff --git a/src/pkg/core.py b/src/pkg/core.py\nnew file mode 100644\n--- /dev/null\n+++ b/src/pkg/core.py\n@@ -0,0 +1 @@\n+hello\n"


def _context(**updates: object) -> WorkerProposalContext:
    body: dict[str, object] = {
        "session_id": "sess-worker-1",
        "repo": "org/demo",
        "task_id": "task-1",
        "tenant_id": "org",
        "org_id": "org",
        "human_initiator_id": "alice",
        "changed_symbols": ["pkg.core.fix"],
    }
    body.update(updates)
    return WorkerProposalContext(**body)  # type: ignore[arg-type]


def _write_bundle(tmp_path: Path, patch: bytes, *, bundle_id: str = "bundle1", **kwargs: object):
    proposal = build_finalized_worker_proposal(
        context=_context(),
        source_sha="abc1234def",
        patch_bytes=patch,
        source_tree="treesha40notdigest",
        finalized_at="2026-08-24T01:00:00+00:00",
    )
    manifest = write_ready_bundle(
        tmp_path,
        run_id="run-prop",
        kind="fix",
        attempt_id="1",
        bundle_id=bundle_id,
        producer_base_sha="abc1234def",
        patch_bytes=patch,
        producer_tree_sha="treesha40notdigest",
        proposal_payload=proposal_json_bytes(proposal),
        **kwargs,
    )
    return manifest, proposal


def test_ready_bundle_includes_schema_fields(tmp_path: Path) -> None:
    manifest, proposal = _write_bundle(tmp_path, PATCH_A)
    loaded, root = load_ready_bundle(
        tmp_path,
        run_id="run-prop",
        kind="fix",
        attempt_id="1",
        bundle_id=manifest.bundle_id,
    )
    path = root / PATCH_PROPOSAL_FILENAME
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(PROPOSAL_SCHEMA).validate(payload)
    sealed = PatchProposal.model_validate(payload)
    assert sealed.schema_version == "patch_proposal.v1"
    assert sealed.session_id == "sess-worker-1"
    assert sealed.repo == "org/demo"
    assert sealed.task_id == "task-1"
    assert sealed.source_sha == "abc1234def"
    assert len(sealed.source_tree_digest) == 64
    assert sealed.patch_digest == sha256_bytes(PATCH_A)
    assert "src/pkg/core.py" in sealed.changed_files
    assert sealed.changed_symbols == ["pkg.core.fix"]
    assert sealed.created_units == []
    assert sealed.deleted_units == []
    assert sealed.actor_identity.principal_kind == "AGENT_WORKER"
    assert sealed.worker_identity.principal_kind == "AGENT_WORKER"
    assert sealed.identity is not None
    assert sealed.identity.EXECUTED_BY.principal_kind == "AGENT_WORKER"
    assert sealed.identity.ON_BEHALF_OF.principal_kind == "HUMAN_INITIATOR"
    assert sealed.created_at
    assert sealed.finalized_at
    assert sealed.raw_patch_location == "patch.diff"
    assert sealed.raw_patch_digest == loaded.patch_sha256
    assert sealed.finalized is True
    assert sealed.immutable_after_finalize is True
    assert proposal.patch_digest == sealed.patch_digest


def test_finalize_then_mutate_raises() -> None:
    sealed = build_finalized_worker_proposal(
        context=_context(),
        source_sha="abc1234",
        patch_bytes=PATCH_A,
        finalized_at="2026-08-24T01:00:00+00:00",
    )
    assert sealed.finalized is True
    with pytest.raises(ProposalImmutableError):
        refuse_mutate_finalized(sealed, notes="tamper")
    with pytest.raises(ProposalImmutableError):
        refuse_mutate_finalized(sealed, patch_digest="d" * 64)


def test_new_patch_is_new_proposal_id_and_digest() -> None:
    first = build_finalized_worker_proposal(
        context=_context(),
        source_sha="abc1234",
        patch_bytes=PATCH_A,
        finalized_at="2026-08-24T01:00:00+00:00",
    )
    original_id = first.proposal_id
    original_digest = first.patch_digest
    second = new_proposal_for_patch(
        first,
        patch_bytes=PATCH_B,
        finalized_at="2026-08-24T02:00:00+00:00",
    )
    assert first.proposal_id == original_id
    assert first.patch_digest == original_digest
    assert first.finalized is True
    assert second.proposal_id != first.proposal_id
    assert second.patch_digest != first.patch_digest
    assert second.patch_digest == sha256_bytes(PATCH_B)
    assert second.finalized is True
    assert "src/pkg/core.py" in second.created_units


def test_actor_is_worker_not_human_impersonation() -> None:
    sealed = build_finalized_worker_proposal(
        context=_context(human_initiator_id="alice"),
        source_sha="abc1234",
        patch_bytes=PATCH_A,
    )
    assert sealed.actor_identity.principal_kind == "AGENT_WORKER"
    assert sealed.actor_identity.identity_id != "alice"
    assert sealed.identity is not None
    assert sealed.identity.EXECUTED_BY.principal_kind == "AGENT_WORKER"
    assert sealed.identity.EXECUTED_BY.identity_id != "alice"
    assert sealed.identity.ON_BEHALF_OF.identity_id == "alice"
    assert sealed.identity.ON_BEHALF_OF.principal_kind == "HUMAN_INITIATOR"


def test_ready_bundle_rejects_rewrite_same_id(tmp_path: Path) -> None:
    _write_bundle(tmp_path, PATCH_A, bundle_id="fixedid")
    with pytest.raises(BundleError, match="already exists"):
        _write_bundle(tmp_path, PATCH_B, bundle_id="fixedid")


def test_unfinalized_proposal_rejected_from_ready_bundle(tmp_path: Path) -> None:
    draft = build_patch_proposal(
        session_id="sess-worker-1",
        repo="org/demo",
        task_id="task-1",
        source_sha="abc1234",
        patch_bytes=PATCH_A,
        raw_patch_location="patch.diff",
        tenant_id="org",
        org_id="org",
    )
    assert draft.finalized is False
    with pytest.raises(BundleError, match="finalized"):
        write_ready_bundle(
            tmp_path,
            run_id="run-open",
            kind="fix",
            attempt_id="1",
            producer_base_sha="abc1234",
            patch_bytes=PATCH_A,
            proposal_payload=proposal_json_bytes(draft),
        )


def test_durable_credentials_fail_closed() -> None:
    with pytest.raises(WorkerProposalError, match="fail-closed"):
        build_patch_proposal(
            session_id="s",
            repo="org/demo",
            task_id="t",
            source_sha="abc1234",
            patch_bytes=PATCH_A,
            raw_patch_location="patch.diff",
            env={"GITEA_BOT_TOKEN": "secret"},
        )


def test_report_copies_proposal_sidecar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    manifest, proposal = _write_bundle(state, PATCH_A, bundle_id="rep1")
    run_path = tmp_path / "runs" / "run-prop"
    run_path.mkdir(parents=True)
    (run_path / "metadata.json").write_text('{"status": "completed"}', encoding="utf-8")
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    reported = process_report(
        {
            "run_id": "run-prop",
            "project": "org/demo",
            "artifact_root": str(run_path),
            "job": {"flow": "developer", "agent": "fixer", "trigger_context": {}},
            "result": {
                "summary": "ok",
                "flow": "developer",
                "agent": "fixer",
                "status": "completed",
                "risk_class": "low",
                "bundle_id": manifest.bundle_id,
                "attempt_id": "1",
                "bundle_kind": "fix",
            },
        }
    )
    sidecar = run_path / PATCH_PROPOSAL_FILENAME
    assert sidecar.is_file()
    copied = json.loads(sidecar.read_text(encoding="utf-8"))
    assert copied["proposal_id"] == proposal.proposal_id
    assert reported["proposal_id"] == proposal.proposal_id
    report_text = (run_path / "final_report.md").read_text(encoding="utf-8")
    assert "patch_proposal" in report_text
    inbox_proposal = (
        state / "bundle-inbox" / "run-prop" / "fix" / "1" / manifest.bundle_id / PATCH_PROPOSAL_FILENAME
    )
    assert json.loads(inbox_proposal.read_text(encoding="utf-8"))["patch_digest"] == proposal.patch_digest


def test_finalize_is_idempotent() -> None:
    draft = build_patch_proposal(
        session_id="sess-worker-1",
        repo="org/demo",
        task_id="task-1",
        source_sha="abc1234",
        patch_bytes=PATCH_A,
        raw_patch_location="patch.diff",
        tenant_id="org",
        org_id="org",
    )
    first = finalize_proposal(draft, finalized_at="2026-08-24T01:00:00+00:00")
    second = finalize_proposal(first, finalized_at="2026-08-24T09:00:00+00:00")
    assert first.finalized_at == second.finalized_at
    assert first.patch_digest == second.patch_digest


def test_lifecycle_ready_bundle_contains_proposal(tmp_path: Path) -> None:
    from agent_control.aci.backends.base import ProbeResult, SandboxAttestation
    from agent_shared.models.attestation import CapabilityTestResult
    from agent_workers.executor.lifecycle import ExecutorLifecycle, issue_ct103_nonce

    state = tmp_path / "state"
    state.mkdir()
    life = ExecutorLifecycle(
        run_id="run-prop-life",
        job_id="job-1",
        ct103_nonce=issue_ct103_nonce(),
        policy_source_repo="org/demo",
        target_source_sha="abc1234",
        durable_root=state,
    )
    runtime = SandboxAttestation(
        backend="simulation",
        backend_version="1",
        mode="strong",
        policy_hash="p",
        probes=[ProbeResult(name="c", passed=True)],
    )
    art = tmp_path / "artifacts"
    life.write_sandbox_attestation(
        art,
        runtime_attestation=runtime,
        capability_tests=[CapabilityTestResult(name="c", passed=True)],
    )
    life.mark_work_started()
    manifest = life.finalize_durable_bundle(
        state,
        kind="fix",
        attempt_id="1",
        producer_base_sha="abc1234",
        patch_bytes=PATCH_A,
        artifact_dir=art,
        session_id="sess-1",
        repo="org/demo",
        task_id="job-1",
        human_initiator_id="alice",
    )
    assert life.patch_proposal is not None
    assert life.patch_proposal.finalized is True
    assert life.patch_proposal.actor_identity.principal_kind == "AGENT_WORKER"
    assert life.bundle_dir is not None
    payload = json.loads((life.bundle_dir / PATCH_PROPOSAL_FILENAME).read_text(encoding="utf-8"))
    Draft202012Validator(PROPOSAL_SCHEMA).validate(payload)
    assert payload["session_id"] == "sess-1"
    assert payload["patch_digest"] == manifest.patch_sha256
    assert (art / PATCH_PROPOSAL_FILENAME).is_file()
