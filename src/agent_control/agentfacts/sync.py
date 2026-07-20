"""Sync check: human AGENT_CARD.md vs machine agent-card.json."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


KNOWN_COMMANDS = ("inspect", "explain", "review", "plan", "fix")
BLOCKED_DEFAULT = ("deploy", "migrate", "secrets")


@dataclass
class SyncResult:
    ok: bool
    divergences: list[str] = field(default_factory=list)
    human: dict[str, Any] = field(default_factory=dict)
    machine: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "divergences": list(self.divergences),
            "human": self.human,
            "machine": self.machine,
        }


def _table_rows(md: str, heading: str) -> list[list[str]]:
    """Parse markdown pipe table immediately under ``## heading``."""
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, md, flags=re.MULTILINE)
    if not match:
        return []
    rest = md[match.end() :]
    next_h = re.search(r"^##\s+", rest, flags=re.MULTILINE)
    block = rest[: next_h.start()] if next_h else rest
    rows: list[list[str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and all(set(c) <= {"-", ":"} for c in cells):
            continue
        rows.append(cells)
    return rows[1:] if rows else []  # drop header


def extract_human_card(md_text: str) -> dict[str, Any]:
    """Extract comparable identity fields from AGENT_CARD.md."""
    name = "ai-sdlc-lab-control-plane"
    for row in _table_rows(md_text, "Identity"):
        if len(row) >= 2 and row[0].lower().replace("*", "") == "agent name":
            name = row[1].strip("`").strip()
            break

    commands: list[dict[str, Any]] = []
    for row in _table_rows(md_text, "Supported commands"):
        if len(row) < 6:
            continue
        cmd_raw = row[0].strip().strip("`")
        if not cmd_raw.startswith("/agent "):
            continue
        cmd_name = cmd_raw.replace("/agent ", "", 1).strip()
        autonomy = row[1]
        risk_m = re.search(r"Risk\s+(\d+)", autonomy, flags=re.IGNORECASE)
        risk_class = int(risk_m.group(1)) if risk_m else -1
        approval = row[5].lower()
        human_approval = "required" in approval and "none" not in approval
        commands.append(
            {
                "name": cmd_name,
                "risk_class": risk_class,
                "human_approval_required": human_approval,
            }
        )

    limitations: list[str] = []
    lim_match = re.search(
        r"^##\s+Known limitations\s*$", md_text, flags=re.MULTILINE
    )
    if lim_match:
        rest = md_text[lim_match.end() :]
        next_h = re.search(r"^##\s+", rest, flags=re.MULTILINE)
        block = rest[: next_h.start()] if next_h else rest
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("- "):
                limitations.append(line[2:].strip())

    blocked = list(BLOCKED_DEFAULT)
    for row in _table_rows(md_text, "Supported commands"):
        if row and "deploy" in row[0].lower():
            blocked = ["deploy", "migrate", "secrets"]
            break

    return {
        "name": name,
        "commands": commands,
        "blocked_commands": blocked,
        "limitations": limitations,
    }


def extract_machine_card(card: dict[str, Any]) -> dict[str, Any]:
    """Normalize agent-card.json into comparable fields."""
    commands = []
    for c in card.get("commands") or []:
        commands.append(
            {
                "name": c["name"],
                "risk_class": int(c["risk_class"]),
                "human_approval_required": bool(c.get("human_approval_required", False)),
            }
        )
    return {
        "name": card.get("name", ""),
        "commands": commands,
        "blocked_commands": list(card.get("blocked_commands") or []),
        "limitations_note": "machine card lists capabilities; limitations live in AGENT_CARD.md + agent-facts",
    }


def check_card_sync(
    *,
    agent_card_md: Path,
    agent_card_json: Path,
) -> SyncResult:
    """Fail when human and machine cards disagree on commands / risk / approval."""
    md_text = agent_card_md.read_text(encoding="utf-8")
    card = json.loads(agent_card_json.read_text(encoding="utf-8"))
    human = extract_human_card(md_text)
    machine = extract_machine_card(card)
    divergences: list[str] = []

    if human["name"] != machine["name"]:
        divergences.append(f"name: human={human['name']!r} machine={machine['name']!r}")

    human_cmds = {c["name"]: c for c in human["commands"]}
    machine_cmds = {c["name"]: c for c in machine["commands"]}
    for name in KNOWN_COMMANDS:
        h = human_cmds.get(name)
        m = machine_cmds.get(name)
        if h is None and m is None:
            divergences.append(f"command missing both sides: {name}")
            continue
        if h is None:
            divergences.append(f"command only in machine: {name}")
            continue
        if m is None:
            divergences.append(f"command only in human: {name}")
            continue
        if h["risk_class"] != m["risk_class"]:
            divergences.append(
                f"risk_class[{name}]: human={h['risk_class']} machine={m['risk_class']}"
            )
        if h["human_approval_required"] != m["human_approval_required"]:
            divergences.append(
                f"human_approval_required[{name}]: "
                f"human={h['human_approval_required']} machine={m['human_approval_required']}"
            )

    h_blocked = sorted(human["blocked_commands"])
    m_blocked = sorted(machine["blocked_commands"])
    if h_blocked != m_blocked:
        divergences.append(f"blocked_commands: human={h_blocked} machine={m_blocked}")

    # Machine card does not yet carry limitations; require human list non-empty.
    if not human["limitations"]:
        divergences.append("human Known limitations section empty")

    return SyncResult(
        ok=not divergences,
        divergences=divergences,
        human=human,
        machine=machine,
    )
