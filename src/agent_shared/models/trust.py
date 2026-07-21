"""Context provenance trust classification (V6 T01)."""

from __future__ import annotations

from typing import Literal

TrustClass = Literal[
    "trusted_policy",
    "trusted_human_instruction",
    "untrusted_issue_content",
    "untrusted_repo_content",
    "untrusted_comment",
    "untrusted_log",
    "untrusted_test_output",
    "model_generated",
]

TRUSTED_AUTHORITY_CLASSES: frozenset[str] = frozenset(
    {"trusted_policy", "trusted_human_instruction"}
)
