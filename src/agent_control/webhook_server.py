"""FastAPI Gitea webhook guard."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response

from agent_control.config import Settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.readiness import build_readiness_report

ALLOWED_EVENTS = {
    "issues",
    "issue_comment",
    "pull_request",
    "pull_request_comment",
    "push",
    "workflow_run",
    "workflow_job",
}


def verify_hmac(secret: str, body: bytes, signature: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="agent-control-plane")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(
        response: Response,
        strict: bool = Query(default=False),
    ) -> dict[str, Any]:
        use_strict = strict or settings.model_health_required_for_readyz
        body, status_code = build_readiness_report(settings, strict=use_strict)
        response.status_code = status_code
        return body

    @app.post("/webhooks/gitea")
    async def gitea_webhook(
        request: Request,
        x_gitea_signature: str = Header(alias="X-Gitea-Signature"),
        x_gitea_delivery: str = Header(alias="X-Gitea-Delivery"),
        x_gitea_event: str = Header(alias="X-Gitea-Event"),
    ) -> dict[str, Any]:
        if request.method != "POST":
            raise HTTPException(status_code=405)
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            raise HTTPException(status_code=415, detail="application/json required")
        body = await request.body()
        if not settings.gitea_webhook_secret:
            raise HTTPException(status_code=503, detail="webhook secret not configured")
        if not verify_hmac(settings.gitea_webhook_secret, body, x_gitea_signature):
            raise HTTPException(status_code=401, detail="invalid signature")
        if x_gitea_event not in ALLOWED_EVENTS:
            raise HTTPException(status_code=400, detail="event type not allowed")
        payload = json.loads(body)
        repo = payload.get("repository", {})
        full_name = repo.get("full_name", "")
        if full_name not in settings.allowed_repos_set():
            raise HTTPException(status_code=403, detail="repo not allowed")
        event_type = f"gitea.{x_gitea_event.replace('.', '_')}"
        event_id = deterministic_event_id("gitea", x_gitea_delivery, event_type)
        event = AgentEvent(
            event_id=event_id,
            type=event_type,
            delivery_id=x_gitea_delivery,
            project=full_name,
            payload=payload,
        )
        path = append_event(settings.agent_state_root, event)
        return {"status": "accepted", "event_id": event_id, "path": str(path)}

    return app
