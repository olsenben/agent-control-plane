"""Gitea API client."""

from __future__ import annotations

from typing import Any

import httpx

from agent_control.config import Settings


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

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}")

    def get_issue(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}/issues/{issue_number}")

    def get_pull_diff(self, owner: str, repo: str, pr_number: int) -> str:
        return self._get_text(f"/repos/{owner}/{repo}/pulls/{pr_number}.diff")

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
