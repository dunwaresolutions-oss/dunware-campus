# Campus — Deployment (on-site)

Campus ships as **one Windows installer**, `Campus-Setup.exe`. There is no
Docker, Python, or Node requirement on the target machine — everything is
inside the installer.

## Target machine

- Windows 10/11 x64 (or Windows Server 2019+), on the school's own network.
- ~4 GB free disk for the app + a growing database.
- **Disk encryption on** (BitLocker). The installer checks and warns loudly if
  not — this box will hold children's PII.
- LAN-only by default. If remote access is wanted, that is the operator's VPN,
  not an internet-exposed port.

## What the installer does (first run)

1. Lays out `%ProgramData%\Campus\{app, pgsql, pgdata, caddy, logs, media}`.
2. Generates per-install secrets into `%ProgramData%\Campus\app\.env`
   (`SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `POSTGRES_PASSWORD`) and ACLs the
   file to SYSTEM + Administrators only.
3. `initdb` the database; registers **Campus PostgreSQL** as a Windows service.
4. Runs the frozen Django: `migrate`, `collectstatic`, then an interactive
   **create-first-admin** and an **MFA enrolment** walk-through.
5. Templates the Caddyfile with the chosen LAN hostname + API bind; registers
   **Campus Proxy** (Caddy) as a service. Prints the `caddy trust` step for
   client machines (so the LAN cert is trusted).
6. Registers **Campus App** (waitress) as a service.
7. Sets all three services to **Automatic** (start on boot) and starts them.
8. Drops Start Menu + Desktop shortcuts and a small launcher that opens
   `https://<host>/`.

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
