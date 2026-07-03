"""Backfill natural_language_task from issue body for bare review/plan commands."""

from __future__ import annotations

import re

from agent_control.graph.context_pack import ISSUE_BUDGET
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.intent import CommandIntent
from agent_workers.rlm.budget import truncate_text

_H1_TITLE_LINE = re.compile(r"^# [^\n]+$")


def issue_body_for_task(issue_text: str) -> str:
    """Strip leading compiler-style '# title' line; return body suitable for natural_language_task."""
    text = issue_text.strip()
    if not text:
        return ""

    first_newline = text.find("\n")
    first_line = text if first_newline == -1 else text[:first_newline]
    if not _H1_TITLE_LINE.match(first_line):
        return text

    title = first_line[2:].strip()
    body = text[len(first_line) :].strip()
    if body:
        return body
    return title


def maybe_backfill_command_intent(
    intent: CommandIntent,
    *,
    kind: str,
    context_pack: ContextPack | None,
    issue_number: int | None,
) -> CommandIntent:
    if kind not in ("review", "plan"):
        return intent
    if intent.natural_language_task.strip():
        return intent
    if issue_number is None or context_pack is None or not context_pack.issue_text:
        return intent

    task = issue_body_for_task(context_pack.issue_text)
    if not task.strip():
        return intent

    task = truncate_text(task, ISSUE_BUDGET)
    return intent.model_copy(update={"natural_language_task": task})
