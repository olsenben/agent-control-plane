"""Live/offline Gitea Actions jobs+logs contract probe (Slice 6F.1 prerequisite)."""

from __future__ import annotations

import argparse
import json
import sys

from agent_control.ci.gitea_actions_errors import GiteaActionsApiError
from agent_control.config import Settings
from agent_control.gitea_client import GiteaClient


def probe(owner: str, repo: str, run_id: str, settings: Settings | None = None) -> dict:
    client = GiteaClient(settings or Settings())
    result: dict = {
        "owner": owner,
        "repo": repo,
        "workflow_run_id": run_id,
        "jobs_route": f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
        "jobs_http_status": None,
        "jobs_count": None,
        "jobs_kind": None,
        "logs_checked": 0,
        "notes": [],
    }
    try:
        jobs = client.list_workflow_run_jobs(owner, repo, run_id, require_nonempty_on_terminal=False)
        result["jobs_http_status"] = 200
        result["jobs_count"] = len(jobs)
        if not jobs:
            result["jobs_kind"] = "empty_jobs"
            result["notes"].append("empty jobs array — treat as contract_mismatch on terminal fail")
        else:
            result["jobs_kind"] = "ok"
            job = jobs[0]
            try:
                logs = client.download_job_logs(owner, repo, job.job_id)
                result["logs_checked"] = 1
                result["logs_content_type"] = logs.content_type
                result["logs_bytes"] = len(logs.body)
                result["notes"].append(
                    "job logs may be combined multi-step streams; retain as-is"
                )
            except GiteaActionsApiError as exc:
                result["notes"].append(f"logs_error:{exc.kind}:{exc.status_code}")
    except GiteaActionsApiError as exc:
        result["jobs_http_status"] = exc.status_code
        result["jobs_kind"] = exc.kind
        result["notes"].append(str(exc))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe Gitea Actions jobs/logs contract")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    out = probe(args.owner, args.repo, args.run_id)
    print(json.dumps(out, indent=2))
    if out.get("jobs_kind") in ("empty_jobs", "forbidden", "not_found", "server_error"):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
