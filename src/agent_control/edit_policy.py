"""Reusable edit-role authorization.

``allowed_files`` is repository scope. ``edit_policy`` is which of those files
may be modified for one task. Evidence visibility is independent.

Missing/empty ``edit_policy`` is inert: no new patch restriction and no
policy prompt text. Production must not set this field.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.edit_policy import (
    SCHEMA_VERSION,
    EditPathRule,
    EditPolicyV1,
    EditRole,
    PatchAuthorizationResult,
)
from agent_shared.patch_paths import PatchPathError, normalize_repo_relative_path

ROLE_EDITABLE: EditRole = "editable"
ROLE_INSPECT_ONLY: EditRole = "inspect_only"
DECISION_ALLOW = "ALLOW"
DECISION_REJECT = "REJECT"
CLASS_NO_VIOLATION = "NO_POLICY_VIOLATION"
CLASS_TEST_EDIT_BLOCKED = "TEST_EDIT_ATTEMPT_BLOCKED"
CLASS_OTHER = "OTHER_POLICY_VIOLATION"
STOP_REPAIR = "STOP_REPAIR"
INSPECT_ONLY_HEADER = (
    "The following files are available as evidence but must not be modified:"
)


class EditPolicyError(RuntimeError):
    """Edit policy could not be parsed or applied."""


def normalize_policy_path(path: str) -> str:
    """Normalize a repository-relative policy path. Rejects traversal."""
    try:
        return normalize_repo_relative_path(path)
    except PatchPathError as exc:
        raise EditPolicyError(str(exc)) from exc


def canonical_policy_body(policy: EditPolicyV1) -> dict[str, Any]:
    rules = sorted(
        (
            {
                "path": rule.path,
                "role": rule.role,
                "reason_code": rule.reason_code,
                "source": rule.source,
            }
            for rule in policy.path_rules
        ),
        key=lambda item: item["path"],
    )
    return {
        "schema_version": policy.schema_version,
        "default_role": policy.default_role,
        "path_rules": rules,
        "provenance": policy.provenance,
    }


def policy_hash(policy: EditPolicyV1 | None) -> str | None:
    if policy is None:
        return None
    return canonical_json_hash(canonical_policy_body(policy))


def inspect_only_paths(policy: EditPolicyV1 | None) -> list[str]:
    if policy is None:
        return []
    return sorted(
        rule.path for rule in policy.path_rules if rule.role == ROLE_INSPECT_ONLY
    )


def render_edit_policy_instruction(policy: EditPolicyV1 | None) -> str:
    """Deterministic model-visible restriction. Empty when policy is inert."""
    paths = inspect_only_paths(policy)
    if not paths:
        return ""
    return "\n".join([INSPECT_ONLY_HEADER, *[f"- {path}" for path in paths]])


def parse_edit_policy(raw: Mapping[str, Any] | None) -> EditPolicyV1 | None:
    """Return a typed policy or None when the feature is off.

    None when the field is missing, empty, or explicitly disabled. Presence of
    ``schema_version: edit_policy.v1`` or legacy ``enabled: true`` opts in.
    """
    if not raw:
        return None
    payload = dict(raw)
    enabled = payload.get("enabled")
    schema = str(payload.get("schema_version") or "").strip()
    has_v1 = schema == SCHEMA_VERSION
    if not has_v1 and enabled is not True:
        return None
    default_role = str(payload.get("default_role") or ROLE_EDITABLE).strip()
    if default_role not in {ROLE_EDITABLE, ROLE_INSPECT_ONLY}:
        raise EditPolicyError(f"malformed default_role {default_role!r}")
    rules = _collect_path_rules(payload)
    policy = EditPolicyV1(
        schema_version=SCHEMA_VERSION,
        default_role=default_role,  # type: ignore[arg-type]
        path_rules=rules,
        provenance=str(payload.get("provenance") or "") or None,
    )
    policy.policy_id = policy_hash(policy)
    return policy


def policy_is_active(policy: EditPolicyV1 | None) -> bool:
    return policy is not None


def role_for_path(policy: EditPolicyV1, path: str) -> tuple[EditRole, str]:
    """Explicit path rule overrides default_role. No glob precedence."""
    normalized = normalize_policy_path(path)
    for rule in policy.path_rules:
        if rule.path == normalized:
            return rule.role, rule.reason_code
    return policy.default_role, "explicit_policy_rule"


def requested_paths(fix_result: Any) -> list[str]:
    paths: list[str] = []
    if fix_result is None:
        return paths
    files = list(getattr(fix_result, "files_changed", None) or [])
    changes = list(getattr(fix_result, "changes", None) or [])
    if not files and isinstance(fix_result, Mapping):
        files = list(fix_result.get("files_changed") or [])
        changes = list(fix_result.get("changes") or [])
    for item in files:
        paths.append(str(item))
    for change in changes:
        if hasattr(change, "path"):
            paths.append(str(change.path))
        elif isinstance(change, Mapping):
            paths.append(str(change.get("path") or ""))
    seen: list[str] = []
    for path in paths:
        if not path:
            continue
        try:
            normalized = normalize_repo_relative_path(path)
        except PatchPathError:
            normalized = path.replace("\\", "/").lstrip("./")
        if normalized not in seen:
            seen.append(normalized)
    return seen


def authorize_edit_targets(
    *,
    requested: Sequence[str],
    policy: Mapping[str, Any] | EditPolicyV1 | None,
) -> dict[str, Any]:
    """Authorize after parse, before apply/verify. Reject-whole-patch."""
    parsed = (
        policy
        if isinstance(policy, EditPolicyV1)
        else parse_edit_policy(policy if isinstance(policy, Mapping) else None)
    )
    requested_list = _normalize_requested(requested)
    if parsed is None:
        return _inactive_authorization(requested_list)
    communicated = inspect_only_paths(parsed)
    editable: list[str] = []
    denied: list[str] = []
    reason_codes: list[str] = []
    for path in requested_list:
        try:
            role, reason = role_for_path(parsed, path)
        except EditPolicyError:
            denied.append(path)
            reason_codes.append("explicit_policy_rule")
            continue
        if role == ROLE_INSPECT_ONLY:
            if path not in denied:
                denied.append(path)
            if reason not in reason_codes:
                reason_codes.append(reason)
        elif path not in editable:
            editable.append(path)
    decision = DECISION_REJECT if denied else DECISION_ALLOW
    parity_ok = communicated == inspect_only_paths(parsed)
    klass = CLASS_NO_VIOLATION
    if denied:
        if any(path.startswith("tests/") or path.endswith("_test.py") for path in denied):
            klass = CLASS_TEST_EDIT_BLOCKED
        elif any(code == "test_oracle" for code in reason_codes):
            klass = CLASS_TEST_EDIT_BLOCKED
        else:
            klass = CLASS_OTHER
    result = PatchAuthorizationResult(
        policy_id=parsed.policy_id,
        requested_paths=requested_list,
        editable_paths=editable,
        inspect_only_paths=communicated,
        denied_paths=denied,
        decision=decision,  # type: ignore[arg-type]
        reason_codes=reason_codes,
        communicated_inspect_only_paths=communicated,
        enforced_inspect_only_paths=communicated,
        parity_ok=parity_ok,
        default_role=parsed.default_role,
        policy_active=True,
    )
    payload = result.model_dump(mode="json")
    payload.update(
        {
            "enabled": True,
            "authorized": decision == DECISION_ALLOW,
            "class": klass,
            "files_requested_to_modify": requested_list,
            "files_authorized": editable,
            "files_rejected": denied,
            "reason": (
                None
                if decision == DECISION_ALLOW
                else "edit_role_policy_rejected: inspect_only path " + ", ".join(denied)
            ),
            "edit_policy_hash": parsed.policy_id,
        }
    )
    return payload


def communication_enforcement_parity(
    policy: EditPolicyV1 | None,
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    """Rendered inspect_only paths must equal enforced inspect_only paths."""
    rendered = inspect_only_paths(policy)
    instruction = render_edit_policy_instruction(policy)
    parsed_from_prompt = _paths_from_instruction(instruction)
    enforced = list(authorization.get("enforced_inspect_only_paths") or [])
    denied = list(authorization.get("denied_paths") or [])
    ok = rendered == parsed_from_prompt == enforced
    if not ok:
        return {
            "ok": False,
            "decision": STOP_REPAIR,
            "rendered": rendered,
            "prompt_paths": parsed_from_prompt,
            "enforced": enforced,
        }
    for path in denied:
        if path not in rendered:
            return {
                "ok": False,
                "decision": STOP_REPAIR,
                "rendered": rendered,
                "prompt_paths": parsed_from_prompt,
                "enforced": enforced,
                "denied_not_communicated": [path],
            }
    return {
        "ok": True,
        "decision": "PARITY_OK",
        "rendered": rendered,
        "prompt_paths": parsed_from_prompt,
        "enforced": enforced,
    }


def policy_audit_record(policy: EditPolicyV1 | None) -> dict[str, Any]:
    if policy is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_active": False,
            "policy_id": None,
            "default_role": None,
            "path_rules": [],
            "communicated_inspect_only_paths": [],
        }
    return {
        "schema_version": policy.schema_version,
        "policy_active": True,
        "policy_id": policy.policy_id,
        "default_role": policy.default_role,
        "provenance": policy.provenance,
        "path_rules": [rule.model_dump(mode="json") for rule in policy.path_rules],
        "communicated_inspect_only_paths": inspect_only_paths(policy),
        "instruction": render_edit_policy_instruction(policy),
    }


def authorization_telemetry(authorization: Mapping[str, Any]) -> dict[str, Any]:
    """Safe audit fields. No patch or prompt bodies."""
    return {
        "event_name": "patch.authz_decided",
        "policy_id": authorization.get("policy_id") or authorization.get("edit_policy_hash"),
        "requested_path_count": len(list(authorization.get("requested_paths") or [])),
        "denied_path_count": len(list(authorization.get("denied_paths") or [])),
        "decision": authorization.get("decision"),
        "reason_codes": list(authorization.get("reason_codes") or []),
    }


def _collect_path_rules(payload: Mapping[str, Any]) -> list[EditPathRule]:
    collected: list[EditPathRule] = []
    seen: dict[str, EditRole] = {}
    for item in list(payload.get("path_rules") or []):
        collected.append(_rule_from_mapping(item if isinstance(item, Mapping) else {}))
    paths = payload.get("paths")
    if isinstance(paths, Mapping):
        for path, spec in paths.items():
            if isinstance(spec, Mapping):
                collected.append(
                    _rule_from_mapping({"path": path, **dict(spec)})
                )
            else:
                collected.append(
                    _rule_from_mapping({"path": path, "role": spec})
                )
    roles = payload.get("roles")
    if not collected and isinstance(roles, Mapping):
        for path, role in roles.items():
            collected.append(_rule_from_mapping({"path": path, "role": role}))
    unique: list[EditPathRule] = []
    for rule in collected:
        normalized = normalize_policy_path(rule.path)
        if ".." in path_parts_guard(rule.path):
            raise EditPolicyError(f"path traversal not allowed: {rule.path!r}")
        role = rule.role
        if normalized in seen and seen[normalized] != role:
            raise EditPolicyError(
                f"duplicate conflicting rules for {normalized}: "
                f"{seen[normalized]} vs {role}"
            )
        if normalized in seen:
            continue
        seen[normalized] = role
        unique.append(
            EditPathRule(
                path=normalized,
                role=role,
                reason_code=str(rule.reason_code or "explicit_policy_rule"),
                source=str(rule.source or "task_config"),
            )
        )
    return unique


def path_parts_guard(path: str) -> tuple[str, ...]:
    return tuple(path.replace("\\", "/").split("/"))


def _rule_from_mapping(item: Mapping[str, Any]) -> EditPathRule:
    role = str(item.get("role") or "").strip()
    if role not in {ROLE_EDITABLE, ROLE_INSPECT_ONLY}:
        raise EditPolicyError(f"malformed role {role!r}")
    path = str(item.get("path") or "").strip()
    if not path:
        raise EditPolicyError("path rule missing path")
    return EditPathRule(
        path=path,
        role=role,  # type: ignore[arg-type]
        reason_code=str(item.get("reason_code") or "explicit_policy_rule"),
        source=str(item.get("source") or "task_config"),
    )


def _normalize_requested(requested: Sequence[str]) -> list[str]:
    seen: list[str] = []
    for path in requested:
        text = str(path)
        if not text:
            continue
        try:
            normalized = normalize_repo_relative_path(text)
        except PatchPathError:
            normalized = text.replace("\\", "/").lstrip("./")
        if normalized not in seen:
            seen.append(normalized)
    return seen


def _inactive_authorization(requested_list: list[str]) -> dict[str, Any]:
    result = PatchAuthorizationResult(
        policy_id=None,
        requested_paths=requested_list,
        editable_paths=requested_list,
        inspect_only_paths=[],
        denied_paths=[],
        decision=DECISION_ALLOW,
        reason_codes=[],
        communicated_inspect_only_paths=[],
        enforced_inspect_only_paths=[],
        parity_ok=True,
        default_role=None,
        policy_active=False,
    )
    payload = result.model_dump(mode="json")
    payload.update(
        {
            "enabled": False,
            "authorized": True,
            "class": CLASS_NO_VIOLATION,
            "files_requested_to_modify": requested_list,
            "files_authorized": requested_list,
            "files_rejected": [],
            "reason": None,
            "edit_policy_hash": None,
        }
    )
    return payload


def _paths_from_instruction(instruction: str) -> list[str]:
    if not instruction.strip():
        return []
    paths: list[str] = []
    for line in instruction.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            paths.append(stripped[2:].strip())
    return paths
