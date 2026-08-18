"""Prompt preamble and summary budget helpers."""

from agent_shared.constants import GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS
from agent_workers.rlm.budget import fit_summary_for_comment
from agent_workers.rlm.prompts import build_fix_system_preamble, build_system_preamble


def test_preamble_includes_character_budget() -> None:
    preamble = build_system_preamble("explain", "read_only")
    assert str(GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS) in preamble
    assert "Gitea issue comment" in preamble


def test_preamble_custom_budget() -> None:
    preamble = build_system_preamble("inspect", "read_only", max_summary_chars=1200)
    assert "1200 characters" in preamble


def test_fit_summary_for_comment_within_budget() -> None:
    text = "Short answer."
    assert fit_summary_for_comment(text, 100) == text


def test_fit_summary_for_comment_truncates_with_marker() -> None:
    text = "word " * 900
    fitted = fit_summary_for_comment(text, 500)
    assert len(fitted) <= 500
    assert fitted.endswith("[Summary truncated to fit Gitea comment limit.]")


def test_fix_preamble_without_prior_memory_has_no_mem_citation_protocol() -> None:
    preamble = build_fix_system_preamble("fix", "write_patch")
    assert "memory_id" not in preamble
    assert "mem-*" not in preamble
    assert "prior_memory" not in preamble
    assert "do not invent a citation" not in preamble


def test_fix_preamble_with_prior_memory_mentions_memory_id_and_abstain() -> None:
    preamble = build_fix_system_preamble("fix", "write_patch", has_prior_memory=True)
    assert "memory_id" in preamble
    assert "mem-*" in preamble
    assert "prior_memory" in preamble
    assert "do not invent a citation" in preamble
    assert "hypotheses" in preamble
