"""Live Gitea structured task/finding receipts. No LLM parser. No prose fallback."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import yaml

from agent_control.transaction.evidence.receipts import (
    AUTH_EXPLICIT,
    AUTH_NONE,
    EVIDENCE_FINDING,
    EVIDENCE_TASK_REQUIREMENT,
    STATUS_INCOMPLETE,
    STATUS_PASS,
    TRUST_TASK_SYSTEM,
    evidence_hash,
    make_receipt,
)
from agent_control.transaction.evidence.sarif import canonicalize_rule_id
from agent_shared.project_ids import split_project

SCHEMA_TASK_RECEIPT = "task_evidence_receipt.v1"
COMPILED_FROM = "GITEA_ISSUE_STRUCTURED_BLOCK"
PRODUCER = "gitea_task_envelope_finding_adapter"

REQUESTED_REMEDIATE = "REMEDIATE_FINDING"
STATUS_BOUND = "BOUND"
STATUS_UNBOUND = "UNBOUND"
STATUS_INCOMPLETE_RECEIPT = "INCOMPLETE"

UNBOUND_TASK_EVIDENCE = "TASK_EVIDENCE_UNBOUND"
UNBOUND_FINDING_MISMATCH = "TASK_FINDING_MISMATCH"
UNBOUND_WRONG_REPO = "WRONG_REPO"
UNBOUND_WRONG_TASK = "WRONG_TASK"
UNBOUND_WRONG_SOURCE = "WRONG_SOURCE_SHA"
UNBOUND_MISSING_BLOCK = "MISSING_STRUCTURED_BLOCK"

STRUCTURED_KEYS = (
    "finding_id",
    "provider",
    "provider_id",
    "rule_id",
    "repository",
    "source_sha",
    "location",
    "affected_path",
    "affected_location",
    "requested_action",
    "authorized_mutation_class",
    "authorized_change_class",
    "initiator",
    "human_initiator",
)

_FENCE_RE = re.compile(
    r"```(?:ya?ml|json|task[-_]evidence)\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_KEY_ALIASES = {
    "repo": "repository",
    "gitea_repository": "repository",
    "provider_id": "provider_id",
    "provider": "provider",
    "human_initiator": "human_initiator",
    "initiator": "initiator",
    "source_sha": "source_sha",
    "sourcesha": "source_sha",
    "authorized_change_class": "authorized_change_class",
    "authorized_mutation_class": "authorized_mutation_class",
}


@dataclass(frozen=True)
class FrozenTaskIssue:
    """Issue content hashed at transaction creation. Later edits do not mutate digest."""

    repository: str
    issue_id: int
    content: str
    digest: str
    body: str
    labels: tuple[str, ...]
    structured: dict[str, Any]
    missing_structured_block: bool


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _label_names(issue: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for item in issue.get("labels") or []:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, Mapping):
            name = str(item.get("name") or "").strip()
        else:
            name = ""
        if name:
            names.append(name)
    return names


def _issue_repository(issue: Mapping[str, Any], fallback: str | None = None) -> str:
    nested = issue.get("repository")
    if isinstance(nested, Mapping):
        full = _opt_str(nested.get("full_name") or nested.get("name"))
        if full:
            return full
    if isinstance(nested, str) and nested.strip():
        return nested.strip()
    html = _opt_str(issue.get("html_url") or issue.get("url"))
    if html:
        parts = html.replace("\\", "/").split("/")
        if "issues" in parts:
            idx = parts.index("issues")
            if idx >= 2:
                return f"{parts[idx - 2]}/{parts[idx - 1]}"
    return str(fallback or "")


def _issue_id(issue: Mapping[str, Any]) -> int:
    for key in ("number", "issue_id", "id"):
        raw = issue.get(key)
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value >= 1:
            return value
    return 0


def _normalize_structured(raw: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.items():
        norm = str(key).strip().lower().replace("-", "_")
        mapped = _KEY_ALIASES.get(norm, norm)
        if mapped in STRUCTURED_KEYS or mapped in _KEY_ALIASES.values():
            out[mapped] = value
    if "provider_id" not in out and out.get("provider"):
        out["provider_id"] = out.get("provider")
    if "initiator" not in out and out.get("human_initiator"):
        out["initiator"] = out.get("human_initiator")
    if "human_initiator" not in out and out.get("initiator"):
        out["human_initiator"] = out.get("initiator")
    if "authorized_mutation_class" not in out and out.get("authorized_change_class"):
        out["authorized_mutation_class"] = out.get("authorized_change_class")
    if "authorized_change_class" not in out and out.get("authorized_mutation_class"):
        out["authorized_change_class"] = out.get("authorized_mutation_class")
    loc = out.get("location") or out.get("affected_location") or out.get("affected_path")
    if loc is not None and not isinstance(loc, (dict, list)):
        text = str(loc).strip()
        out["affected_location"] = text
        out["affected_path"] = text.split(":")[0] if text else None
        out.setdefault("location", text)
    elif isinstance(loc, Mapping):
        path = _opt_str(loc.get("path") or loc.get("uri"))
        line = loc.get("start_line") or loc.get("line")
        out["affected_path"] = path
        out["affected_location"] = f"{path}:{line}" if path and line else path
        out.setdefault("location", out["affected_location"])
    return out


def parse_structured_labels(labels: Sequence[str]) -> dict[str, Any]:
    """Machine-readable labels only. Unknown free-text labels are ignored."""
    raw: dict[str, Any] = {}
    allowed = set(STRUCTURED_KEYS) | set(_KEY_ALIASES)
    for name in labels:
        if ":" not in name:
            continue
        key, _, value = name.partition(":")
        norm = key.strip().lower().replace("-", "_")
        if norm not in allowed:
            continue
        mapped = _KEY_ALIASES.get(norm, norm)
        text = value.strip()
        if text:
            raw[mapped] = text
    return _normalize_structured(raw)


def parse_structured_fence(body: str) -> dict[str, Any] | None:
    """YAML/JSON fence. Does not interpret surrounding prose."""
    match = _FENCE_RE.search(body or "")
    if match is None:
        return None
    blob = match.group(1).strip()
    if not blob:
        return None
    lang = "yaml"
    header = match.group(0).split("\n", 1)[0].lower()
    if "json" in header:
        lang = "json"
    loaded: Any
    if lang == "json":
        try:
            loaded = json.loads(blob)
        except json.JSONDecodeError:
            return None
    else:
        try:
            loaded = yaml.safe_load(blob)
        except yaml.YAMLError:
            try:
                loaded = json.loads(blob)
            except json.JSONDecodeError:
                return None
    if not isinstance(loaded, Mapping):
        return None
    return _normalize_structured(loaded)


def parse_structured_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    body = str(issue.get("body") or "")
    labels = _label_names(issue)
    fenced = parse_structured_fence(body) or {}
    labeled = parse_structured_labels(labels)
    merged = {**labeled, **fenced}
    return merged


def structured_block_complete(structured: Mapping[str, Any]) -> bool:
    finding = _opt_str(structured.get("finding_id"))
    rule = _opt_str(structured.get("rule_id"))
    provider = _opt_str(structured.get("provider") or structured.get("provider_id"))
    repository = _opt_str(structured.get("repository"))
    source_sha = _opt_str(structured.get("source_sha"))
    location = _opt_str(
        structured.get("location")
        or structured.get("affected_location")
        or structured.get("affected_path")
    )
    action = _opt_str(structured.get("requested_action"))
    mutation = _opt_str(
        structured.get("authorized_mutation_class") or structured.get("authorized_change_class")
    )
    initiator = _opt_str(structured.get("initiator") or structured.get("human_initiator"))
    return bool(
        finding
        and (rule or provider)
        and repository
        and source_sha
        and location
        and action
        and mutation
        and initiator
    )


def freeze_gitea_issue(
    issue: Mapping[str, Any],
    *,
    repository: str | None = None,
) -> FrozenTaskIssue:
    repo = _issue_repository(issue, repository)
    issue_id = _issue_id(issue)
    body = str(issue.get("body") or "")
    labels = tuple(sorted(_label_names(issue)))
    payload = {
        "gitea_repository": repo,
        "issue_id": issue_id,
        "body": body,
        "labels": list(labels),
    }
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = evidence_hash(payload)
    structured = parse_structured_issue(issue)
    missing = not structured_block_complete(structured)
    return FrozenTaskIssue(
        repository=repo,
        issue_id=issue_id,
        content=content,
        digest=digest,
        body=body,
        labels=labels,
        structured=structured,
        missing_structured_block=missing,
    )


def fetch_gitea_issue(
    client: Any,
    repository: str,
    issue_id: int,
) -> dict[str, Any]:
    """Read-only get_issue. Does not write to Gitea."""
    owner, repo = split_project(repository)
    payload = client.get_issue(owner, repo, issue_id)
    if not isinstance(payload, Mapping):
        return {}
    data = dict(payload)
    data.setdefault("repository", {"full_name": repository})
    return data


def _finding_tokens(item: Mapping[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("finding_id", "identity", "rule_id"):
        value = _opt_str(item.get(key))
        if value:
            tokens.add(value)
            if key == "rule_id":
                tokens.add(canonicalize_rule_id(value))
    loc = item.get("affected_location")
    loc_path = loc.get("path") if isinstance(loc, Mapping) else loc
    path = _opt_str(
        item.get("location_path") or item.get("affected_path") or item.get("path") or loc_path
    )
    rule = _opt_str(item.get("rule_id"))
    if path:
        tokens.add(path.split(":")[0])
    if rule and path:
        path_only = path.split(":")[0]
        tokens.add(f"{rule}|{path_only}")
        tokens.add(f"{canonicalize_rule_id(rule)}|{path_only}")
    return {token for token in tokens if token}


def finding_in_source(
    structured: Mapping[str, Any],
    source_findings: Sequence[Mapping[str, Any]] | None,
) -> bool:
    source = list(source_findings or [])
    wanted = _finding_tokens(structured)
    finding_id = _opt_str(structured.get("finding_id"))
    if finding_id:
        wanted.add(finding_id)
    if not wanted:
        return False
    present: set[str] = set()
    for item in source:
        present.update(_finding_tokens(item))
    return bool(wanted & present)


def _unbound_reason(
    freeze: FrozenTaskIssue,
    binding: Mapping[str, Any],
    *,
    expected_issue_id: int | None,
    expected_repository: str | None,
    source_findings: Sequence[Mapping[str, Any]] | None,
    source_findings_provided: bool,
) -> str | None:
    if freeze.missing_structured_block:
        return UNBOUND_MISSING_BLOCK
    structured = freeze.structured
    bind_repo = _opt_str(binding.get("repo") or binding.get("repository"))
    bind_sha = _opt_str(binding.get("source_sha"))
    issue_repo = _opt_str(structured.get("repository")) or freeze.repository
    expected_repo = expected_repository or bind_repo
    if expected_repo and issue_repo and issue_repo != expected_repo:
        return UNBOUND_TASK_EVIDENCE
    if freeze.repository and expected_repo and freeze.repository != expected_repo:
        return UNBOUND_TASK_EVIDENCE
    if expected_issue_id is not None and freeze.issue_id and freeze.issue_id != int(expected_issue_id):
        return UNBOUND_TASK_EVIDENCE
    issue_sha = _opt_str(structured.get("source_sha"))
    if bind_sha and issue_sha and issue_sha != bind_sha:
        return UNBOUND_TASK_EVIDENCE
    if source_findings_provided and not finding_in_source(structured, source_findings):
        return UNBOUND_FINDING_MISMATCH
    return None


def derive_task_evidence_receipt(
    freeze: FrozenTaskIssue,
    *,
    binding: Mapping[str, Any] | None = None,
    expected_issue_id: int | None = None,
    expected_repository: str | None = None,
    source_findings: Sequence[Mapping[str, Any]] | None = None,
    source_findings_provided: bool = False,
    task_id: str | None = None,
    proposal_id: str | None = None,
    transaction_id: str | None = None,
) -> dict[str, Any]:
    """Deterministic receipt. TASK_DIGEST is freeze.digest, not a later issue edit."""
    bind = dict(binding or {})
    structured = dict(freeze.structured)
    reason = _unbound_reason(
        freeze,
        bind,
        expected_issue_id=expected_issue_id,
        expected_repository=expected_repository,
        source_findings=source_findings,
        source_findings_provided=source_findings_provided,
    )
    bind_repo = _opt_str(bind.get("repo") or bind.get("repository")) or freeze.repository
    bind_sha = _opt_str(bind.get("source_sha")) or _opt_str(structured.get("source_sha"))
    bound = reason is None
    if reason == UNBOUND_MISSING_BLOCK:
        status = STATUS_INCOMPLETE_RECEIPT
    elif reason:
        status = STATUS_UNBOUND
    else:
        status = STATUS_BOUND
    patch = _opt_str(bind.get("patch_digest"))
    initiator = _opt_str(structured.get("initiator") or structured.get("human_initiator")) or "unknown"
    action = _opt_str(structured.get("requested_action")) or "OTHER_STRUCTURED"
    if action not in {REQUESTED_REMEDIATE, "AUTHORIZE_MUTATION", "OTHER_STRUCTURED"}:
        action = "OTHER_STRUCTURED"
    mutation = _opt_str(
        structured.get("authorized_mutation_class") or structured.get("authorized_change_class")
    ) or "OTHER_TYPED"
    receipt_id_src = {
        "gitea_repository": freeze.repository or bind_repo,
        "issue_id": freeze.issue_id,
        "task_digest": freeze.digest,
        "source_sha": bind_sha,
    }
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_TASK_RECEIPT,
        "receipt_id": evidence_hash(receipt_id_src)[:16],
        "gitea_repository": freeze.repository or bind_repo or "unknown/repo",
        "issue_id": freeze.issue_id if freeze.issue_id >= 1 else 1,
        "task_id": task_id,
        "proposal_id": proposal_id,
        "transaction_id": transaction_id,
        "source_sha": bind_sha or "unknown",
        "patch_digest": patch,
        "task_digest": freeze.digest,
        "human_initiator": initiator,
        "finding_id": _opt_str(structured.get("finding_id")),
        "provider_id": _opt_str(structured.get("provider_id") or structured.get("provider")),
        "rule_id": _opt_str(structured.get("rule_id")),
        "affected_path": _opt_str(structured.get("affected_path")),
        "affected_location": _opt_str(structured.get("affected_location") or structured.get("location")),
        "requested_action": action,
        "authorized_mutation_class": mutation,
        "authorized_change_class": _opt_str(structured.get("authorized_change_class")),
        "receipt_classes": ["TASK_NAMED", "FAILURE_DIRECT"],
        "compiled_from": COMPILED_FROM,
        "binding": {
            "repository": bind_repo or freeze.repository,
            "source_sha": bind_sha or "unknown",
            "task_digest": freeze.digest,
            "bound": bound,
        },
        "unbound_reason": reason,
        "llm_parsed": False,
        "hidden_gold": False,
        "trust_class": TRUST_TASK_SYSTEM,
        "authoritative_when_actor_provided": False,
        "free_text_authorization": False,
        "status": status,
        "notes": None,
    }
    return receipt


def task_receipt_to_evidence(
    task_receipt: Mapping[str, Any],
    *,
    binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    bind = dict(binding or {})
    reason = task_receipt.get("unbound_reason")
    bound = task_receipt.get("status") == STATUS_BOUND and not reason
    status = STATUS_PASS if bound else STATUS_INCOMPLETE
    auth = AUTH_EXPLICIT if bound else AUTH_NONE
    extra = {
        "task_evidence_receipt": dict(task_receipt),
        "unbound_reason": reason,
        "llm_parsed": False,
        "free_text_authorization": False,
    }
    receipts: list[dict[str, Any]] = [
        make_receipt(
            evidence_type=EVIDENCE_TASK_REQUIREMENT,
            result_status=status,
            trust_class=TRUST_TASK_SYSTEM,
            producer=PRODUCER,
            fact="TASK_AUTHORIZES_FINDING_REMEDIATION" if bound else "TASK_EVIDENCE_INCOMPLETE",
            authorization_class=auth,
            rule_id=_opt_str(task_receipt.get("rule_id") or task_receipt.get("finding_id")),
            location_path=_opt_str(task_receipt.get("affected_path")),
            detail=str(reason) if reason else None,
            extra=extra,
            repo=bind.get("repo") or bind.get("repository") or task_receipt.get("gitea_repository"),
            source_sha=bind.get("source_sha") or task_receipt.get("source_sha"),
            patch_digest=bind.get("patch_digest") or task_receipt.get("patch_digest"),
            candidate_digest=bind.get("candidate_digest"),
        )
    ]
    if bound and task_receipt.get("finding_id"):
        receipts.append(
            make_receipt(
                evidence_type=EVIDENCE_FINDING,
                result_status=STATUS_PASS,
                trust_class=TRUST_TASK_SYSTEM,
                producer=PRODUCER,
                rule_id=_opt_str(task_receipt.get("rule_id") or task_receipt.get("finding_id")),
                location_path=_opt_str(task_receipt.get("affected_path")),
                authorization_class=AUTH_NONE,
                extra={"task_evidence_receipt_id": task_receipt.get("receipt_id")},
                repo=bind.get("repo") or bind.get("repository") or task_receipt.get("gitea_repository"),
                source_sha=bind.get("source_sha") or task_receipt.get("source_sha"),
                patch_digest=bind.get("patch_digest") or task_receipt.get("patch_digest"),
                candidate_digest=bind.get("candidate_digest"),
            )
        )
    return {
        "status": "OK" if bound else STATUS_INCOMPLETE,
        "detail": reason,
        "task_receipt": dict(task_receipt),
        "receipts": receipts,
    }
