"""Periodic and watch-based inbox ingest backup (Slice 4C)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from agent_control.config import Settings, get_settings
from agent_control.results_ingest import ct104_inbox_dir, ingest_inbox, ingest_result_file

logger = logging.getLogger(__name__)


def ingest_watch_loop(
    state_root: Path,
    *,
    sweep_interval_seconds: int = 120,
    settings: Settings | None = None,
) -> None:
    """Backup ingest: watchfiles when available, periodic sweep always."""
    settings = settings or get_settings()
    inbox = ct104_inbox_dir(state_root)
    inbox.mkdir(parents=True, exist_ok=True)

    try:
        from watchfiles import watch

        logger.info("ingest-watch: starting watchfiles on %s", inbox)
        last_sweep = time.monotonic()
        for changes in watch(inbox, debounce=2000, step=500):
            for _change_type, path_str in changes:
                path = Path(path_str)
                if path.suffix != ".json" or path.name.endswith(".processed"):
                    continue
                try:
                    ingest_result_file(state_root, path, settings=settings)
                except Exception as exc:
                    logger.warning("ingest-watch file %s failed: %s", path, exc)
            now = time.monotonic()
            if now - last_sweep >= sweep_interval_seconds:
                ingest_inbox(state_root, settings=settings)
                last_sweep = now
    except ImportError:
        logger.warning("watchfiles not installed; ingest-watch using sweep only")
        while True:
            ingest_inbox(state_root, settings=settings)
            time.sleep(sweep_interval_seconds)
