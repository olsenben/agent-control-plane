#!/usr/bin/env python3
"""Push all tracked files to Gitea via Contents API. Set GITEA_TOKEN env var."""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path

import httpx

OWNER = "ai-sdlc-lab"
REPO = "agent-control-plane"
BRANCH = "main"
BASE = os.environ.get("GITEA_BASE_URL", "https://git.ham-sup-lo.com").rstrip("/")
TOKEN = os.environ.get("GITEA_TOKEN", "")


def main() -> int:
    if not TOKEN:
        print("Set GITEA_TOKEN (PAT with repo write scope)", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parents[1]
    files = subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
    headers = {"Authorization": f"token {TOKEN}"}
    verify = os.environ.get("GITEA_SSL_VERIFY", "true").lower() not in ("0", "false", "no")
    with httpx.Client(base_url=f"{BASE}/api/v1", headers=headers, verify=verify, timeout=60.0) as client:
        for path in files:
            full = root / path
            content_b64 = base64.b64encode(full.read_bytes()).decode("ascii")
            r = client.get(f"/repos/{OWNER}/{REPO}/contents/{path}", params={"ref": BRANCH})
            sha = r.json().get("sha") if r.status_code == 200 else None
            body = {
                "message": f"feat(control): sync {path}",
                "content": content_b64,
                "branch": BRANCH,
            }
            if sha:
                body["sha"] = sha
            resp = client.request(
                "POST" if sha is None else "PUT",
                f"/repos/{OWNER}/{REPO}/contents/{path}",
                json=body,
            )
            if resp.status_code not in (200, 201):
                print(f"FAIL {path}: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
                return 1
            print(f"OK {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
