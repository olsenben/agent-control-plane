"""CT104 patch_proposal.v1 builder. Immutable after finalize. No durable credentials."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_control.transaction.identity import (
    agent_worker,
    attribution,
    human_initiator,
)
from agent_control.transaction.identity.credentials import worker_credential_assertion
from agent_control.transaction.proposal import (
    ProposalImmutableError,
    assert_mutable,
    finalize_proposal,
    replace_unfinalized,
    utc_now,
)
from agent_shared.bundles.inbox import bundle_dir
from agent_shared.models.bundle import BundleKind
from agent_shared.models.transaction.identity import CompositeIdentity, IdentityPrincipal
from agent_shared.models.transaction.proposal import PatchProposal

PATCH_PROPOSAL_FILENAME = "patch_proposal.v1.json"
WORKER_ISSUER = "ct104"
DEFAULT_WORKER_ID = "agentworker"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


class WorkerProposalError(RuntimeError):
    """Raised when CT104 cannot seal a patch proposal."""


@dataclass(frozen=True)
class WorkerProposalContext:
    """Attribution and envelope fields for a worker-produced proposal."""

    session_id: str
    repo: str
    task_id: str
    tenant_id: str = "default"
    org_id: str = "default"
    human_initiator_id: str | None = None
    changed_files: list[str] | None = None
    changed_symbols: list[str] | None = None
    created_units: list[str] | None = None
    deleted_units: list[str] | None = None
    worker_id: str = DEFAULT_WORKER_ID
    notes: str | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def ensure_source_sha(value: str) -> str:
    text = (value or "").strip()
    if len(text) >= 7:
        return text
    return sha256_text(text or "missing-source-sha")


def source_tree_digest_for(source_tree: str | None, *, source_sha: str) -> str:
    """SHA-256 digest of the source tree when a git tree sha is all we have."""
    if source_tree and _SHA256_RE.fullmatch(source_tree):
        return source_tree
    material = (source_tree or source_sha).strip() or source_sha
    return sha256_text(material)


def parse_changed_files(patch_bytes: bytes) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    text = patch_bytes.decode("utf-8", errors="replace")
    for line in text.splitlines():
        match = _DIFF_GIT_RE.match(line)
        if not match:
            continue
        path = match.group(2)
        if path not in seen:
            seen.add(path)
            files.append(path)
    return files


def parse_unit_changes(patch_bytes: bytes) -> tuple[list[str], list[str]]:
    created: list[str] = []
    deleted: list[str] = []
    current: str | None = None
    text = patch_bytes.decode("utf-8", errors="replace")
    for line in text.splitlines():
        match = _DIFF_GIT_RE.match(line)
        if match:
            current = match.group(2)
            continue
        if current is None:
            continue
        if line.startswith("new file mode") and current not in created:
            created.append(current)
        elif line.startswith("deleted file mode") and current not in deleted:
            deleted.append(current)
    return created, deleted


def worker_actor_identity(*, worker_id: str = DEFAULT_WORKER_ID) -> IdentityPrincipal:
    """Executing actor is always AGENT_WORKER. Never a human initiator."""
    return agent_worker(worker_id, issuer=WORKER_ISSUER)


def assert_no_durable_credentials(env: Mapping[str, str] | None = None) -> None:
    assertion = worker_credential_assertion(env=env)
    if not assertion.get("ok"):
        names = [
            str(item.get("env_name"))
            for item in assertion.get("violations") or []
            if item.get("env_name")
        ]
        detail = ", ".join(names) if names else "durable credentials present"
        raise WorkerProposalError(
            "WORKER_DURABLE_CREDENTIALS_PRESENT=NO fail-closed: " + detail
        )


def _composite_identity(
    *,
    actor: IdentityPrincipal,
    human_initiator_id: str | None,
) -> CompositeIdentity | None:
    if not human_initiator_id:
        return None
    return attribution(
        on_behalf_of=human_initiator(human_initiator_id),
        executed_by=actor,
    )


def proposal_json_bytes(proposal: PatchProposal) -> bytes:
    data = proposal.model_dump(mode="json", exclude_none=True)
    return json.dumps(data, indent=2, sort_keys=True).encode("utf-8")


def build_patch_proposal(
    *,
    session_id: str,
    repo: str,
    task_id: str,
    source_sha: str,
    patch_bytes: bytes,
    raw_patch_location: str,
    tenant_id: str = "default",
    org_id: str = "default",
    source_tree: str | None = None,
    changed_files: list[str] | None = None,
    changed_symbols: list[str] | None = None,
    created_units: list[str] | None = None,
    deleted_units: list[str] | None = None,
    human_initiator_id: str | None = None,
    worker_id: str = DEFAULT_WORKER_ID,
    proposal_id: str | None = None,
    created_at: str | None = None,
    notes: str | None = None,
    env: Mapping[str, str] | None = None,
) -> PatchProposal:
    """Build an unfinalized proposal. Actor/EXECUTED_BY are AGENT_WORKER."""
    if not patch_bytes:
        raise WorkerProposalError("patch is empty")
    assert_no_durable_credentials(env)

    actor = worker_actor_identity(worker_id=worker_id)
    if actor.principal_kind != "AGENT_WORKER":
        raise WorkerProposalError("actor_identity must be AGENT_WORKER")

    effective_sha = ensure_source_sha(source_sha)
    patch_digest = sha256_bytes(patch_bytes)
    files = list(changed_files) if changed_files is not None else parse_changed_files(patch_bytes)
    created = list(created_units) if created_units is not None else None
    deleted = list(deleted_units) if deleted_units is not None else None
    if created is None or deleted is None:
        parsed_created, parsed_deleted = parse_unit_changes(patch_bytes)
        if created is None:
            created = parsed_created
        if deleted is None:
            deleted = parsed_deleted

    identity = _composite_identity(actor=actor, human_initiator_id=human_initiator_id)
    if identity is not None and identity.EXECUTED_BY.principal_kind != "AGENT_WORKER":
        raise WorkerProposalError("EXECUTED_BY must be AGENT_WORKER")

    return PatchProposal(
        session_id=session_id,
        proposal_id=proposal_id or f"pp-{patch_digest}",
        repo=repo,
        tenant_id=tenant_id,
        org_id=org_id,
        task_id=task_id,
        source_sha=effective_sha,
        source_tree_digest=source_tree_digest_for(source_tree, source_sha=effective_sha),
        patch_digest=patch_digest,
        changed_files=files,
        changed_symbols=list(changed_symbols or []),
        created_units=created,
        deleted_units=deleted,
        actor_identity=actor,
        worker_identity=worker_actor_identity(worker_id=worker_id),
        identity=identity,
        created_at=created_at or utc_now(),
        raw_patch_location=raw_patch_location,
        raw_patch_digest=patch_digest,
        finalized=False,
        notes=notes,
    )


def build_finalized_worker_proposal(
    *,
    context: WorkerProposalContext,
    source_sha: str,
    patch_bytes: bytes,
    raw_patch_location: str = "patch.diff",
    source_tree: str | None = None,
    env: Mapping[str, str] | None = None,
    finalized_at: str | None = None,
) -> PatchProposal:
    draft = build_patch_proposal(
        session_id=context.session_id,
        repo=context.repo,
        task_id=context.task_id,
        source_sha=source_sha,
        patch_bytes=patch_bytes,
        raw_patch_location=raw_patch_location,
        tenant_id=context.tenant_id,
        org_id=context.org_id,
        source_tree=source_tree,
        changed_files=context.changed_files,
        changed_symbols=context.changed_symbols,
        created_units=context.created_units,
        deleted_units=context.deleted_units,
        human_initiator_id=context.human_initiator_id,
        worker_id=context.worker_id,
        notes=context.notes,
        env=env,
    )
    return finalize_proposal(draft, finalized_at=finalized_at)


def new_proposal_for_patch(
    prior: PatchProposal,
    *,
    patch_bytes: bytes,
    raw_patch_location: str | None = None,
    source_tree: str | None = None,
    env: Mapping[str, str] | None = None,
    finalized_at: str | None = None,
) -> PatchProposal:
    """A new patch is a new proposal id/digest. Never mutates a finalized prior."""
    human_id = None
    if prior.identity is not None:
        human_id = prior.identity.ON_BEHALF_OF.identity_id
    replacement = build_patch_proposal(
        session_id=prior.session_id,
        repo=prior.repo,
        task_id=prior.task_id,
        source_sha=prior.source_sha,
        patch_bytes=patch_bytes,
        raw_patch_location=raw_patch_location or prior.raw_patch_location,
        tenant_id=prior.tenant_id,
        org_id=prior.org_id,
        source_tree=source_tree,
        changed_files=None,
        changed_symbols=list(prior.changed_symbols),
        human_initiator_id=human_id,
        worker_id=prior.worker_identity.identity_id,
        notes=prior.notes,
        env=env,
    )
    sealed = finalize_proposal(replacement, finalized_at=finalized_at)
    if sealed.proposal_id == prior.proposal_id and sealed.patch_digest != prior.patch_digest:
        raise WorkerProposalError("new patch must not reuse a prior proposal_id")
    return sealed


def refuse_mutate_finalized(proposal: PatchProposal, **updates: object) -> PatchProposal:
    """In-place mutate after finalize fails. Does not rewrite the prior digest."""
    assert_mutable(proposal)
    return replace_unfinalized(proposal, **updates)


def context_from_fields(
    *,
    session_id: str,
    repo: str,
    task_id: str,
    tenant_id: str | None = None,
    org_id: str | None = None,
    human_initiator_id: str | None = None,
    changed_files: list[str] | None = None,
    changed_symbols: list[str] | None = None,
    created_units: list[str] | None = None,
    deleted_units: list[str] | None = None,
    worker_id: str = DEFAULT_WORKER_ID,
    notes: str | None = None,
) -> WorkerProposalContext:
    owner = repo.split("/", 1)[0] if "/" in repo else repo
    return WorkerProposalContext(
        session_id=session_id,
        repo=repo,
        task_id=task_id,
        tenant_id=tenant_id or owner or "default",
        org_id=org_id or owner or "default",
        human_initiator_id=human_initiator_id,
        changed_files=changed_files,
        changed_symbols=changed_symbols,
        created_units=created_units,
        deleted_units=deleted_units,
        worker_id=worker_id,
        notes=notes,
    )


def copy_proposal_sidecar(
    *,
    state_root: Path,
    run_id: str,
    kind: BundleKind,
    attempt_id: str,
    bundle_id: str,
    dest_dir: Path,
) -> Path | None:
    """Copy the sealed proposal next to the run report. Never mutates the inbox copy."""
    root = bundle_dir(
        state_root,
        run_id=run_id,
        kind=kind,
        attempt_id=attempt_id,
        bundle_id=bundle_id,
    )
    src = root / PATCH_PROPOSAL_FILENAME
    if not src.is_file():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / PATCH_PROPOSAL_FILENAME
    dest.write_bytes(src.read_bytes())
    return dest


def load_proposal_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "PATCH_PROPOSAL_FILENAME",
    "ProposalImmutableError",
    "WORKER_ISSUER",
    "WorkerProposalContext",
    "WorkerProposalError",
    "assert_no_durable_credentials",
    "build_finalized_worker_proposal",
    "build_patch_proposal",
    "context_from_fields",
    "copy_proposal_sidecar",
    "ensure_source_sha",
    "load_proposal_payload",
    "new_proposal_for_patch",
    "parse_changed_files",
    "proposal_json_bytes",
    "refuse_mutate_finalized",
    "sha256_bytes",
    "source_tree_digest_for",
    "worker_actor_identity",
]
