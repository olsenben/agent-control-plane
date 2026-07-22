"""Observatory public link helpers (V9 T06, H8 OBSERVE_PUBLIC_BASE_URL fail-closed).

``OBSERVE_PUBLIC_BASE_URL`` is unset by default (see
``agent_control.config.Settings.observe_public_base_url`` and its
``validate_observe_public_base_url`` startup validator for the https/shape
checks). Every function in this module treats "unset", "malformed", or
"``run_id`` not URL-safe" identically: return ``None`` (never a link), so a
Gitea comment or the ``docs/gitea-custom/extra_tabs.tmpl`` snippet omits the
Observe link entirely rather than guess a LAN/HTTP address or interpolate an
unvalidated ``run_id`` into a URL. See
``docs/slice-v9-t06-observe-public-links.md``.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from agent_control.config import Settings, get_settings

logger = logging.getLogger(__name__)

# run_id producers in this codebase: make_run_id() ("run-<32 hex chars>",
# agent_shared.project_ids), make_rlm_root_job_id(), approval/dispatch_fix.py's
# fix_run_id, and assorted test/CLI callers. This allowlist accepts every one
# of those shapes while rejecting anything that could break out of a URL path
# segment or a Markdown link/code span -- whitespace, "/", backticks,
# brackets, parentheses, and other control/punctuation characters.
_RUN_ID_URL_SAFE_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def is_url_safe_run_id(run_id: str | None) -> bool:
    """True if *run_id* is safe to interpolate into an Observatory URL."""
    return bool(run_id) and bool(_RUN_ID_URL_SAFE_RE.match(run_id))


def observe_public_base_url_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool((settings.observe_public_base_url or "").strip())


def observe_session_path(run_id: str) -> str:
    """Relative Observatory session path (matches ``observe/routes.py``)."""
    return f"/observe/sessions/{quote(run_id, safe='')}"


def observe_repo_path(project: str) -> str:
    """Relative Observatory repo path for the Gitea ``extra_tabs`` link."""
    owner, _, repo = project.partition("/")
    return f"/observe/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"


def build_observe_session_url(run_id: str, settings: Settings | None = None) -> str | None:
    """Absolute Observatory session URL, or ``None`` if it must be omitted.

    Fails closed on every axis: an unset base URL and a ``run_id`` that does
    not match the conservative URL-safe allowlist both return ``None`` rather
    than guess or half-render a link.
    """
    settings = settings or get_settings()
    base = (settings.observe_public_base_url or "").strip()
    if not base:
        return None
    if not is_url_safe_run_id(run_id):
        logger.warning("observe_public_url_unsafe_run_id run_id=%r", run_id)
        return None
    return f"{base.rstrip('/')}{observe_session_path(run_id)}"


def observe_link_line(run_id: str, settings: Settings | None = None) -> str | None:
    """One ``Observe: <url>`` Markdown line for a Gitea comment, or ``None``.

    Callers must append this line only when it is not ``None`` -- there is
    no relative-path fallback; an unset/invalid base URL means the Observe
    link is omitted from the comment entirely (H8 fail-closed).
    """
    url = build_observe_session_url(run_id, settings=settings)
    if not url:
        return None
    return f"Observe: {url}"


def observe_config_warning(settings: Settings | None = None) -> str | None:
    """Human-readable warning surfaced at startup and via ``/readyz``.

    Returns ``None`` once ``OBSERVE_PUBLIC_BASE_URL`` is configured.
    """
    if observe_public_base_url_configured(settings):
        return None
    return (
        "OBSERVE_PUBLIC_BASE_URL is unset -- Observatory links are omitted "
        "from Gitea comments and docs/gitea-custom/extra_tabs.tmpl stays "
        "inert until a human sets it (fail-closed; no LAN/HTTP default is "
        "assumed)."
    )
