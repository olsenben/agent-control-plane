"""Gitea API client."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from agent_control.config import Settings

logger = logging.getLogger(__name__)


class GiteaClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.base_url = self.settings.gitea_base_url.rstrip("/")
        self.token = self.settings.gitea_bot_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self.token}"} if self.token else {}

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1{path}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def _get_text(self, path: str) -> str:
        url = f"{self.base_url}/api/v1{path}"
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.text

    def _post(self, path: str, body: dict[str, Any], *, run_id: str | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1{path}"
        if run_id:
            logger.info("gitea_api_post run_id=%s path=%s", run_id, path)
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json=body, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}")

    def get_issue(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}/issues/{issue_number}")

    def get_pull_diff(self, owner: str, repo: str, pr_number: int) -> str:
        return self._get_text(f"/repos/{owner}/{repo}/pulls/{pr_number}.diff")

    def get_branch(self, owner: str, repo: str, branch: str) -> dict[str, Any]:
        encoded = quote(branch, safe="")
        return self._get(f"/repos/{owner}/{repo}/branches/{encoded}")

    def get_branch_sha(self, owner: str, repo: str, branch: str) -> str:
        data = self.get_branch(owner, repo, branch)
        commit = data.get("commit") or {}
        return str(commit.get("id") or commit.get("sha") or "")

    def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        head: str | None = None,
        state: str = "open",
    ) -> list[dict[str, Any]]:
        query = f"/repos/{owner}/{repo}/pulls?state={state}&limit=50"
        if head:
            query += f"&head={quote(head, safe='')}"
        url = f"{self.base_url}/api/v1{query}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return []

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        head: str,
        base: str,
        title: str,
        body: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        return self._post(
            f"/repos/{owner}/{repo}/pulls",
            {"title": title, "body": body, "head": head, "base": base},
            run_id=run_id,
        )

    async def post_issue_comment_async(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/repos/{owner}/{repo}/issues/{issue_number}/comments"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"body": body}, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def get_workflow_run(self, owner: str, repo: str, run_id: str | int) -> dict[str, Any]:
        """GET /repos/{owner}/{repo}/actions/runs/{run} — authoritative Actions state."""
        return self._get(f"/repos/{owner}/{repo}/actions/runs/{run_id}")

    def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        *,
        head_sha: str | None = None,
        status: str | None = None,
        branch: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """GET /repos/{owner}/{repo}/actions/runs with optional head_sha filter."""
        from urllib.parse import urlencode

        params: dict[str, str | int] = {"limit": limit}
        if head_sha:
            params["head_sha"] = head_sha
        if status:
            params["status"] = status
        if branch:
            params["branch"] = branch
        query = urlencode(params)
        data = self._get(f"/repos/{owner}/{repo}/actions/runs?{query}")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            runs = data.get("workflow_runs") or data.get("runs") or []
            if isinstance(runs, list):
                return runs
        return []
