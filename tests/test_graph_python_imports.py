"""Tests for Python import extraction."""

from pathlib import Path

from agent_control.graph.extractors.python_imports import extract_file_import_edges, extract_imports


def test_extract_imports_from_dispatch(control_plane_root: Path) -> None:
    path = control_plane_root / "src" / "agent_control" / "workflows" / "dispatch.py"
    names = extract_imports(path)
    assert "agent_control.config" in names or "typing" in names


def test_extract_file_import_edges(control_plane_root: Path) -> None:
    files, edges, _warnings = extract_file_import_edges(
        "ai-sdlc-lab/agent-control-plane",
        control_plane_root,
    )
    assert any(f.endswith("dispatch.py") for f in files)
    import_edges = [e for e in edges if e["kind"] == "file_imports_file"]
    assert import_edges
