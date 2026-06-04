"""Gitea API client (stub; httpx calls added in later phases)."""

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

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        raise NotImplementedError("Gitea API not wired in skeleton")

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
