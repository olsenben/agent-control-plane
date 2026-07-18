"""CI repair worker — structured patch + SRT verify + non-force push report (6F.2).

Distinct from agent_workers/rlm/repair.py (JSON schema repair).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent_control.ci.events import (
    append_fix_ci_repair_blocked,
    append_fix_ci_repair_pushed,
    append_fix_ci_repair_started,
    append_fix_ci_repair_stale,
)
from agent_control.ci.pending import register_pending_ci
from agent_control.ci.reservation import (
    RepairReservation,
    acquire_repair_lease,
    load_repair_reservation,
    release_repair_lease,
    save_repair_reservation,
)
from agent_shared.models.ci import (
    FixCiRepairBlockedEvent,
    FixCiRepairPushedEvent,
    FixCiRepairStartedEvent,
    FixCiRepairStaleEvent,
    RequiredWorkflow,
)
from agent_workers.sandbox.verify import run_verification_sandbox

logger = logging.getLogger(__name__)


def run_ci_repair_job(job_payload: dict[str, Any]) -> dict[str, Any]:
    """Claim lease, execute repair pipeline, report durable results for CT103."""
    state_root = Path(str(job_payload.get("state_root") or ""))
    repair_key = str(job_payload.get("repair_key") or "")
    if not state_root.is_dir() or not repair_key:
        return {"ok": False, "reason": "invalid_payload"}

    reservation = load_repair_reservation(state_root, repair_key)
    if reservation is None:
        reservation = RepairReservation.from_dict(
            {k: v for k, v in job_payload.items() if k in RepairReservation.__dataclass_fields__}
        )

    # Push-then-crash recovery: already terminal with new SHA → replay pushed
    if reservation.status == "terminal" and reservation.new_head_commit_sha:
        return _replay_pushed(state_root, reservation)

    lease = acquire_repair_lease(
        state_root, repair_key, holder=str(job_payload.get("job_id") or reservation.fix_run_id)
    )
    if lease is None:
        return {"ok": False, "reason": "lease_held"}

    try:
        reservation.status = "claimed"
        save_repair_reservation(state_root, reservation)

        append_fix_ci_repair_started(
            state_root,
            FixCiRepairStartedEvent(
                fix_run_id=reservation.fix_run_id,
                repository=reservation.repository,
                expected_head_commit_sha=reservation.expected_head_commit_sha,
                pr_number=reservation.pr_number,
                repair_attempt=reservation.repair_attempt,
                repair_key=reservation.repair_key,
            ),
        )

        # Head check #1 — remote must still be expected_sha
        remote_head = _fetch_remote_head(reservation)
        if remote_head is None:
            return _block(state_root, reservation, ["api_unavailable"], "agent:blocked")
        if remote_head != reservation.expected_head_commit_sha:
            return _stale(
                state_root,
                reservation,
                reason="remote_head_changed",
                observed=remote_head,
            )

        # Candidate already pushed (reconcile after crash)
        candidate = reservation.new_head_commit_sha
        if candidate and remote_head == candidate:
            return _replay_pushed(state_root, reservation)

        workspace = _prepare_workspace(reservation)
        if workspace is None:
            return _block(state_root, reservation, ["workspace_prepare_failed"], "agent:blocked")

        patch_result = _produce_and_apply_patch(reservation, workspace)
        if not patch_result.get("ok"):
            return _block(
                state_root,
                reservation,
                list(patch_result.get("reason_codes") or ["patch_failed"]),
                str(patch_result.get("label") or "agent:needs-human"),
            )

        if not reservation.required_command_ids:
            return _block(state_root, reservation, ["no_mapped_verifier"], "agent:blocked")

        verify = run_verification_sandbox(
            Path("."),
            workspace,
            list(reservation.required_command_ids),
        )
        if not verify.get("passed"):
            reason = "verification_failed"
            if verify.get("status") == "sandbox_failed":
                reason = "sandbox_attestation_failed"
            return _block(state_root, reservation, [reason], "agent:blocked")

        # Post-verify scope check hook (closed-world re-run)
        scope = _post_verify_scope_check(reservation, workspace)
        if not scope.get("ok"):
            return _block(
                state_root,
                reservation,
                list(scope.get("reason_codes") or ["scope_violation"]),
                "agent:blocked",
            )

        # Head check #2 immediately before push
        remote_head2 = _fetch_remote_head(reservation)
        if remote_head2 != reservation.expected_head_commit_sha:
            return _stale(
                state_root,
                reservation,
                reason="remote_head_changed",
                observed=remote_head2,
            )

        push = _non_force_push(reservation, workspace)
        if not push.get("ok"):
            if push.get("stale"):
                return _stale(
                    state_root,
                    reservation,
                    reason=str(push.get("reason") or "push_rejected"),
                    observed=push.get("observed_head"),
                )
            return _block(
                state_root,
                reservation,
                list(push.get("reason_codes") or ["push_failed"]),
                "agent:blocked",
            )

        new_sha = str(push["new_head_commit_sha"])
        reservation.new_head_commit_sha = new_sha
        reservation.status = "terminal"
        reservation.terminal_reason = "pushed"
        save_repair_reservation(state_root, reservation)

        # Durable report — CT103 also consumes this for pending registration
        append_fix_ci_repair_pushed(
            state_root,
            FixCiRepairPushedEvent(
                fix_run_id=reservation.fix_run_id,
                repository=reservation.repository,
                previous_head_commit_sha=reservation.expected_head_commit_sha,
                new_head_commit_sha=new_sha,
                pr_number=reservation.pr_number,
                repair_attempt=reservation.repair_attempt,
                repair_key=reservation.repair_key,
            ),
        )
        apply_repair_pushed_on_ct103(state_root, reservation, new_sha)
        return {"ok": True, "new_head_commit_sha": new_sha}
    finally:
        release_repair_lease(lease)


def apply_repair_pushed_on_ct103(
    state_root: Path,
    reservation: RepairReservation,
    new_sha: str,
) -> None:
    """Idempotent: register new 6E pending and supersede old SHA (CT103 authority)."""
    register_pending_ci(
        state_root,
        fix_run_id=reservation.fix_run_id,
        repository=reservation.repository,
        expected_head_commit_sha=new_sha,
        opened_pr_number=reservation.pr_number,
        issue_id=reservation.issue_id,
        agent_branch=reservation.agent_branch,
        required_workflows=[RequiredWorkflow(path=".gitea/workflows/ci.yaml", source="repo_default")],
        artifact_root=reservation.artifact_root,
    )


def _replay_pushed(state_root: Path, reservation: RepairReservation) -> dict[str, Any]:
    new_sha = reservation.new_head_commit_sha or ""
    if not new_sha:
        return {"ok": False, "reason": "missing_new_sha"}
    append_fix_ci_repair_pushed(
        state_root,
        FixCiRepairPushedEvent(
            fix_run_id=reservation.fix_run_id,
            repository=reservation.repository,
            previous_head_commit_sha=reservation.expected_head_commit_sha,
            new_head_commit_sha=new_sha,
            pr_number=reservation.pr_number,
            repair_attempt=reservation.repair_attempt,
            repair_key=reservation.repair_key,
        ),
    )
    apply_repair_pushed_on_ct103(state_root, reservation, new_sha)
    return {"ok": True, "replayed": True, "new_head_commit_sha": new_sha}


def _block(
    state_root: Path,
    reservation: RepairReservation,
    reasons: list[str],
    label: str,
) -> dict[str, Any]:
    reservation.status = "terminal"
    reservation.terminal_reason = reasons[0] if reasons else "blocked"
    save_repair_reservation(state_root, reservation)
    append_fix_ci_repair_blocked(
        state_root,
        FixCiRepairBlockedEvent(
            fix_run_id=reservation.fix_run_id,
            repository=reservation.repository,
            expected_head_commit_sha=reservation.expected_head_commit_sha,
            pr_number=reservation.pr_number,
            reason_codes=reasons,
            label=label,
        ),
    )
    return {"ok": False, "blocked": True, "reason_codes": reasons}


def _stale(
    state_root: Path,
    reservation: RepairReservation,
    *,
    reason: str,
    observed: str | None,
) -> dict[str, Any]:
    reservation.status = "terminal"
    reservation.terminal_reason = reason
    save_repair_reservation(state_root, reservation)
    append_fix_ci_repair_stale(
        state_root,
        FixCiRepairStaleEvent(
            fix_run_id=reservation.fix_run_id,
            repository=reservation.repository,
            expected_head_commit_sha=reservation.expected_head_commit_sha,
            pr_number=reservation.pr_number,
            repair_attempt=reservation.repair_attempt,
            repair_key=reservation.repair_key,
            reason=reason,
            observed_head_commit_sha=observed,
        ),
    )
    return {"ok": False, "stale": True, "reason": reason}


def _fetch_remote_head(reservation: RepairReservation) -> str | None:
    """Fetch current branch head from Gitea. Returns None on API failure."""
    try:
        from agent_control.config import get_settings
        from agent_control.gitea_client import GiteaClient
        from agent_shared.repo_identity import split_repo_full_name

        settings = get_settings()
        owner, repo = split_repo_full_name(reservation.repository)
        client = GiteaClient(settings)
        branch = reservation.agent_branch
        if not branch:
            return None
        sha = client.get_branch_sha(owner, repo, branch)
        return sha or None
    except Exception:
        logger.exception("repair_fetch_remote_head_failed key=%s", reservation.repair_key)
        return None


def _prepare_workspace(reservation: RepairReservation) -> Path | None:
    """Clone agent branch at expected_sha into a disposable repair workspace."""
    from agent_workers.repo.policy_loader import clone_repo
    from agent_workers.settings import get_worker_settings

    settings = get_worker_settings()
    root = (
        Path(reservation.artifact_root or settings.agent_runs_dir)
        / "repair-workspaces"
        / reservation.repair_key.replace(":", "_").replace("/", "_")
    )
    if root.exists():
        import shutil

        shutil.rmtree(root)

    owner, repo = reservation.repository.split("/", 1)
    base = settings.gitea_base_url.rstrip("/")
    repo_url = f"{base}/{owner}/{repo}.git"
    try:
        clone_repo(settings, repo_url, reservation.agent_branch, root)
    except Exception:
        logger.exception("repair_clone_failed key=%s", reservation.repair_key)
        return None

    from agent_workers.publish.remote import _git_run

    checkout = _git_run(root, ["git", "checkout", "--force", reservation.expected_head_commit_sha])
    if checkout.returncode != 0:
        # Shallow clone may lack the SHA if tip moved between checks
        logger.error(
            "repair_checkout_expected_sha_failed key=%s err=%s",
            reservation.repair_key,
            checkout.stderr,
        )
        return None
    head = _git_run(root, ["git", "rev-parse", "HEAD"])
    if head.stdout.strip() != reservation.expected_head_commit_sha:
        return None
    return root


def _produce_and_apply_patch(reservation: RepairReservation, workspace: Path) -> dict[str, Any]:
    """Apply structured repair_patch.diff within allowed_files and commit locally."""
    from agent_workers.gates.runner import collect_changed_files
    from agent_workers.publish.remote import _git_run, _stage_allowed_files

    if not reservation.allowed_files:
        return {
            "ok": False,
            "reason_codes": ["scope_violation", "empty_allowed_files"],
            "label": "agent:needs-human",
        }

    injected = Path(reservation.artifact_root or ".") / "repair_patch.diff"
    if not injected.is_file():
        injected = workspace / "repair_patch.diff"
    if not injected.is_file():
        generated = _generate_intentional_fail_removal_patch(workspace, reservation.allowed_files)
        if generated is None:
            return {
                "ok": False,
                "reason_codes": ["repair_proposal_unavailable"],
                "label": "agent:needs-human",
            }
        injected = generated

    apply = _git_run(workspace, ["git", "apply", "--whitespace=nowarn", str(injected)])
    if apply.returncode != 0:
        return {
            "ok": False,
            "reason_codes": ["patch_apply_failed"],
            "label": "agent:blocked",
            "detail": apply.stderr,
        }

    changed = collect_changed_files(workspace)
    allowed = set(reservation.allowed_files)
    # Ignore ephemeral patch artifact if it landed inside the worktree
    ignore = {"repair_patch.diff"}
    extra = [p for p in changed if p not in allowed and Path(p).name not in ignore]
    if extra:
        return {
            "ok": False,
            "reason_codes": ["scope_violation"],
            "label": "agent:blocked",
            "detail": f"out_of_scope:{extra}",
        }

    try:
        _stage_allowed_files(workspace, list(reservation.allowed_files))
    except Exception as exc:
        return {
            "ok": False,
            "reason_codes": ["stage_failed"],
            "label": "agent:blocked",
            "detail": str(exc),
        }

    msg = (
        f"fix(ci-repair): attempt {reservation.repair_attempt} "
        f"for {reservation.expected_head_commit_sha[:12]}"
    )
    commit = _git_run(
        workspace,
        ["git", "-c", "user.email=agent-bot@local", "-c", "user.name=agent-bot", "commit", "-m", msg],
    )
    if commit.returncode != 0:
        return {
            "ok": False,
            "reason_codes": ["commit_failed"],
            "label": "agent:blocked",
            "detail": commit.stderr,
        }
    return {"ok": True, "source": "injected_or_generated_patch"}


def _generate_intentional_fail_removal_patch(
    workspace: Path, allowed_files: list[str]
) -> Path | None:
    """Demo heuristic: remove intentional-fail test stubs from allowed test files."""
    import re

    from agent_workers.publish.remote import _git_run

    edited = False
    # Match annotated signatures: def name() -> None:
    pattern = re.compile(
        r"(?m)^def (test_6f2_intentional_fail|test_6f1_intentional_fail)\([^)]*\)"
        r"(?:\s*->\s*[^:\n]+)?:.*?(?=^def |\Z)",
        re.DOTALL,
    )
    for rel in allowed_files:
        if not rel.startswith("tests/") or not rel.endswith(".py"):
            continue
        path = workspace / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        new_text, n = pattern.subn("", text)
        if n:
            # Collapse leftover blank runs from removed defs
            new_text = re.sub(r"\n{3,}", "\n\n", new_text).rstrip() + "\n"
            path.write_text(new_text, encoding="utf-8")
            edited = True

    if not edited:
        return None
    diff = _git_run(workspace, ["git", "diff", "--", *allowed_files])
    if diff.returncode != 0 or not diff.stdout.strip():
        return None
    # Keep patch outside the git worktree so it is not an untracked scope violation
    out = workspace.parent / "repair_patch.diff"
    out.write_text(diff.stdout, encoding="utf-8")
    # Reset working tree so git apply can re-apply cleanly
    _git_run(workspace, ["git", "checkout", "--", *allowed_files])
    return out


def _post_verify_scope_check(reservation: RepairReservation, workspace: Path) -> dict[str, Any]:
    """Ensure post-verify tree stays within allowed_files when a allowlist is set."""
    from agent_workers.gates.runner import collect_changed_files

    if not reservation.allowed_files:
        return {"ok": True}
    # Compare against expected tip: only allowlist paths may differ from HEAD~1
    # After commit, working tree should be clean; dirty out-of-scope files fail.
    changed = collect_changed_files(workspace)
    allowed = set(reservation.allowed_files)
    extra = [p for p in changed if p not in allowed]
    if extra:
        return {"ok": False, "reason_codes": ["scope_violation"], "detail": str(extra)}
    return {"ok": True}


def _non_force_push(reservation: RepairReservation, workspace: Path) -> dict[str, Any]:
    """Non-force fast-forward push onto the existing agent branch (outside SRT)."""
    from agent_workers.publish.remote import push_repair_fast_forward
    from agent_workers.settings import get_worker_settings

    settings = get_worker_settings()
    if not settings.fix_remote_publish_enabled:
        return {"ok": False, "reason_codes": ["publish_disabled"]}

    owner, repo = reservation.repository.split("/", 1)
    repo_url = f"{settings.gitea_base_url.rstrip('/')}/{owner}/{repo}.git"
    result = push_repair_fast_forward(
        repo_workspace=workspace,
        agent_branch=reservation.agent_branch,
        expected_remote_sha=reservation.expected_head_commit_sha,
        repository=reservation.repository,
        repo_url=repo_url,
        settings=settings,
    )
    if result.get("ok"):
        return {
            "ok": True,
            "new_head_commit_sha": result.get("new_head_commit_sha"),
        }
    if result.get("stale"):
        return {
            "ok": False,
            "stale": True,
            "reason": result.get("reason") or "push_rejected",
            "observed_head": result.get("observed_head"),
        }
    return {
        "ok": False,
        "reason_codes": list(result.get("reason_codes") or ["push_failed"]),
        "detail": result.get("detail"),
    }
