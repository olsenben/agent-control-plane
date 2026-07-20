"""V5 T06 — gated self-improvement (prompt/workflow proposals as PRs only)."""

from agent_control.self_improve.gate import (
    evaluate_in_prod_self_edit,
    evaluate_proposal_eligibility,
    is_production_deploy_root,
)
from agent_control.self_improve.paths import (
    GATED_SELF_IMPROVE_GLOBS,
    classify_paths,
    is_gated_self_improve_path,
)
from agent_control.self_improve.propose import (
    FileProposal,
    propose_probe_pr,
    propose_self_improve,
)

__all__ = [
    "GATED_SELF_IMPROVE_GLOBS",
    "FileProposal",
    "classify_paths",
    "evaluate_in_prod_self_edit",
    "evaluate_proposal_eligibility",
    "is_gated_self_improve_path",
    "is_production_deploy_root",
    "propose_probe_pr",
    "propose_self_improve",
]
