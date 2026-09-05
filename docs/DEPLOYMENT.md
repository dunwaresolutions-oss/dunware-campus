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
- LAN-only by default. If remote access is wanted, that is the operator's VPN,
  not an internet-exposed port.

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
   to run by hand once a database is reachable. Either way, the first admin
   is **not** created interactively by the installer — run it once, by hand,
   right after (`campus-app.exe manage shell -c
   "from apps.accounts.services import bootstrap_superadmin; ..."`, printed
   at the end of setup) — and enrol MFA immediately after signing in.
5. Templates the Caddyfile with the chosen LAN hostname + API bind
   (verified: `{$CAMPUS_HOST:localhost}`/`{$API_BIND:...}` correctly
   replaced). If Caddy + NSSM are staged, registers **Campus Proxy** as a
   service; otherwise skipped with a message naming what's missing.
6. If NSSM is staged, registers **Campus App** (waitress) as a service.
7. Sets every service that *was* registered to **Automatic** and starts it.
8. Drops Start Menu + Desktop shortcuts and a small launcher that opens
   `https://<host>/`.

Every skip above prints exactly what's missing and where to get it (this
table) — setup finishes either way rather than aborting partway through.

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
