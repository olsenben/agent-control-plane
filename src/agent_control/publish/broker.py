"""CT103 publish broker orchestration (fix + repair)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent_control.approval.service import (
    claim_approval_for_publish,
    consume_approval_on_pr_open,
    release_approval_claim,
)
from agent_control.approval.storage import load_approval
from agent_control.ci.pending import register_pending_ci
from agent_control.config import Settings, get_settings
from agent_control.gitea_client import GiteaClient
from agent_control.gitea_comments import post_issue_comment
from agent_control.publish.remote import (
    RemoteMutationError,
    build_commit_message,
    build_pr_body,
    open_or_find_pr,
    push_commit,
    push_repair_fast_forward,
)
from agent_control.publish.state import (
    cas_transition,
    load_publish_record,
    save_publish_intent,
    save_publish_record,
)
from agent_control.publish.validate import ValidationError, validate_and_commit
from agent_shared.bundles.inbox import BundleError, copy_bundle_to_snapshot, load_ready_bundle
from agent_shared.models.approval import FixAuthorizationBinding
from agent_shared.models.bundle import AuthoritativePublishResult
from agent_shared.models.fix import FixResult
from agent_shared.models.publish import PublishIntent
from agent_shared.project_ids import split_project


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_auth_result(state_root: Path, result: AuthoritativePublishResult) -> Path:
    path = (
        state_root
        / "publish-results"
        / result.run_id
        / result.bundle_id
        / "remote_publish_result.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def _load_binding_from_approval(approval) -> FixAuthorizationBinding:
    return FixAuthorizationBinding(
        approval_id=approval.approval_id,
        approval_target_id=approval.approval_target_id,
        plan_run_id=approval.plan_run_id,
        plan_hash=approval.plan_hash,
        blast_radius_hash=approval.blast_radius_hash,
        allowed_files=list(approval.allowed_files),
        approved_base_sha=approval.approved_base_sha,
        approved_base_ref=approval.approved_base_ref,
    )


def broker_publish_fix(
    *,
    state_root: Path,
    run_id: str,
    attempt_id: str,
    bundle_id: str,
    settings: Settings | None = None,
) -> dict:
    """Validate snapshot, claim approval, CI intent, push, open PR, consume."""
    settings = settings or get_settings()
    record = load_publish_record(state_root, run_id, bundle_id)
    if record and record.publish_state == "succeeded":
        return {"ok": True, "idempotent": True, "publish_state": "succeeded"}

    cas_transition(
        state_root,
        run_id=run_id,
        kind="fix",
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="queued",
        to_state="validating",
    )

    try:
        manifest, _ = load_ready_bundle(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
        )
        snapshot = copy_bundle_to_snapshot(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
        )
    except BundleError as exc:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[str(exc)],
        )
        return {"ok": False, "reason": "bundle_invalid", "detail": str(exc)}

    project = record.project if record else None
    approval_target_id = record.approval_target_id if record else None
    if not project or not approval_target_id:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_terminal",
            messages=["missing project/approval on publish record"],
        )
        return {"ok": False, "reason": "missing_binding"}

    approval = load_approval(state_root, project, approval_target_id)
    if approval is None:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_terminal",
            messages=["approval not found"],
        )
        return {"ok": False, "reason": "approval_missing"}

    if approval.status in ("rejected", "expired", "consumed"):
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_terminal",
            messages=[f"approval status {approval.status}"],
        )
        return {"ok": False, "reason": "approval_unavailable"}

    trusted_sha = approval.approved_base_sha
    if not trusted_sha:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_terminal",
            messages=["no approved_base_sha"],
        )
        return {"ok": False, "reason": "no_trusted_sha"}

    binding = _load_binding_from_approval(approval)
    # Resolve repo URL from CT103 config + project — never from worker
    owner, repo = split_project(project)
    repo_url = f"{settings.gitea_base_url.rstrip('/')}/{owner}/{repo}.git"
    agent_branch = f"agent/{run_id}"
    base_ref = approval.approved_base_ref or "main"

    commit_msg = build_commit_message(
        run_id=run_id,
        binding=binding,
        approved_base_sha=trusted_sha,
    )

    try:
        validated = validate_and_commit(
            settings=settings,
            snapshot_dir=snapshot,
            manifest=manifest,
            binding=binding,
            repo_url=repo_url,
            trusted_base_sha=trusted_sha,
            commit_message=commit_msg,
        )
    except ValidationError as exc:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[f"{exc.reason}: {exc}"],
        )
        return {"ok": False, "reason": exc.reason, "detail": str(exc)}

    job_key = f"{run_id}:{bundle_id}"
    claimed = claim_approval_for_publish(
        state_root,
        approval,
        publish_job_id=job_key,
    )
    if claimed is None:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_retryable",
            messages=["approval claim failed"],
        )
        return {"ok": False, "reason": "claim_failed"}

    intent = PublishIntent(
        run_id=run_id,
        bundle_id=bundle_id,
        kind="fix",
        project=project,
        agent_branch=agent_branch,
        expected_commit_sha=validated.commit_sha,
        created_at=_now(),
    )
    save_publish_intent(state_root, intent)

    # Pending-CI intent before push (PR number may be filled later)
    register_pending_ci(
        state_root,
        fix_run_id=run_id,
        repository=project,
        expected_head_commit_sha=validated.commit_sha,
        opened_pr_number=None,
        issue_id=approval.issue_id,
        agent_branch=agent_branch,
    )

    cas_transition(
        state_root,
        run_id=run_id,
        kind="fix",
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="validating",
        to_state="remote_pending",
        expected_commit_sha=validated.commit_sha,
        trusted_base_sha=trusted_sha,
        patch_sha256=validated.patch_sha256,
        result_tree_sha=validated.result_tree_sha,
        agent_branch=agent_branch,
    )

    client = GiteaClient(settings)
    try:
        # Verify remote base unchanged
        tip = client.get_branch_sha(owner, repo, base_ref)
        if tip != trusted_sha:
            release_approval_claim(state_root, claimed)
            cas_transition(
                state_root,
                run_id=run_id,
                kind="fix",
                attempt_id=attempt_id,
                bundle_id=bundle_id,
                from_state="remote_pending",
                to_state="failed_terminal",
                messages=["remote base advanced"],
            )
            return {"ok": False, "reason": "stale_base"}

        push_commit(
            workspace=validated.workspace,
            commit_sha=validated.commit_sha,
            agent_branch=agent_branch,
            base_ref=base_ref,
            repo_url=repo_url,
            settings=settings,
        )
    except RemoteMutationError as exc:
        release_approval_claim(state_root, claimed)
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="remote_pending",
            to_state="failed_retryable" if not exc.stale else "failed_terminal",
            messages=[str(exc)],
        )
        return {"ok": False, "reason": exc.stage, "detail": str(exc), "stale": exc.stale}
    except Exception as exc:
        release_approval_claim(state_root, claimed)
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="remote_pending",
            to_state="failed_retryable",
            messages=[str(exc)],
        )
        return {"ok": False, "reason": "push_failed", "detail": str(exc)}

    # Load fix_result from snapshot for PR body if present
    fix_result = FixResult(files_changed=list(binding.allowed_files))
    result_file = snapshot / "fix_result.json"
    if result_file.is_file():
        try:
            fix_result = FixResult.model_validate(json.loads(result_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    pr_body = build_pr_body(
        run_id=run_id,
        issue_number=approval.issue_id,
        binding=binding,
        fix_result=fix_result,
        approved_base_sha=trusted_sha,
        ci_hints=list(binding.ci_hints) if hasattr(binding, "ci_hints") else None,
    )
    # Idempotency marker
    pr_body = pr_body + f"\n\n<!-- agent-run-id:{run_id} bundle-id:{bundle_id} -->\n"
    title = f"agent(fix): {binding.approval_target_id}"

    try:
        pr_number, pr_url, _reused = open_or_find_pr(
            client=client,
            owner=owner,
            repo=repo,
            agent_branch=agent_branch,
            base_ref=base_ref,
            title=title,
            body=pr_body,
        )
    except RemoteMutationError as exc:
        # Push succeeded — partial recovery path
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="remote_pending",
            to_state="failed_retryable",
            commit_sha=validated.commit_sha,
            messages=[f"pr_open: {exc}"],
        )
        return {
            "ok": False,
            "reason": "pr_open",
            "commit_sha": validated.commit_sha,
            "detail": str(exc),
        }

    # Update pending CI with PR number
    register_pending_ci(
        state_root,
        fix_run_id=run_id,
        repository=project,
        expected_head_commit_sha=validated.commit_sha,
        opened_pr_number=pr_number,
        issue_id=approval.issue_id,
        agent_branch=agent_branch,
    )

    consume_approval_on_pr_open(
        state_root,
        claimed,
        fix_run_id=run_id,
        consumed_event_id=f"publish-{bundle_id}",
    )

    auth = AuthoritativePublishResult(
        run_id=run_id,
        bundle_id=bundle_id,
        attempt_id=attempt_id,
        kind="fix",
        trusted_base_sha=trusted_sha,
        patch_sha256=validated.patch_sha256,
        result_tree_sha=validated.result_tree_sha,
        commit_sha=validated.commit_sha,
        remote_branch=agent_branch,
        pr_number=pr_number,
        pr_url=pr_url,
        approval_binding_id=binding.approval_id,
        published_at=_now(),
        publish_state="succeeded",
    )
    _write_auth_result(state_root, auth)

    cas_transition(
        state_root,
        run_id=run_id,
        kind="fix",
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="remote_pending",
        to_state="succeeded",
        commit_sha=validated.commit_sha,
        pr_number=pr_number,
        pr_url=pr_url,
    )

    try:
        post_issue_comment(
            project,
            approval.issue_id,
            (
                f"## Publish complete\n\n"
                f"Independent CT103 validation passed.\n\n"
                f"- Branch: `{agent_branch}`\n"
                f"- Commit: `{validated.commit_sha}`\n"
                f"- PR: #{pr_number}\n"
                f"- Bundle: `{bundle_id}`\n"
            ),
            settings=settings,
        )
    except Exception:
        # Comment failure must not mark publication failed
        pass

    return {
        "ok": True,
        "publish_state": "succeeded",
        "commit_sha": validated.commit_sha,
        "pr_number": pr_number,
        "pr_url": pr_url,
    }


def broker_publish_repair(
    *,
    state_root: Path,
    run_id: str,
    attempt_id: str,
    bundle_id: str,
    expected_head_commit_sha: str,
    agent_branch: str,
    project: str,
    allowed_files: list[str],
    repo_url: str | None = None,
    settings: Settings | None = None,
) -> dict:
    """Repair brokerage: validate against trusted expected SHA; non-force FF push."""
    settings = settings or get_settings()
    record = load_publish_record(state_root, run_id, bundle_id)
    if record and record.publish_state == "succeeded":
        return {"ok": True, "idempotent": True}

    try:
        manifest, _ = load_ready_bundle(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
        )
        snapshot = copy_bundle_to_snapshot(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
        )
    except BundleError as exc:
        return {"ok": False, "reason": "bundle_invalid", "detail": str(exc)}

    if manifest.producer_base_sha != expected_head_commit_sha:
        return {
            "ok": False,
            "reason": "base_sha_mismatch",
            "detail": "producer_base_sha != trusted expected head",
        }

    owner, repo = split_project(project)
    url = repo_url or f"{settings.gitea_base_url.rstrip('/')}/{owner}/{repo}.git"

    # Synthetic binding for gate scope
    binding = FixAuthorizationBinding(
        approval_id="repair",
        approval_target_id="repair",
        plan_run_id=run_id,
        plan_hash="repair",
        blast_radius_hash="repair",
        allowed_files=list(allowed_files),
        approved_base_sha=expected_head_commit_sha,
    )

    try:
        validated = validate_and_commit(
            settings=settings,
            snapshot_dir=snapshot,
            manifest=manifest,
            binding=binding,
            repo_url=url,
            trusted_base_sha=expected_head_commit_sha,
            commit_message=f"agent(repair): {run_id} ({bundle_id})",
        )
    except ValidationError as exc:
        return {"ok": False, "reason": exc.reason, "detail": str(exc)}

    # Supersede intent before push
    intent = PublishIntent(
        run_id=run_id,
        bundle_id=bundle_id,
        kind="repair",
        project=project,
        agent_branch=agent_branch,
        expected_commit_sha=validated.commit_sha,
        created_at=_now(),
    )
    save_publish_intent(state_root, intent)
    register_pending_ci(
        state_root,
        fix_run_id=run_id,
        repository=project,
        expected_head_commit_sha=validated.commit_sha,
        agent_branch=agent_branch,
    )

    push = push_repair_fast_forward(
        workspace=validated.workspace,
        commit_sha=validated.commit_sha,
        agent_branch=agent_branch,
        expected_remote_sha=expected_head_commit_sha,
        repository=project,
        repo_url=url,
        settings=settings,
    )
    if not push.get("ok"):
        return {
            "ok": False,
            "stale": bool(push.get("stale")),
            "reason": push.get("reason") or "push_failed",
            "detail": push,
        }

    # Durable repair-pushed + pending supersede (CT103 authority)
    from agent_control.ci.events import append_fix_ci_repair_pushed
    from agent_shared.models.ci import FixCiRepairPushedEvent, RequiredWorkflow

    append_fix_ci_repair_pushed(
        state_root,
        FixCiRepairPushedEvent(
            fix_run_id=run_id,
            repository=project,
            previous_head_commit_sha=expected_head_commit_sha,
            new_head_commit_sha=validated.commit_sha,
            pr_number=None,
            repair_attempt=int(attempt_id) if str(attempt_id).isdigit() else 1,
            repair_key=f"{project}:{run_id}:{attempt_id}",
        ),
    )
    register_pending_ci(
        state_root,
        fix_run_id=run_id,
        repository=project,
        expected_head_commit_sha=validated.commit_sha,
        agent_branch=agent_branch,
        required_workflows=[
            RequiredWorkflow(path=".gitea/workflows/ci.yaml", source="repo_default")
        ],
    )

    auth = AuthoritativePublishResult(
        run_id=run_id,
        bundle_id=bundle_id,
        attempt_id=attempt_id,
        kind="repair",
        trusted_base_sha=expected_head_commit_sha,
        patch_sha256=validated.patch_sha256,
        result_tree_sha=validated.result_tree_sha,
        commit_sha=validated.commit_sha,
        remote_branch=agent_branch,
        published_at=_now(),
        publish_state="succeeded",
    )
    _write_auth_result(state_root, auth)
    if record:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state=record.publish_state,  # type: ignore[arg-type]
            to_state="succeeded",
            commit_sha=validated.commit_sha,
        )
    else:
        from agent_shared.models.publish import PublishRecord

        save_publish_record(
            state_root,
            PublishRecord(
                run_id=run_id,
                kind="repair",
                attempt_id=attempt_id,
                bundle_id=bundle_id,
                publish_state="succeeded",
                commit_sha=validated.commit_sha,
                project=project,
                updated_at=_now(),
            ),
        )

    return {
        "ok": True,
        "new_head_commit_sha": validated.commit_sha,
        "publish_state": "succeeded",
    }
