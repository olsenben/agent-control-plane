"""V5 T01 — AgentFacts-lite sync + integrity checks."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_control.agentfacts import (
    build_manifest,
    check_card_sync,
    verify_agentfacts,
    write_manifest,
)
from agent_control.agentfacts.sign import attach_integrity, verify_integrity
from agent_control.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_cards_in_sync() -> None:
    result = check_card_sync(
        agent_card_md=REPO_ROOT / "docs" / "AGENT_CARD.md",
        agent_card_json=REPO_ROOT / "agent-card.json",
    )
    assert result.ok, result.divergences


def test_build_and_verify_roundtrip(tmp_path: Path) -> None:
    md = REPO_ROOT / "docs" / "AGENT_CARD.md"
    card = REPO_ROOT / "agent-card.json"
    secret = "test-agentfacts-secret"
    manifest = build_manifest(
        agent_card_md=md,
        agent_card_json=card,
        signing_secret=secret,
    )
    out = tmp_path / "agent-facts.json"
    write_manifest(out, manifest)

    # Point verify at a mini repo layout
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "AGENT_CARD.md").write_bytes(md.read_bytes())
    (tmp_path / "agent-card.json").write_bytes(card.read_bytes())
    (tmp_path / "agent-facts.json").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")

    ok = verify_agentfacts(tmp_path, signing_secret=secret, require_hmac=True)
    assert ok.ok, ok.errors


def test_unsigned_manifest_fails(tmp_path: Path) -> None:
    md = REPO_ROOT / "docs" / "AGENT_CARD.md"
    card = REPO_ROOT / "agent-card.json"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "AGENT_CARD.md").write_bytes(md.read_bytes())
    (tmp_path / "agent-card.json").write_bytes(card.read_bytes())
    # no agent-facts.json
    result = verify_agentfacts(tmp_path)
    assert not result.ok
    assert any("unsigned" in e for e in result.errors)


def test_stale_source_hash_fails(tmp_path: Path) -> None:
    md = REPO_ROOT / "docs" / "AGENT_CARD.md"
    card = REPO_ROOT / "agent-card.json"
    (tmp_path / "docs").mkdir()
    md_bytes = md.read_bytes()
    json_bytes = card.read_bytes()
    (tmp_path / "docs" / "AGENT_CARD.md").write_bytes(md_bytes)
    (tmp_path / "agent-card.json").write_bytes(json_bytes)

    manifest = build_manifest(agent_card_md=md, agent_card_json=card)
    write_manifest(tmp_path / "agent-facts.json", manifest)

    # Mutate human card without re-signing
    (tmp_path / "docs" / "AGENT_CARD.md").write_bytes(md_bytes + b"\n")
    result = verify_agentfacts(tmp_path)
    assert not result.ok
    assert any("stale" in e for e in result.errors)


def test_tampered_payload_fails_digest() -> None:
    md = REPO_ROOT / "docs" / "AGENT_CARD.md"
    card = REPO_ROOT / "agent-card.json"
    manifest = build_manifest(agent_card_md=md, agent_card_json=card)
    manifest["limitations"] = list(manifest["limitations"]) + ["tampered"]
    errors = verify_integrity(
        manifest,
        agent_card_md_bytes=md.read_bytes(),
        agent_card_json_bytes=card.read_bytes(),
    )
    assert any("digest mismatch" in e for e in errors)


def test_missing_integrity_is_unsigned() -> None:
    body = {
        "schema_version": "agent_facts.v1",
        "name": "x",
        "capabilities": {
            "commands": [],
            "blocked_commands": [],
            "hosts": {"governance": "CT103", "execution": "CT104", "ci_truth": "CT102"},
        },
        "limitations": ["none"],
    }
    errors = verify_integrity(body)
    assert errors == ["unsigned: missing integrity block"]


def test_sync_detects_risk_divergence(tmp_path: Path) -> None:
    md = (REPO_ROOT / "docs" / "AGENT_CARD.md").read_text(encoding="utf-8")
    card = json.loads((REPO_ROOT / "agent-card.json").read_text(encoding="utf-8"))
    for c in card["commands"]:
        if c["name"] == "fix":
            c["risk_class"] = 0  # diverge from human Risk 2
    md_path = tmp_path / "AGENT_CARD.md"
    json_path = tmp_path / "agent-card.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(card), encoding="utf-8")
    result = check_card_sync(agent_card_md=md_path, agent_card_json=json_path)
    assert not result.ok
    assert any("risk_class[fix]" in d for d in result.divergences)


def test_cli_agentfacts_check_repo() -> None:
    runner = CliRunner()
    # Ensure committed manifest matches current cards
    from agent_control.agentfacts import build_manifest, write_manifest

    manifest = build_manifest(
        agent_card_md=REPO_ROOT / "docs" / "AGENT_CARD.md",
        agent_card_json=REPO_ROOT / "agent-card.json",
    )
    write_manifest(REPO_ROOT / "agent-facts.json", manifest)

    result = runner.invoke(main, ["agentfacts", "check", "--repo-root", str(REPO_ROOT)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True


def test_attach_integrity_hmac_roundtrip() -> None:
    raw = {
        "schema_version": "agent_facts.v1",
        "name": "n",
        "signed_by": "CT103",
        "signed_at_utc": "2026-07-20T00:00:00Z",
        "capabilities": {
            "commands": [],
            "blocked_commands": ["deploy"],
            "hosts": {"governance": "CT103", "execution": "CT104", "ci_truth": "CT102"},
        },
        "limitations": ["x"],
    }
    signed = attach_integrity(
        raw,
        agent_card_md_bytes=b"md",
        agent_card_json_bytes=b"{}",
        signing_secret="sec",
    )
    assert signed["integrity"]["hmac"]["sig"]
    assert not verify_integrity(
        signed,
        agent_card_md_bytes=b"md",
        agent_card_json_bytes=b"{}",
        signing_secret="sec",
        require_hmac=True,
    )
    bad = verify_integrity(
        signed,
        agent_card_md_bytes=b"md",
        agent_card_json_bytes=b"{}",
        signing_secret="wrong",
        require_hmac=True,
    )
    assert any("hmac" in e for e in bad)
