"""Map context sources to trust_class labels (V6 T01)."""

from __future__ import annotations

from agent_shared.models.trust import TrustClass

_SOURCE_TO_TRUST: dict[str, TrustClass] = {
    "gitea_issue": "untrusted_issue_content",
    "gitea_issue_override": "untrusted_issue_content",
    "gitea_pr_diff": "untrusted_repo_content",
    "graph_blast_radius": "untrusted_repo_content",
    "adr_slice": "trusted_policy",
    "memory_retrieval": "model_generated",
    "ripgrep_search": "untrusted_repo_content",
    "trusted_human_instruction": "trusted_human_instruction",
}


def trust_class_for_source(source: str) -> TrustClass:
    return _SOURCE_TO_TRUST.get(source, "untrusted_repo_content")


def build_provenance_items(sources: list[str]) -> list[dict[str, str]]:
    return [{"source": s, "trust_class": trust_class_for_source(s)} for s in sources]
