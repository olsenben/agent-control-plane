"""Parse explicit agent activation from Gitea comment bodies."""

from __future__ import annotations

import re

from agent_shared.approval_ids import parse_approval_target
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
# Bare review/plan on issue threads rely on issue-task backfill (slice 5.3) in dispatch
# to populate natural_language_task from context_pack.issue_text. Inspect intentionally
# does not backfill — it stays bounded to explicit comment text only.
_APPROVAL_COMMAND_KINDS = frozenset({"approve", "reject", "fix"})
_FINDING_PATTERN = re.compile(r"^F-\d+$", re.IGNORECASE)
_REASON_PATTERN = re.compile(r"\breason=(.+)$", re.IGNORECASE | re.DOTALL)


def _normalize_target(raw: str) -> str | None:
    parsed = parse_approval_target(raw.strip())
    if parsed is None:
        return None
    kind, issue_id, suffix = parsed
    if kind == "wi" and issue_id is not None:
        return f"WI-{issue_id:04d}-{suffix}"
    return f"PLAN-run-{suffix}"


def _parse_approval_rest(rest: str) -> tuple[str | None, str | None]:
    """Parse approval target and optional reject reason from command remainder."""
    text = rest.strip()
    if not text:
        return None, None
    reason_match = _REASON_PATTERN.search(text)
    reject_reason: str | None = None
    if reason_match:
        reject_reason = reason_match.group(1).strip() or None
        text = _REASON_PATTERN.sub("", text).strip()
    target_token = text.split()[0] if text else ""
    target = _normalize_target(target_token)
    return target, reject_reason


def _intent_with_target(
    *,
    kind: str,
    activation: str,
    target: str,
    reject_reason: str | None = None,
) -> CommandIntent:
    return CommandIntent(
        activated=True,
        activation=activation,
        kind=kind,
        natural_language_task=target,
        approval_target=target,
        work_item_id=target,
        reject_reason=reject_reason,
        confidence=1.0,
    )


def parse_command_intent(body: str) -> CommandIntent:
    """Parse activation from comment body. Fail closed on ambiguous input."""
    text = (body or "").strip()
    if not text:
        return CommandIntent(activated=False, confidence=0.0)

    slash = _SLASH_AGENT.match(text)
    if slash:
        verb = slash.group(1).lower()
        rest = (slash.group(2) or "").strip()

        if verb in _APPROVAL_COMMAND_KINDS:
            if not rest:
                return CommandIntent(activated=False, confidence=0.0)
            first_token = rest.split()[0]
            if _FINDING_PATTERN.match(first_token):
                return CommandIntent(activated=False, confidence=0.0)
            target, reject_reason = _parse_approval_rest(rest)
            if target is None:
                return CommandIntent(activated=False, confidence=0.0)
            return _intent_with_target(
                kind=verb,
                activation="/agent",
                target=target,
                reject_reason=reject_reason if verb == "reject" else None,
            )

        if verb == "run":
            wi_id = rest.split()[0] if rest else ""
            target = _normalize_target(wi_id)
            if target is None:
                return CommandIntent(activated=False, confidence=0.0)
            return _intent_with_target(kind=verb, activation="/agent", target=target)

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
        if kind == "fix":
            target = _normalize_target(rest.split()[0])
            if target is None:
                return CommandIntent(activated=False, confidence=0.0)
            return _intent_with_target(kind=kind, activation=f"@agent-{role}", target=target)
        return CommandIntent(
            activated=True,
            activation=f"@agent-{role}",
            kind=kind,
            natural_language_task=rest,
            confidence=1.0,
        )

    return CommandIntent(activated=False, confidence=0.0)
