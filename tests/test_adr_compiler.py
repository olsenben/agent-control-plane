from pathlib import Path

from agent_control.adr_compiler import compile_adrs


def test_compile_skips_superseded(tmp_path: Path) -> None:
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-active.md").write_text(
        "---\nid: ADR-0001\nstatus: accepted\ntitle: Active ADR\n---\n# Body\n",
        encoding="utf-8",
    )
    (adr_dir / "0002-old.md").write_text(
        "---\nid: ADR-0002\nstatus: superseded\ntitle: Old\n---\n",
        encoding="utf-8",
    )
    facts = compile_adrs(adr_dir)
    assert len(facts) == 1
    assert facts[0]["adr_id"] == "ADR-0001"
