"""Allowlisted read-only MCP tools — no write / shell / mutation surface."""

from __future__ import annotations

from typing import Any, Callable

from agent_control.config import Settings, get_settings
from agent_control.mcp import queries
from agent_control.mcp.bounds import bound_payload
from agent_control.mcp.call_log import log_tool_call
from agent_control.mcp.validate import envelope

FORBIDDEN_TOOLS = frozenset(
    {
        "update_state",
        "mark_finding_fixed",
        "push_commit",
        "modify_adr",
        "run_shell",
        "terraform_apply",
        "write_file",
        "shell",
        "exec",
        "sql",
        "publish",
        "approve",
        "write_repo",
        "write_state",
        "git_push",
        "adr_mutate",
    }
)

ToolHandler = Callable[[dict[str, Any], Settings], dict[str, Any]]


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(x) for x in value if x is not None and str(x)]
    return [str(value)]


def _repo(args: dict[str, Any]) -> str:
    return str(args.get("repo") or args.get("project") or "")


def _handle_get_context_capsule(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.get_context_capsule(_repo(args), settings=settings)


def _handle_get_relevant_adr_facts(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.get_relevant_adr_facts(
        _repo(args),
        _as_str_list(args.get("changed_files") or args.get("files")),
        settings=settings,
    )


def _handle_get_finding(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.get_finding(_repo(args), str(args.get("finding_id") or ""), settings=settings)


def _handle_get_verification_state(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.get_verification_state(_repo(args), settings=settings)


def _handle_get_policy(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.get_policy(
        _repo(args),
        str(args.get("policy_name") or args.get("name") or ""),
        settings=settings,
    )


def _handle_get_run_trajectory(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.get_run_trajectory(
        _repo(args),
        str(args.get("run_id") or ""),
        settings=settings,
    )


def _handle_find_callers(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.find_callers(
        _repo(args),
        str(args.get("file") or args.get("path") or ""),
        settings=settings,
    )


def _handle_find_affected_tests(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.find_affected_tests(
        _repo(args),
        _as_str_list(args.get("files") or args.get("changed_files")),
        settings=settings,
    )


def _handle_find_dependency_path(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.find_dependency_path(
        _repo(args),
        str(args.get("src") or ""),
        str(args.get("dst") or ""),
        settings=settings,
    )


def _handle_explain_blast_radius(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return queries.explain_blast_radius(
        _repo(args),
        _as_str_list(args.get("changed_files") or args.get("files")),
        settings=settings,
    )


def _handle_get_context_pack(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    issue_raw = args.get("issue_id")
    issue_id = int(issue_raw) if issue_raw is not None and str(issue_raw).isdigit() else None
    if issue_raw is not None and issue_id is None:
        try:
            issue_id = int(issue_raw)
        except (TypeError, ValueError):
            issue_id = None
    return queries.get_context_pack(
        _repo(args),
        changed_files=_as_str_list(args.get("changed_files") or args.get("files")),
        issue_id=issue_id,
        settings=settings,
    )


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_context_capsule": _handle_get_context_capsule,
    "get_relevant_adr_facts": _handle_get_relevant_adr_facts,
    "get_finding": _handle_get_finding,
    "get_verification_state": _handle_get_verification_state,
    "get_policy": _handle_get_policy,
    "get_run_trajectory": _handle_get_run_trajectory,
    "find_callers": _handle_find_callers,
    "find_affected_tests": _handle_find_affected_tests,
    "find_dependency_path": _handle_find_dependency_path,
    "explain_blast_radius": _handle_explain_blast_radius,
    "get_context_pack": _handle_get_context_pack,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_context_capsule": "Read bounded context capsule from verification_state projection.",
    "get_relevant_adr_facts": "Read ADR facts related to changed files (graph + ADR compiler).",
    "get_finding": "Read a single finding from verified memory projections by finding_id.",
    "get_verification_state": "Read summaries/verification_state.json for a repo.",
    "get_policy": "Read an allowlisted local policy YAML (tools, recursive_context, …).",
    "get_run_trajectory": "Read memory + event + recursive-context trajectory for a run_id.",
    "find_callers": "Graph: files that import the given file.",
    "find_affected_tests": "Graph: affected tests for changed files via blast radius.",
    "find_dependency_path": "Graph: shortest dependency path between two nodes.",
    "explain_blast_radius": "Graph: explain blast radius for changed files.",
    "get_context_pack": "Bounded local context pack (graph/ADR/memory; no network).",
}

TOOL_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_context_capsule": {
        "type": "object",
        "properties": {"repo": {"type": "string", "description": "owner/repo"}},
        "required": ["repo"],
    },
    "get_relevant_adr_facts": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "changed_files": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["repo"],
    },
    "get_finding": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "finding_id": {"type": "string"},
        },
        "required": ["repo", "finding_id"],
    },
    "get_verification_state": {
        "type": "object",
        "properties": {"repo": {"type": "string"}},
        "required": ["repo"],
    },
    "get_policy": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "policy_name": {"type": "string"},
        },
        "required": ["repo", "policy_name"],
    },
    "get_run_trajectory": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "run_id": {"type": "string"},
        },
        "required": ["repo", "run_id"],
    },
    "find_callers": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "file": {"type": "string"},
        },
        "required": ["repo", "file"],
    },
    "find_affected_tests": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "files": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["repo"],
    },
    "find_dependency_path": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "src": {"type": "string"},
            "dst": {"type": "string"},
        },
        "required": ["repo", "src", "dst"],
    },
    "explain_blast_radius": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "changed_files": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["repo"],
    },
    "get_context_pack": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "changed_files": {"type": "array", "items": {"type": "string"}},
            "issue_id": {"type": "integer"},
        },
        "required": ["repo"],
    },
}


def list_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name in sorted(TOOL_HANDLERS):
        tools.append(
            {
                "name": name,
                "description": TOOL_DESCRIPTIONS.get(name, name),
                "inputSchema": TOOL_INPUT_SCHEMAS.get(
                    name,
                    {"type": "object", "properties": {"repo": {"type": "string"}}},
                ),
            }
        )
    return tools


def invoke_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    settings: Settings | None = None,
    log_path: Any = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    args = dict(arguments or {})
    tool = (name or "").strip()

    if tool in FORBIDDEN_TOOLS or tool not in TOOL_HANDLERS:
        result = envelope(
            tool=tool or "unknown",
            ok=False,
            error=f"tool_not_allowed:{tool}",
            evidence_refs=["policy:mcp.readonly"],
        )
        log_tool_call(tool=tool, args=args, ok=False, error=result.get("error", ""), log_path=log_path)
        return result

    try:
        result = TOOL_HANDLERS[tool](args, settings)
    except Exception as exc:  # noqa: BLE001 — surface as tool error, never mutate
        result = envelope(
            tool=tool,
            ok=False,
            error=f"internal_error:{type(exc).__name__}",
            repo=str(args.get("repo") or "") or None,
        )
        log_tool_call(tool=tool, args=args, ok=False, error=str(exc), log_path=log_path)
        return result

    if isinstance(result.get("data"), dict):
        result["data"] = bound_payload(result["data"])
    log_tool_call(
        tool=tool,
        args=args,
        ok=bool(result.get("ok")),
        error=str(result.get("error") or ""),
        log_path=log_path,
    )
    return result
