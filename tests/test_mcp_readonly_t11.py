"""T11 — read-only MCP graph/memory server."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from agent_control.events import write_verification_state
from agent_control.graph.store import GraphStore
from agent_control.mcp.bounds import bound_payload
from agent_control.mcp.registry import FORBIDDEN_TOOLS, invoke_tool, list_tools
from agent_control.mcp.server import ReadonlyMcpServer
from agent_control.mcp.validate import MCP_TOOL_RESULT_SCHEMA, validate_tool_result
from agent_control.memory.store import MemoryStore
from agent_shared.models.memory import MemoryRecord
from agent_shared.models.review import ReviewFinding
from agent_shared.models.state import VerificationState
from jsonschema import Draft202012Validator


@pytest.fixture
def mcp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "agent-state"
    runs = tmp_path / "agent-runs"
    cache = tmp_path / "cache"
    state.mkdir()
    runs.mkdir()
    cache.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_RUNS_DIR", str(runs))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(cache))
    return state


def _seed_graph(repo: str) -> GraphStore:
    from agent_control.config import get_settings

    store = GraphStore(get_settings().graph_db_path)
    store.init_schema()
    store.upsert_snapshot(
        repo,
        files=["src/a.py", "src/b.py", "tests/test_a.py"],
        services=["svc-a"],
        tests=["tests/test_a.py"],
        adrs=[{"adr_id": "ADR-0001", "title": "Test"}],
        edges=[
            {
                "src": "file:src/b.py",
                "dst": "file:src/a.py",
                "kind": "file_imports_file",
                "src_kind": "file",
                "dst_kind": "file",
                "provenance": "static_analysis",
            },
            {
                "src": "service:svc-a",
                "dst": "file:src/a.py",
                "kind": "service_owns_file",
                "src_kind": "service",
                "dst_kind": "file",
                "provenance": "catalog",
            },
            {
                "src": "service:svc-a",
                "dst": "test:tests/test_a.py",
                "kind": "service_tested_by_test",
                "src_kind": "service",
                "dst_kind": "test",
                "provenance": "catalog",
            },
            {
                "src": "file:src/a.py",
                "dst": "test:tests/test_a.py",
                "kind": "file_tested_by_test",
                "src_kind": "file",
                "dst_kind": "test",
                "provenance": "heuristic",
            },
        ],
        source_sha="abc123",
    )
    return store


def _seed_memory(repo: str) -> None:
    from agent_control.config import get_settings

    owner, name = repo.split("/", 1)
    store = MemoryStore(get_settings().memory_db_path)
    store.init_schema()
    store.upsert_record(
        MemoryRecord(
            record_id="rec-1",
            run_id="run-t11",
            repo_owner=owner,
            repo_name=name,
            repo_full_name=repo,
            issue_id=42,
            source_command="review",
            source_run_id="run-t11",
            created_at="2026-07-20T00:00:00+00:00",
            updated_at="2026-07-20T00:00:00+00:00",
            findings=[
                ReviewFinding(
                    id="finding-xyz",
                    severity="warn",
                    summary="Example finding for MCP",
                    file="src/a.py",
                )
            ],
        )
    )


def test_list_tools_is_readonly_allowlist() -> None:
    names = {t["name"] for t in list_tools()}
    assert "get_context_capsule" in names
    assert "explain_blast_radius" in names
    assert "get_context_pack" in names
    assert names.isdisjoint(FORBIDDEN_TOOLS)
    assert "run_shell" not in names
    assert "update_state" not in names


def test_forbidden_tools_denied(mcp_env: Path) -> None:
    for name in ("run_shell", "update_state", "push_commit", "modify_adr", "write_file"):
        result = invoke_tool(name, {"repo": "ai-sdlc-lab/demo"})
        assert result["ok"] is False
        assert result["schema"] == "mcp_tool_result.v1"
        assert "not_allowed" in result["error"] or "forbidden" in result["error"]


def test_schema_validate_and_bounds() -> None:
    Draft202012Validator.check_schema(MCP_TOOL_RESULT_SCHEMA)
    ok = validate_tool_result(
        {
            "schema": "mcp_tool_result.v1",
            "ok": True,
            "tool": "get_policy",
            "data": {},
            "evidence_refs": [],
        }
    )
    assert ok["ok"] is True
    huge = {"items": ["x" * 1000 for _ in range(200)], "schema": "mcp_tool_result.v1"}
    trimmed = bound_payload(huge, max_chars=5_000)
    assert len(json.dumps(trimmed)) <= 5_000


def test_verification_state_and_capsule(mcp_env: Path) -> None:
    from agent_control.config import get_settings

    repo = "ai-sdlc-lab/demo"
    settings = get_settings()
    state = VerificationState(project=repo, head_sha="deadbeef", event_count=3)
    write_verification_state(settings.agent_state_root, repo, state)

    vs = invoke_tool("get_verification_state", {"repo": repo})
    assert vs["ok"] is True
    assert vs["data"]["state"]["head_sha"] == "deadbeef"

    cap = invoke_tool("get_context_capsule", {"repo": repo})
    assert cap["ok"] is True
    assert cap["data"]["capsule"]["project"] == repo
    assert cap["data"]["capsule"]["schema"] == "agent.state_manifest.v1"


def test_graph_and_finding_queries(mcp_env: Path) -> None:
    repo = "ai-sdlc-lab/demo"
    _seed_graph(repo)
    _seed_memory(repo)

    callers = invoke_tool("find_callers", {"repo": repo, "file": "src/a.py"})
    assert callers["ok"] is True
    assert "file:src/b.py" in callers["data"]["related"]

    tests = invoke_tool(
        "find_affected_tests",
        {"repo": repo, "files": ["src/a.py"]},
    )
    assert tests["ok"] is True
    assert "tests/test_a.py" in tests["data"]["affected_tests"]

    path = invoke_tool(
        "find_dependency_path",
        {"repo": repo, "src": "src/b.py", "dst": "src/a.py"},
    )
    assert path["ok"] is True
    assert path["data"]["path"][0] == "file:src/b.py"
    assert path["data"]["path"][-1] == "file:src/a.py"

    blast = invoke_tool(
        "explain_blast_radius",
        {"repo": repo, "changed_files": ["src/a.py"]},
    )
    assert blast["ok"] is True
    assert blast["data"]["repo"] == repo

    finding = invoke_tool(
        "get_finding",
        {"repo": repo, "finding_id": "finding-xyz"},
    )
    assert finding["ok"] is True
    assert finding["data"]["finding"]["finding_id"] == "finding-xyz"

    traj = invoke_tool(
        "get_run_trajectory",
        {"repo": repo, "run_id": "run-t11"},
    )
    assert traj["ok"] is True
    assert traj["data"]["memory"]["run_id"] == "run-t11"

    pack = invoke_tool(
        "get_context_pack",
        {"repo": repo, "changed_files": ["src/a.py"], "issue_id": 42},
    )
    assert pack["ok"] is True
    assert pack["data"]["network"] is False
    assert "graph_blast_radius" in pack["data"]["context_sources"]


def test_get_policy_allowlist(mcp_env: Path) -> None:
    denied = invoke_tool(
        "get_policy",
        {"repo": "ai-sdlc-lab/agent-control-plane", "policy_name": "secrets"},
    )
    assert denied["ok"] is False
    assert denied["error"] == "policy_not_allowlisted"

    ok = invoke_tool(
        "get_policy",
        {"repo": "ai-sdlc-lab/agent-control-plane", "policy_name": "recursive_context"},
    )
    assert ok["ok"] is True
    assert "recursive_context" in ok["data"]["content"]


def test_stdio_initialize_and_tools_list(mcp_env: Path) -> None:
    server = ReadonlyMcpServer()
    init = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
    )
    assert init is not None
    assert init["result"]["serverInfo"]["name"] == "agent-control-plane-readonly"
    assert init["result"]["capabilities"]["tools"] == {"listChanged": False}

    listed = server.handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    assert listed is not None
    names = {t["name"] for t in listed["result"]["tools"]}
    assert "get_context_capsule" in names
    assert names.isdisjoint(FORBIDDEN_TOOLS)

    forbidden_call = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "run_shell", "arguments": {"cmd": "id"}},
        }
    )
    assert forbidden_call is not None
    assert forbidden_call["result"]["isError"] is True

    # End-to-end one line through serve()
    buf_in = StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "get_context_capsule",
                    "arguments": {"repo": "ai-sdlc-lab/demo"},
                },
            }
        )
        + "\n"
    )
    buf_out = StringIO()
    server.serve(stdin=buf_in, stdout=buf_out)
    lines = [ln for ln in buf_out.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["id"] == 9
    body = json.loads(payload["result"]["content"][0]["text"])
    assert body["schema"] == "mcp_tool_result.v1"
