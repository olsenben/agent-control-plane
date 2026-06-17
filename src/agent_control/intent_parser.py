"""Parse explicit agent activation from Gitea comment bodies."""

from __future__ import annotations

import re

from agent_shared.models.intent import CommandIntent

_SLASH_AGENT = re.compile(
    r"^\s*/agent\s+(inspect|review|verify|fix|explain|plan|approve|reject|run)\b(?:\s+(.*))?$",
    re.IGNORECASE | re.DOTALL,
)
_MENTION_AGENT = re.compile(
    r"^\s*@agent-(reviewer|developer|ci-fixer|planner|verifier|explainer)\b(?:\s+(.*))?$",
    re.IGNORECASE | re.DOTALL,
)

_MENTION_TO_KIND: dict[str, str] = {
    "reviewer": "review",
    "developer": "fix",
    "ci-fixer": "fix",
    "planner": "plan",
    "verifier": "verify",
    "explainer": "explain",
}

_BARE_COMMAND_KINDS = frozenset({"inspect", "explain", "review", "plan"})

_WI_PATTERN = re.compile(r"^WI-\d{4,}$", re.IGNORECASE)


def parse_command_intent(body: str) -> CommandIntent:
    """Parse activation from comment body. Fail closed on ambiguous input."""
    text = (body or "").strip()
    if not text:
        return CommandIntent(activated=False, confidence=0.0)

    slash = _SLASH_AGENT.match(text)
    if slash:
        verb = slash.group(1).lower()
        rest = (slash.group(2) or "").strip()
        if verb in ("approve", "reject", "run"):
            wi_id = rest.split()[0] if rest else ""
            if not _WI_PATTERN.match(wi_id):
                return CommandIntent(activated=False, confidence=0.0)
            return CommandIntent(
                activated=True,
                activation="/agent",
                kind=verb,
                natural_language_task=wi_id,
                work_item_id=wi_id.upper(),
                confidence=1.0,
            )
        if not rest and verb in _BARE_COMMAND_KINDS:
            return CommandIntent(
                activated=True,
                activation="/agent",
                kind=verb,
                natural_language_task="",
                confidence=0.8 if verb == "inspect" else 1.0,
            )
        if not rest:
            return CommandIntent(activated=False, confidence=0.0)
        return CommandIntent(
            activated=True,
            activation="/agent",
            kind=verb,
            natural_language_task=rest,
            confidence=1.0,
        )

    mention = _MENTION_AGENT.match(text)
    if mention:
        role = mention.group(1).lower()
        rest = (mention.group(2) or "").strip()
        kind = _MENTION_TO_KIND.get(role)
        if not kind:
            return CommandIntent(activated=False, confidence=0.0)
        if not rest:
            return CommandIntent(activated=False, confidence=0.0)
        return CommandIntent(
            activated=True,
            activation=f"@agent-{role}",
            kind=kind,
            natural_language_task=rest,
            confidence=1.0,
        )

    return CommandIntent(activated=False, confidence=0.0)
