# Gitea custom templates -- Agent Observatory tab (V9 T06)

This directory ships one Gitea "customizing" file --
[`extra_tabs.tmpl`](extra_tabs.tmpl) -- that adds an **Observatory** tab to
the repository header on CT100 (Gitea), linking to the control plane's
`/observe/repos/{owner}/{repo}` route. It is installed by copying it into
Gitea's `$GITEA_CUSTOM/templates/custom/` directory and restarting Gitea; it
is **not** part of the `agent-control-plane` deploy and has no runtime
dependency on this repo beyond the URL it points at.

## Why this is separate from OBSERVE_PUBLIC_BASE_URL fail-closed (H8)

`OBSERVE_PUBLIC_BASE_URL` (see `docs/slice-v9-t06-observe-public-links.md`)
governs Observe links **agent-control-plane itself emits** (Gitea comments):
those are computed per-request from `Settings.observe_public_base_url` and
fail closed automatically (omitted) when unset.

Gitea's own Go templates have no access to agent-control-plane's
environment, so `extra_tabs.tmpl` cannot look `OBSERVE_PUBLIC_BASE_URL` up
live -- the base URL must be substituted into the file's text once, by a
human, before install. **The fail-closed rule for this file is
operational, not automatic: do not install it while `OBSERVE_PUBLIC_BASE_URL`
is unset on CT103, and re-edit + restart Gitea if that value ever changes.**
An un-installed file is exactly equivalent to "no tab" -- the safe default.

## Version pin

Verified against the live homelab Gitea instance:

```text
$ curl -s https://git.ham-sup-lo.com/api/v1/version
{"version":"1.26.2"}
```

Checked 2026-07-21. Re-run this command and repeat the spike below (see
"Upgrade checklist") whenever CT100's Gitea version changes.

## Template context spike (2026-07-21, tag `v1.26.2`)

No CT100 filesystem/SSH access is available from this development
environment (only CT103/CT104 are in the documented homelab SSH surface),
so the spike below was performed by reading Gitea's own upstream source at
the pinned tag rather than a live install-and-verify on CT100. The **human
install step records the actual live confirmation** (see "Install on
CT100" below).

1. **Insertion point.** `templates/repo/header.tmpl` (tag `v1.26.2`)
   calls `{{template "custom/extra_tabs" .}}` once, right after the
   built-in "Activity" tab and before the "Settings" tab, inside the
   `{{if not (or .Repository.IsBeingCreated .Repository.IsBroken)}}` block.
   The `.` passed to `custom/extra_tabs` is the same page-context value
   used for every sibling tab in that block (it exposes `.Repository`,
   `.Permission`, etc. directly, confirmed by neighboring calls like
   `.Permission.CanRead ctx.Consts.RepoUnitTypeCode` in the same scope).
2. **Repo identity fields.** `models/repo/repo.go` (tag `v1.26.2`) declares
   `Repository.OwnerName string` and `Repository.Name string` as plain
   exported fields (not methods), and `Repository.FullName()` returns
   `OwnerName + "/" + Name`. `extra_tabs.tmpl` therefore uses
   `{{.Repository.OwnerName}}` and `{{.Repository.Name}}` directly, matching
   `agent-control-plane`'s own `"{owner}/{repo}"` project-id convention
   (`agent_shared.project_ids.split_project`).
3. **Icon helper.** `{{svg "octicon-pulse"}}` is already used by the
   built-in "Activity" tab in the same `header.tmpl`, so it is a
   proven-available helper in this exact template context (not a guess).
4. **Reproduce / verify against a newer tag:**

   ```bash
   curl -s https://raw.githubusercontent.com/go-gitea/gitea/v1.26.2/templates/repo/header.tmpl \
     | sha256sum
   curl -s https://raw.githubusercontent.com/go-gitea/gitea/v1.26.2/models/repo/repo.go \
     | sha256sum
   ```

   Recorded checksums for `v1.26.2` (fetched 2026-07-21 via this
   environment's HTTPS client; re-run the commands above to independently
   confirm before trusting a byte-for-byte match, since `curl`/proxies can
   differ from other HTTP clients in line-ending handling):

   | File | sha256 |
   |---|---|
   | `templates/repo/header.tmpl` | `95542ee9612d167dc10fade1d860fb919a3359172d9eb47ebc3513efe145b5ab`[^len] |
   | `models/repo/repo.go` | `7cee19e44818cf0fe21ecd2e55c0f8beaed34dd7f561bcec344e2fe291c891c2`[^len] |

   [^len]: Both are 64 hex characters (32-byte SHA-256 digests); re-wrap if
       your terminal/font makes the length hard to eyeball.
5. **Live confirmation method (Gitea's own recommended approach, not yet
   run against CT100):** temporarily set `RUN_MODE = dev` in CT100's
   `app.ini`, add `{{ $ | DumpVar }}` to a scratch copy of the template,
   restart Gitea, load any repo page, and inspect the dumped context to
   confirm `.Repository.OwnerName`/`.Repository.Name` resolve as expected
   on the live instance before relying on this file in production. Revert
   `RUN_MODE` to `prod` afterwards.

## Install on CT100 (human required)

Gitea customization files live under Gitea's `$GITEA_CUSTOM` directory on
the Gitea host/container itself (CT100, `192.168.4.60`), which is outside
this repo's documented SSH surface (only CT103/CT104 are; see
`.cursor/rules/ssh-ct103-ct104.mdc`). A human with CT100 access must:

1. Find `$GITEA_CUSTOM` on CT100: `gitea help` (look for the `CustomPath`
   value) or check **Site Administration -> Configuration** in the Gitea
   UI.
2. Copy [`extra_tabs.tmpl`](extra_tabs.tmpl) to
   `$GITEA_CUSTOM/templates/custom/extra_tabs.tmpl`.
3. Edit the copy: replace `OBSERVE_PUBLIC_BASE_URL_PLACEHOLDER` with the
   exact value configured as `OBSERVE_PUBLIC_BASE_URL` in CT103's
   `agent-control-plane/.env` (no trailing slash).
4. Restart Gitea (`gitea` requires a full restart to pick up `custom/`
   changes).
5. Open any repo in the browser; confirm an **Observatory** tab appears
   after **Activity** and links to
   `<OBSERVE_PUBLIC_BASE_URL>/observe/repos/<owner>/<repo>`.
6. Note: that route currently returns the raw JSON session list (V9 T04's
   five-panel HTML UI is per-session, `/observe/sessions/{run_id}`, not
   per-repo) -- a repo-level HTML landing page is a documented non-goal of
   this ticket, not a defect. Authenticated users still get useful,
   auth-gated data; unauthenticated users get the same 401/redirect/403
   the rest of the Observatory enforces.
7. Reply to the coordinator with: Gitea version confirmed, tab rendered
   (yes/no), link target seen in the browser (do not paste tokens/cookies).

## Upgrade checklist (repeat when CT100's Gitea version changes)

1. `curl -s https://<gitea-host>/api/v1/version` -- record the new version.
2. Re-fetch `templates/repo/header.tmpl` and `models/repo/repo.go` at the
   matching upstream tag; diff against the checksums recorded above.
3. Confirm `{{template "custom/extra_tabs" .}}` still exists at the same
   (or an equivalent) insertion point, and that `.Repository.OwnerName`/
   `.Repository.Name` are still valid fields in that context.
4. If either changed, update `extra_tabs.tmpl` and this checklist's
   checksums/version pin in the same change.
5. Re-run the live confirmation method (step 5 of the spike above) on
   CT100 after the Gitea upgrade, before trusting the tab in production.

## Non-goals

- No agent-driven install onto CT100 (no SSH/filesystem access from this
  environment to that host).
- No live env-var lookup from inside a Gitea template -- the base URL is a
  one-time human substitution, documented above.
- No repo-level HTML Observatory page (only the per-session five-panel UI
  from V9 T04 exists today); the tab links to the existing JSON API route.
