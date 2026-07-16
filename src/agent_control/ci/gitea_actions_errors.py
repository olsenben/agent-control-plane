"""Gitea Actions jobs/logs client errors and typed results (Slice 6F.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EvidenceFetchKind = Literal[
    "ok",
    "forbidden",
    "not_found",
    "rate_limited",
    "server_error",
    "timeout",
    "oversized",
    "unexpected_content_type",
    "empty_jobs",
    "redirect",
    "decode_error",
    "unknown",
]


class GiteaActionsApiError(Exception):
    def __init__(
        self,
        kind: EvidenceFetchKind,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass
class WorkflowJob:
    job_id: str
    name: str = ""
    status: str = ""
    conclusion: str = ""
    run_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobLogsResult:
    job_id: str
    body: bytes
    content_type: str = ""
    source_content_length: int | None = None
    truncated_by_limit: bool = False
