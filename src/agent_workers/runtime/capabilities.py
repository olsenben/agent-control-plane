"""Detect runtime capabilities for a worker run."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from agent_shared.models.session import Capabilities
from agent_workers.settings import WorkerSettings


def detect_capabilities(
    settings: WorkerSettings,
    run_id: str,
    workspace: Path,
    model_policy: str,
    warnings: list[str] | None = None,
) -> Capabilities:
    warnings = warnings or []
    repo_clone = settings.git_ro_key_path is None or settings.git_ro_key_path.exists()
    if not repo_clone:
        warnings.append("git read-only key not found; repo clone may fail")
    gitea_comment = bool(settings.gitea_agent_token and settings.gitea_agent_comment_enabled)
    compiled = (workspace / ".agent" / "context").exists() if workspace.exists() else False
    index = (workspace / ".agent" / "generated").exists() if workspace.exists() else False
    model_endpoint = "not_required_fake_engine" if model_policy == "fake" else "configured"
    if model_policy == "official":
        model_endpoint = "official_rlm_candidate"
    return Capabilities(
        run_id=run_id,
        repo_clone=repo_clone,
        ripgrep=shutil.which("rg") is not None,
        sandbox=False,
        model_endpoint=model_endpoint,
        gitea_comment=gitea_comment,
        context_index=index,
        compiled_context=compiled,
        network=False,
        warnings=warnings,
    )


def python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
