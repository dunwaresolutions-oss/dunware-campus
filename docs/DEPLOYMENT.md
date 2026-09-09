# Campus — Deployment (on-site)

Campus ships as **one Windows installer**, `Campus-Setup.exe`. There is no
Docker, Python, or Node requirement on the target machine — everything is
inside the installer. How the installer itself is built (PyInstaller freeze,
Inno Setup compile, the real bugs that were found and fixed doing it for
real) is `docs/PACKAGING.md`; this document is the operator-facing side —
what a machine needs before install, and what to do after.

## Target machine

- Windows 10/11 x64 (or Windows Server 2019+), on the school's own network.
- ~4 GB free disk for the app + a growing database.
- **Disk encryption on** (BitLocker). The installer checks and warns loudly if
  not — this box will hold children's PII.
- LAN-only by default. Off-premises access is **opt-in**, provisioned
  separately with `deploy\remote-setup.ps1` (Cloudflare Tunnel / WireGuard /
  plain gateway) — see **Remote access** below and
  `docs/REMOTE_ACCESS_AND_YOUR_DATA.md`.

## Third-party binaries (stage before a real install)

Two binaries and one service-shim ship **inside the installer if staged, but
are never fetched or committed** by this repo — `deploy/_thirdparty/` is
gitignored. Without them, `Campus-Setup.exe` still installs and the app
files/secrets/`.env`/Caddyfile are all laid out correctly, but the database
and the two Windows services are skipped with a clear message instead of
being registered — see `docs/PACKAGING.md` for the drill that proved this.

| What | Stage it at | Get it from | License |
|---|---|---|---|
| PostgreSQL 16, portable Windows zip build | `deploy/_thirdparty/pgsql/` (`pgsql/bin/initdb.exe` etc.) | https://www.enterprisedb.com/download-postgresql-binaries | PostgreSQL License |
| Caddy, Windows amd64 | `deploy/_thirdparty/caddy/caddy.exe` | https://caddyserver.com/download | Apache 2.0 |
| NSSM — wraps `caddy.exe`/`campus-app.exe` as Windows services (neither speaks the Windows Service Control Protocol itself; `pg_ctl register` does, so Postgres needs no such shim) | `deploy/_thirdparty/caddy/nssm.exe` | https://nssm.cc/download | Public domain / permissive |
| **Remote access only** — `cloudflared.exe` and/or `wireguard.exe` + `wg.exe`. Needed *only* for a site that will run `remote-setup.ps1`; a LAN-only install ignores their absence exactly like the row above. | `deploy/_thirdparty/remote/` → `{app}\remote\bin` | https://github.com/cloudflare/cloudflared/releases · https://www.wireguard.com/install/ | Apache 2.0 · GPLv2 |

Stage all three before running Inno Setup (`deploy/campus.iss`) and the
installer's `[Files]` step bundles them in; `install.ps1` picks them up
automatically at first run. A build with none staged is still useful — an
operator can point `DATABASE_URL` in the generated `.env` at a Postgres they
installed some other way, and run the app/proxy manually or under their own
service manager.

## What the installer does (first run)

1. Lays out `%ProgramData%\Campus\{app, pgsql, pgdata, caddy, logs, media}`.
2. Generates per-install secrets into `%ProgramData%\Campus\app\.env`
   (`SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `POSTGRES_PASSWORD`) and ACLs the
   file to SYSTEM + Administrators only — proven for real: a non-elevated
   session was denied read access to the file it just wrote.
3. If a portable Postgres is staged: `initdb`, registers **Campus
   PostgreSQL** as a Windows service. Otherwise: skipped, with a message
   telling the operator to point `.env` at an existing Postgres instead.
4. If step 3 produced a reachable database: runs the frozen Django's
   `migrate` and `collectstatic`. Otherwise: skipped, with the exact command
   to run by hand once a database is reachable.

   **First administrator:** the installer does *not* create it. Instead, the
   first visit to `https://<host>/` shows a **"Welcome to Campus"** screen
   (`/setup`) that creates the initial SUPERADMIN and signs that browser in.
   The `POST /api/auth/setup/admin/` endpoint is unauthenticated but
   self-disabling — it returns 409 the instant any superadmin exists, and
   `GET /api/auth/setup/status/` drives the redirect. Complete it promptly
   after install (single-tenant LAN appliance; the window is the minutes
   between install and first admin). A headless alternative remains:
   `campus-app.exe manage create_admin` (or `deploy/create-campus-admin.ps1`).
   Enrol MFA immediately after — staff cannot reach any record until it is
   confirmed.
5. Templates the Caddyfile with the chosen LAN hostname + API bind
   (verified: `{$CAMPUS_HOST:localhost}`/`{$API_BIND:...}` correctly
   replaced). If Caddy + NSSM are staged, registers **Campus Proxy** as a
   service; otherwise skipped with a message naming what's missing.
6. If NSSM is staged, registers **Campus App** (waitress) as a service.
7. Sets every service that *was* registered to **Automatic** and starts it.
8. **Trusts the local HTTPS certificate.** After the health check (which
   forces Caddy to issue its cert), the installer finds the root of Caddy's
   internal CA and adds it to this machine's **Trusted Root Certification
   Authorities** store, so Edge/Chrome show a padlock instead of "Not
   secure". Caddy runs as a SYSTEM service and can't do this itself
   (`skip_install_trust` is set in the Caddyfile so it stops trying). A copy
   is left at `%ProgramData%\Campus\campus-local-ca.crt`.
9. Drops Start Menu + Desktop shortcuts and a small launcher that opens
   `https://<host>/`.

Every skip above prints exactly what's missing and where to get it (this
table) — setup finishes either way rather than aborting partway through.

### Other machines on the LAN

They still need the CA once. Push `%ProgramData%\Campus\campus-local-ca.crt`
to each client's **Trusted Root Certification Authorities** — by Group Policy
(*Computer Configuration → Policies → Windows Settings → Security Settings →
Public Key Policies*), or `certutil -addstore -f Root campus-local-ca.crt`
elevated, or `caddy trust` if Caddy is on that box. Browse Campus by the
**hostname you chose at install**, not a bare IP — the certificate covers the
name (and loopback for `localhost`), not arbitrary addresses. Restart the
browser fully after importing.

`repair-campus.ps1` re-runs the trust step on an existing install.

## Remote access (optional)

Campus is LAN-only until someone deliberately turns off-premises access on. The
way to do it is the **Start Menu → "Campus — Remote Access Setup"** window on
the box (it self-elevates): pick a mode, fill the fields, click **Apply**;
progress and the follow-up steps show in the log pane, and a **Turn OFF** option
reverts to LAN-only. Stage the binaries from the table above first. All three
modes keep the database, files and backups on-premises — see
`docs/REMOTE_ACCESS_AND_YOUR_DATA.md` for what differs (in-transit visibility)
and for the language to give a school's privacy officer.

`scripts\remote-setup.ps1` is the same actions without the window, for scripted
runs (`-Mode Tunnel|WireGuard|Gateway|Status|Off`); both share
`remote-setup.lib.ps1`.

| Mode | What you fill in | Needs |
|---|---|---|
| **Cloudflare Tunnel** — easiest for parents, nothing to install | public hostname, allowed emails (optional); a **Sign in to Cloudflare** button opens the browser | a Cloudflare account + a domain in Cloudflare; finish the Cloudflare Access policy in the dashboard (the log prints the steps) |
| **WireGuard** — best for staff, ciphertext-only in transit | listen port; then per device a name + the school's public IP/DDNS → **Create device config** writes a `.conf` to import | one **UDP** port forwarded to the box |
| **Gateway** — own domain, own Let's Encrypt cert, TLS ends on the box | public hostname, Let's Encrypt email | ports **80 + 443** forwarded, public DNS A record |
| **Turn OFF** | — | always leaves a working LAN install |

The Django side is inert until this runs: `REMOTE_ACCESS_ENABLED` in `.env`
gates a middleware that restores the real client IP from the fronting layer's
header (`CF-Connecting-IP` etc.) **only when the peer is loopback**, so axes
lockout and the audit log attribute remote users correctly. Tunnel mode adds a
4th Windows service, **Campus Remote** (`cloudflared`, outbound-only). The
superadmin console has a read-only **Remote access** page showing the current
state. `/admin` is never reachable off-LAN, in any mode.

## Field support

Run these in the elevated shell on the box (`campus-app.exe` is at
`%ProgramData%\Campus\app\`):

- `campus-app.exe manage support_bundle` → one **redacted** ZIP (logs, health,
  service states, `.env` with secrets stripped, table row counts). Contains no
  student data — safe to email before a visit or carry away after one.
- `campus-app.exe manage support_tail app|proxy|db|remote [-n N]` → tail a
  service log.
- `campus-app.exe manage support_sql "<query>" --operator "<name>" [--write]`
  → read-only unless `--write` (always rolls back otherwise); writes one
  append-only audit entry per run.

**Hotfix overlay** — to fix a logic bug on site without a full rebuild: drop the
corrected `.py` under `%ProgramData%\Campus\app\hotfix\` at its real package
path (e.g. `hotfix\apps\grades\services.py`), restart **Campus App**, verify.
It shadows the frozen copy. Active hotfixes are logged at startup, flagged by
`manage check` (`core.W001`), and shown in `support_bundle` + the Remote access
page — so a patched box is never invisible. Fold the fix into a real release
and clear the folder once it ships. Cannot add a dependency or change a model
(those need a patched build via `repair-campus.ps1 -RefreshAppFrom`).

## Day 2

- **Backups:** `deploy\backup.ps1` — encrypted `pg_dump` + media. Schedule it
  (Task Scheduler) and move the output off-box. Test restores with
  `deploy\restore.ps1` — a release is not signed off until a
  backup → wipe → restore drill passes.
- **Updates:** run the new `Campus-Setup.exe`; it stops the services, swaps the
  app, runs `migrate`, restarts. Data is untouched.
- **Uninstall:** asks **"Keep Campus data (database, media, audit log)?"** —
  default **Yes**.

## Operator privacy checklist

Before go-live, work through `OPERATOR_PRIVACY_CHECKLIST.md` for the school's
jurisdiction — retention windows, consent wording, who gets the health-data
role, the records-request process, and the breach-response contact.
