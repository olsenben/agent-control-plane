"""Gitea API client."""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import quote

import httpx

from agent_control.ci.gitea_actions_errors import GiteaActionsApiError, JobLogsResult, WorkflowJob
from agent_control.config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_LOG_BYTE_LIMIT = 2_000_000


class GiteaHttpError(Exception):
    """Status-aware Gitea HTTP failure for comment projection / API calls."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        retryable: bool = False,
        deleted: bool = False,
        ambiguous: bool = False,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.deleted = deleted
        self.ambiguous = ambiguous
        self.retry_after = retry_after


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

    def _put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1{path}"
        with httpx.Client(timeout=60.0) as client:
            resp = client.put(url, json=body, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def _patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """PATCH with status-aware errors for comment projection (V6 T02)."""
        url = f"{self.base_url}/api/v1{path}"
        with httpx.Client(timeout=60.0) as client:
            try:
                resp = client.patch(url, json=body, headers=self._headers())
            except httpx.TimeoutException as exc:
                raise GiteaHttpError(0, "timeout", retryable=True, ambiguous=True) from exc
            except httpx.TransportError as exc:
                raise GiteaHttpError(0, f"transport: {exc}", retryable=True) from exc
            if resp.status_code == 404:
                raise GiteaHttpError(404, "comment not found", retryable=False, deleted=True)
            if resp.status_code == 401 or resp.status_code == 403:
                raise GiteaHttpError(resp.status_code, "auth failed", retryable=False)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                raise GiteaHttpError(
                    429,
                    "rate limited",
                    retryable=True,
                    retry_after=int(retry_after) if retry_after and retry_after.isdigit() else None,
                )
            if resp.status_code >= 500:
                raise GiteaHttpError(resp.status_code, resp.text[:200], retryable=True)
            if resp.status_code >= 400:
                raise GiteaHttpError(resp.status_code, resp.text[:200], retryable=False)
            if not resp.content:
                return {}
            return resp.json()

    def patch_issue_comment(
        self,
        owner: str,
        repo: str,
        comment_id: int,
        body: str,
    ) -> dict[str, Any]:
        return self._patch(
            f"/repos/{owner}/{repo}/issues/comments/{comment_id}",
            {"body": body},
        )

    def get_issue_comment(self, owner: str, repo: str, comment_id: int) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}/issues/comments/{comment_id}")

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}")

    def user_has_repo_permission(
        self,
        owner: str,
        repo: str,
        username: str,
        *,
        need: str = "read",
    ) -> bool:
        """Return whether *username* has at least *need* access on the repo.

        Uses Gitea collaborator permission API when available; falls back to
        repository ``permissions`` for the authenticated bot when username
        matches acting identity. A 404 for any other user means no access
        (N07: collaborator revoke must deny).
        """
        need_l = (need or "read").lower()
        encoded_user = quote(username, safe="")
        url = (
            f"{self.base_url}/api/v1/repos/{owner}/{repo}/collaborators/"
            f"{encoded_user}/permission"
        )
        acting = (self.settings.gitea_acting_identity or "agent-bot").strip().lower()
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=self._headers())
                if resp.status_code == 404:
                    if str(username).strip().lower() != acting:
                        return False
                    # Acting bot may not appear as collaborator — use token repo perms.
                    repo_data = self.get_repo(owner, repo)
                    perms = repo_data.get("permissions") or {}
                    if need_l == "write":
                        return bool(perms.get("push") or perms.get("admin"))
                    return bool(perms.get("pull") or perms.get("push") or perms.get("admin"))
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return False
        perm = str(data.get("permission") or data.get("role_name") or "").lower()
        if need_l == "write":
            return perm in {"admin", "write", "owner"}
        return perm in {"admin", "write", "read", "owner"}

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

    def get_file_raw(self, owner: str, repo: str, path: str, *, ref: str) -> str | None:
        """Return file text at ref, or None if missing. Raises on other API errors."""
        encoded_path = quote(path, safe="/")
        encoded_ref = quote(ref, safe="")
        url = f"{self.base_url}/api/v1/repos/{owner}/{repo}/raw/{encoded_path}?ref={encoded_ref}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=self._headers())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text

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

    def create_branch(
        self,
        owner: str,
        repo: str,
        *,
        new_branch: str,
        old_branch: str,
    ) -> dict[str, Any]:
        """Create ``new_branch`` from ``old_branch`` (idempotent if already exists)."""
        try:
            return self._post(
                f"/repos/{owner}/{repo}/branches",
                {"new_branch_name": new_branch, "old_branch_name": old_branch},
            )
        except httpx.HTTPStatusError as exc:
            # 409 already exists — treat as success for propose retries
            if exc.response is not None and exc.response.status_code in (409, 422):
                return {"name": new_branch, "already_exists": True}
            raise

    def get_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        ref: str | None = None,
    ) -> dict[str, Any] | None:
        """GET file metadata (sha) at ref; None if missing."""
        encoded = quote(path, safe="/")
        url_path = f"/repos/{owner}/{repo}/contents/{encoded}"
        if ref:
            url_path += f"?ref={quote(ref, safe='')}"
        url = f"{self.base_url}/api/v1{url_path}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=self._headers())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None

    def create_or_update_file(
        self,
        owner: str,
        repo: str,
        *,
        path: str,
        content: str,
        message: str,
        branch: str,
    ) -> dict[str, Any]:
        """Create or update a file on ``branch`` via Contents API (base64 body)."""
        encoded = quote(path, safe="/")
        body: dict[str, Any] = {
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "message": message,
            "branch": branch,
        }
        existing = self.get_contents(owner, repo, path, ref=branch)
        api_path = f"/repos/{owner}/{repo}/contents/{encoded}"
        if existing and existing.get("sha"):
            body["sha"] = existing["sha"]
            return self._put(api_path, body)
        return self._post(api_path, body)

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

    @staticmethod
    def _actions_error_from_response(resp: httpx.Response) -> GiteaActionsApiError:
        code = resp.status_code
        retry_after: float | None = None
        if code == 429:
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    retry_after = float(ra)
                except ValueError:
                    retry_after = None
            return GiteaActionsApiError(
                "rate_limited",
                f"rate limited: {code}",
                status_code=code,
                retry_after=retry_after,
            )
        if code == 403:
            return GiteaActionsApiError("forbidden", "token capability problem", status_code=code)
        if code == 404:
            return GiteaActionsApiError(
                "not_found",
                "unsupported route or stale identifier",
                status_code=code,
            )
        if code >= 500:
            return GiteaActionsApiError("server_error", f"server error: {code}", status_code=code)
        if 300 <= code < 400:
            return GiteaActionsApiError("redirect", f"unexpected redirect: {code}", status_code=code)
        return GiteaActionsApiError("unknown", f"unexpected status: {code}", status_code=code)

    def list_workflow_run_jobs(
        self,
        owner: str,
        repo: str,
        run_id: str | int,
        *,
        require_nonempty_on_terminal: bool = False,
    ) -> list[WorkflowJob]:
        """GET .../actions/runs/{run}/jobs — fail-closed typed errors."""
        path = f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
        url = f"{self.base_url}/api/v1{path}"
        try:
            with httpx.Client(timeout=30.0, follow_redirects=False) as client:
                resp = client.get(url, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise GiteaActionsApiError("timeout", "list jobs timed out") from exc
        except httpx.HTTPError as exc:
            raise GiteaActionsApiError("unknown", f"list jobs http error: {exc}") from exc

        if resp.status_code != 200:
            raise self._actions_error_from_response(resp)

        try:
            data = resp.json()
        except ValueError as exc:
            raise GiteaActionsApiError("decode_error", "jobs response not json") from exc

        raw_jobs: list[Any]
        if isinstance(data, list):
            raw_jobs = data
        elif isinstance(data, dict):
            jobs = data.get("jobs") or data.get("workflow_jobs") or []
            raw_jobs = jobs if isinstance(jobs, list) else []
        else:
            raw_jobs = []

        if require_nonempty_on_terminal and not raw_jobs:
            raise GiteaActionsApiError(
                "empty_jobs",
                "terminal run returned empty jobs array (contract_mismatch)",
                status_code=200,
            )

        out: list[WorkflowJob] = []
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue
            jid = str(item.get("id") or item.get("job_id") or "")
            if not jid:
                continue
            out.append(
                WorkflowJob(
                    job_id=jid,
                    name=str(item.get("name") or ""),
                    status=str(item.get("status") or ""),
                    conclusion=str(item.get("conclusion") or ""),
                    run_id=str(item.get("run_id") or run_id),
                    raw=item,
                )
            )
        return out

    def download_job_logs(
        self,
        owner: str,
        repo: str,
        job_id: str | int,
        *,
        max_bytes: int = _DEFAULT_LOG_BYTE_LIMIT,
    ) -> JobLogsResult:
        """GET .../actions/jobs/{job_id}/logs with byte/time limits."""
        path = f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
        url = f"{self.base_url}/api/v1{path}"
        try:
            with httpx.Client(timeout=60.0, follow_redirects=False) as client:
                with client.stream("GET", url, headers=self._headers()) as resp:
                    if resp.status_code != 200:
                        # Drain minimally
                        try:
                            resp.read()
                        except Exception:
                            pass
                        raise self._actions_error_from_response(resp)
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if ctype and not any(
                        t in ctype
                        for t in ("text/", "octet-stream", "json", "application/zip", "")
                    ):
                        if "html" in ctype:
                            raise GiteaActionsApiError(
                                "unexpected_content_type",
                                f"unexpected content-type: {ctype}",
                                status_code=200,
                            )
                    cl_header = resp.headers.get("content-length")
                    source_len: int | None = None
                    if cl_header:
                        try:
                            source_len = int(cl_header)
                        except ValueError:
                            source_len = None
                        if source_len is not None and source_len > max_bytes * 4:
                            # Still allow streaming up to max_bytes; mark oversized intent
                            pass
                    chunks: list[bytes] = []
                    total = 0
                    truncated = False
                    for chunk in resp.iter_bytes():
                        if not chunk:
                            continue
                        if total + len(chunk) > max_bytes:
                            remain = max_bytes - total
                            if remain > 0:
                                chunks.append(chunk[:remain])
                                total += remain
                            truncated = True
                            break
                        chunks.append(chunk)
                        total += len(chunk)
                    body = b"".join(chunks)
                    return JobLogsResult(
                        job_id=str(job_id),
                        body=body,
                        content_type=ctype,
                        source_content_length=source_len,
                        truncated_by_limit=truncated,
                    )
        except GiteaActionsApiError:
            raise
        except httpx.TimeoutException as exc:
            raise GiteaActionsApiError("timeout", "job logs timed out") from exc
        except httpx.HTTPError as exc:
            raise GiteaActionsApiError("unknown", f"job logs http error: {exc}") from exc
