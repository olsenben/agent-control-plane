"""FastAPI Gitea webhook guard."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response

from agent_control.config import Settings
from agent_control.event_types import canonical_gitea_event_type
from agent_control.events import AgentEvent, append_event, deterministic_event_id, write_reduction_outbox
from agent_control.queue import enqueue_state_reduction
from agent_control.readiness import build_readiness_report

logger = logging.getLogger(__name__)

PUBLIC_ALLOWED_PATHS = {"/healthz", "/readyz", "/webhooks/gitea"}

ALLOWED_EVENTS = {
    "issues",
    "issue_comment",
    "issue_label",
    "pull_request",
    "pull_request_sync",
    "pull_request_comment",
    "push",
    "workflow_run",
    "workflow_job",
}


def verify_hmac(secret: str, body: bytes, signature: str) -> bool:
    """Verify Gitea/GitHub webhook HMAC-SHA256 signatures.

    Gitea sends raw hex in X-Gitea-Signature; GitHub-compatible X-Hub-Signature-256
    uses a sha256= prefix. Accept both.
    """
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    from agent_control.telemetry import init_telemetry

    init_telemetry(service_name="agent-control-plane")
    app = FastAPI(title="agent-control-plane")

    @app.middleware("http")
    async def restrict_public_surface(request: Request, call_next):
        if settings.enforce_public_surface_restriction:
            path = request.url.path
            if path not in PUBLIC_ALLOWED_PATHS and not path.startswith(
                ("/observe", "/api/observe")
            ):
                return Response(status_code=404)
        return await call_next(request)

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
        if not settings.is_repo_allowed(full_name):
            raise HTTPException(status_code=403, detail="repo not allowed")

        canonical_type, raw_action = canonical_gitea_event_type(x_gitea_event, payload)
        event_id = deterministic_event_id("gitea", x_gitea_delivery, canonical_type)
        event = AgentEvent(
            event_id=event_id,
            type=canonical_type,
            raw_event_type=x_gitea_event,
            raw_action=raw_action,
            delivery_id=x_gitea_delivery,
            project=full_name,
            payload=payload,
        )
        path, created = append_event(settings.agent_state_root, event)
        if created:
            try:
                enqueue_state_reduction(
                    settings.redis_url,
                    event.event_id,
                    event.project,
                    str(settings.agent_state_root),
                )
            except Exception:
                logger.exception(
                    "failed to enqueue state reduction for %s", event.event_id
                )
                write_reduction_outbox(
                    settings.agent_state_root,
                    event.event_id,
                    event.project,
                )

        return {"status": "accepted", "event_id": event_id, "path": str(path)}

    app.state.settings = settings
    from agent_control.observe.routes import register_observe_routes

    register_observe_routes(app)
    return app
