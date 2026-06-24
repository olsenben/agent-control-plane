"""Closed-world diff policy and gate (Slice 6C)."""

from agent_shared.closed_world.gate import evaluate_diff_gate
from agent_shared.closed_world.loader import load_closed_world_policy
from agent_shared.closed_world.policy import ClosedWorldPolicy, path_matches_glob

__all__ = [
    "ClosedWorldPolicy",
    "evaluate_diff_gate",
    "load_closed_world_policy",
    "path_matches_glob",
]
