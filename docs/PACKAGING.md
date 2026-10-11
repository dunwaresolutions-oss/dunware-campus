# Campus — Packaging (Phase 9)

How the bundled installer gets built, what was actually proven this phase,
and what's staged separately. Two real bugs were found and fixed by actually
running the frozen build — not just writing the freeze scripts.

## The pipeline

```
frontend/          npm run build              -> frontend/out/            (static SPA)
backend/            pyinstaller campus.spec     -> dist/campus-app/         (frozen Django + waitress)
deploy/_thirdparty/  (staged by hand, see below) -> pgsql/, caddy/, nssm.exe[, remote/]
deploy/campus.iss   iscc campus.iss             -> dist/installer/Campus-Setup.exe
```

`campus_app.py` is the one entrypoint the frozen build ever runs:
`campus-app.exe serve` (what the "Campus App" Windows service runs) or
`campus-app.exe manage <django command>` (what `install.ps1` uses for
`migrate`/`collectstatic`, and what an operator uses for
`run_retention`/`export_student`/`erase_student` — and now
`support_bundle`/`support_tail`/`support_sql` — after install; there is no
Python on the target machine to run `manage.py` directly).

Before it dispatches, `main()` calls `_apply_hotfix_overlay()`: if
`%ProgramData%\Campus\app\hotfix\` holds any `.py`, a narrow meta-path finder is
inserted ahead of PyInstaller's frozen importer so a corrected module at its
real package path shadows the bundled one. Empty dir → no-op. This is the
sanctioned on-site fix path for a logic bug; active overlays print to the
service log and are flagged by `manage check` (`core.W001`). See
`docs/DEPLOYMENT.md#field-support`.

## Build it yourself

```powershell
cd frontend; npm run build; cd ..

cd backend
.\.venv\Scripts\pip install -r requirements\build.txt
$env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
$env:SECRET_KEY = "<any 50+ char placeholder — only used while PyInstaller imports settings>"
$env:FIELD_ENCRYPTION_KEY = "<any 32-byte base64 placeholder, same reason>"
.\.venv\Scripts\pyinstaller ..\deploy\campus.spec --distpath ..\dist --workpath ..\build --noconfirm
cd ..

# stage deploy/_thirdparty/{pgsql,caddy}[,nssm] — see "Third-party binaries" below

cd deploy
& "C:\...\Inno Setup 6\ISCC.exe" campus.iss
```

The virtualenv is `backend\.venv` (create it there; it is gitignored). Inno
Setup 6 or 7 both work — e.g. `C:\Program Files\Inno Setup 7\ISCC.exe`; a full
compile with everything staged takes ~7 minutes.

Smoke-test the frozen app before compiling, with the **prod** settings the
build uses (the dev settings import `django_extensions`, which is deliberately
not bundled, so they fail on the frozen exe):

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
$env:SECRET_KEY = "<placeholder>"; $env:FIELD_ENCRYPTION_KEY = "<placeholder>"
.\dist\campus-app\campus-app.exe manage check     # expect: no issues
```

The three companion windows (**Campus — Remote Access Setup**, **Campus —
Payments Setup**, **Campus — Central Link Setup**) are not separate
installers: `campus.iss` copies `remote-setup-ui.ps1` /
`campus-payments-setup-ui.ps1` / `campus-central-setup-ui.ps1` into
`{app}\scripts` and adds their Start Menu shortcuts, so one `iscc` run keeps
them current. "Central Link Setup" (C1, 2026-10-08) sets `deployment_mode`
and links a school to a Campus Central head office — see
docs/CENTRAL_SYNC_SCOPE.md; **Campus Central itself is a separate product
with its own, not-yet-built installer**, never something this window can
turn a Campus install into.

Output: `dist/installer/Campus-Setup.exe` — ~294 MB with the third-party
binaries staged and bundled in (266 MB when this was first written, before
GnuPG and the GTK3 runtime were added), ~37 MB without. Like the `bookkeeping-tool`
installer, this is never committed — it's a build artifact / GitHub Release
asset (`dist/`, `build/`, `deploy/_thirdparty/` are all in `.gitignore`).

## What was actually run this phase, and what it found

### 1 — The freeze itself: two real bugs, both fixed

`pyinstaller campus.spec` produced a 17 MB `campus-app.exe` (≈99 MB onedir
total). Rather than declare it done, it was actually exercised:

```
campus-app.exe manage check --deploy --fail-level WARNING
  -> System check identified no issues (1 silenced)
campus-app.exe manage migrate
  -> every app's migrations applied cleanly (accounts through billing)
campus-app.exe serve --host 127.0.0.1 --port 8082
```

**Bug #1 — `ModuleNotFoundError: No module named 'whitenoise.middleware'`.**
`campus-app.exe serve` crashed on the first request. Django resolves
`MIDDLEWARE`/`STORAGES` entries as dotted-path *strings* at runtime — static
analysis can't trace those the way it traces a real `import` statement — so a
package referenced only that way needs its submodules collected explicitly.
`whitenoise` was in the spec's hidden-imports as a bare package name; fixed by
switching it to `collect_submodules("whitenoise")` (the same treatment every
other string-referenced package — `axes`, `django_otp`, `corsheaders` — was
already getting).

**Bug #2 — a redirect loop through the real proxy-trust path.** After fixing
#1, `GET /api/healthz/` behind a simulated Caddy (`curl -H
"X-Forwarded-Proto: https"`) still 301-redirected instead of answering. Root
cause: **waitress does not trust `X-Forwarded-*` headers by default** — an
anti-spoofing measure — so `SECURE_PROXY_SSL_HEADER` never saw `https` and
`SECURE_SSL_REDIRECT` kept firing, which would have been an infinite loop
behind the real bundled Caddy in production. Fixed in `campus_app.py`'s
`cmd_serve()`: `waitress.serve(..., trusted_proxy="127.0.0.1",
trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto",
"x-forwarded-host"}, clear_untrusted_proxy_headers=True)`.

Re-verified on the rebuilt frozen exe:

```
curl -H "X-Forwarded-Proto: https" http://127.0.0.1:8082/api/healthz/
  -> HTTP/1.1 200 OK   {"status": "ok", "service": "campus"}
curl http://127.0.0.1:8082/api/healthz/          (no header — untrusted)
  -> HTTP/1.1 301 Moved Permanently -> https://127.0.0.1:8082/...
```

Both the fix and the still-enforced-for-real-clients redirect are proven, not
assumed. `settings/base.py` also gained a `sys.frozen` branch so `BASE_DIR`
(and therefore where `.env` and the exported frontend are found) resolves to
the executable's own directory in a frozen build instead of wherever
PyInstaller happens to unpack the bundled `config` package — proven by the
`.env` next to `campus-app.exe` actually being read.

WeasyPrint is bundled as Python code but its native Cairo/Pango/GObject
libraries are **not** — this build machine doesn't have them, so PDF
generation falls back to the already-designed `.html` path
(`apps/grades/services.py PdfEngineUnavailable`). A build machine that stages
the GTK runtime gets real PDFs; one that doesn't still ships a working
product. Not a bug — a documented capability gap (see
`docs/ASVS_LITE_REVIEW.md` V6.4.1 for the equivalent framing on key rotation).

### 2 — `install.ps1`: the first-run wizard, drilled for real (minus two binaries)

Rewritten from the documented-but-unimplemented Phase-0/8 shape into real
code. Drilled against a scratch install root built from the frozen output
above:

```
==> Campus first-run setup - <scratch root>
    OS: Microsoft Windows 11 Home (64-bit)
    ! could not determine BitLocker status (not fatal) - please confirm it manually.
==> Generating per-install secrets
    wrote <scratch root>\app\.env (ACL'd to SYSTEM + Administrators)
    - skipped: PostgreSQL - no portable build staged at ...\pgsql\bin
    - skipped: migrate/collectstatic - needs a reachable database
    templated Caddyfile for host 'campus-test.local', api '127.0.0.1:8001'
    - skipped: Campus Proxy service - Caddy not staged at ...\caddy\bin\caddy.exe
    - skipped: Campus App - NSSM not staged at ...\caddy\bin\nssm.exe
==> Setup finished
```

Verified for real, not just by reading the script:

- **Secret generation** — `SECRET_KEY`/`FIELD_ENCRYPTION_KEY`/`POSTGRES_PASSWORD`
  actually written to `.env`.
- **The ACL restriction is real, not asserted** — after the run, this
  (non-elevated) session's own `Get-Content` on the generated `.env` was
  **denied** (`icacls` showed only `SYSTEM` / `BUILTIN\Administrators`). That
  is Windows UAC token filtering doing exactly what "ACL'd to SYSTEM +
  Administrators only" is supposed to mean, demonstrated rather than
  claimed.
- **Caddyfile templating** — `{$CAMPUS_HOST:localhost}` / `{$API_BIND:...}`
  correctly replaced with the chosen LAN host and bind everywhere they
  appear.
- **The launcher** — a `launch-campus.url` pointing at `https://<host>/` was
  written for the Start Menu / Desktop shortcut.
- **Graceful degradation** — with no Postgres, no Caddy, and no NSSM staged,
  every dependent step printed a clear, specific, actionable skip message
  and setup still finished instead of crashing.

Not run for real (no binaries to run them against, exactly like the Phase 8
backup/restore drill): `initdb`/`pg_ctl register` (needs the staged portable
Postgres) and the two `nssm install` service registrations (needs NSSM +
Caddy staged). The code paths are written and this is the acceptance test
for a build machine that has staged them — see "Third-party binaries" below.

### 3 — The Inno Setup installer: compiled for real

```
iscc campus.iss
  -> Successful compile
  -> dist/installer/Campus-Setup.exe   (266 MB, with PostgreSQL/Caddy/NSSM bundled)
```

Packages the frozen app, the exported frontend, the Caddyfile, all four
deploy scripts, and — once staged, see below — the real PostgreSQL/Caddy/NSSM
binaries. The `[Code]` uninstall logic (a "keep data?" prompt, then a clean
service teardown via `uninstall-services.ps1`) is written; a fresh install +
uninstall cycle is the acceptance test for whoever runs the finished
installer on a target machine.

## Third-party binaries

Two binaries and one service-shim are **staged into `deploy/_thirdparty/`
before compiling** and never committed to the repo (the directory is
gitignored) — Inno's `[Files]` entries pick them up with
`skipifsourcedoesntexist`, so the `.iss` compiles either way, but only a
build with them staged produces a fully self-contained installer:

| What | Where it goes | Get it from | License |
|---|---|---|---|
| PostgreSQL 16, portable Windows zip build | `deploy/_thirdparty/pgsql/` (so `pgsql/bin/pg_dump.exe` etc. exist) | https://www.enterprisedb.com/download-postgresql-binaries | PostgreSQL License (BSD/MIT-style) |
| Caddy, Windows amd64 | `deploy/_thirdparty/caddy/caddy.exe` | https://caddyserver.com/download | Apache 2.0 |
| NSSM (wraps `caddy.exe run` / `campus-app.exe serve` as Windows services — neither implements the Windows Service Control Protocol on its own) | `deploy/_thirdparty/caddy/nssm.exe` (install.ps1 looks for it next to `caddy.exe`) | https://nssm.cc/download | Public domain / permissive |

PostgreSQL itself needs no such shim — `pg_ctl register` implements the
service protocol directly, which is why `install.ps1`'s Postgres path uses
`pg_ctl register` and its Caddy/App paths use NSSM.

### 4 — the full stack, actually staged and proven end-to-end

A first installer was shipped without these three binaries staged (no
internet access in that build's dev environment) — `install.ps1` degraded
exactly as designed (clear skip messages, no crash), but that meant no
database and no reverse proxy actually came up, so `https://localhost/`
correctly refused to connect. Once this environment *did* have outbound
access, all three were fetched for real (PostgreSQL 16.4, Caddy v2.11.4,
NSSM 2.24) and verified to actually run (`pg_ctl --version`, `caddy
version`, `nssm version`) before staging.

That surfaced one more real, if minor, bug: `install.ps1`'s `.env` write
used `Set-Content -Encoding utf8`, which in Windows PowerShell 5.1 emits a
**UTF-8 BOM** — and django-environ silently treats a BOM-prefixed first
line as an "Invalid line" and drops it rather than erroring. Harmless today
only because the dropped line (`CAMPUS_ENV=prod`) isn't read anywhere;
still a real latent bug, fixed by writing both the `.env` and the templated
Caddyfile via `[System.IO.File]::WriteAllText(..., UTF8Encoding($false))`
instead. (Checked the Caddyfile side specifically with `caddy validate` —
Caddy's own parser tolerates a BOM fine, so that half was hygiene, not a
live bug; the `.env` half was live.)

With real binaries staged and the fix applied, the entire stack was proven
end-to-end in one drill — not via the installer's Windows-service path
(registering real services was left for an actual install, see below), but
by running the exact same binaries as plain processes against a scratch
root:

```
initdb -D pgdata -U postgres -A trust        -> Success.
pg_ctl start -D pgdata -o "-p 5433 ..."      -> server started, ready to accept connections
campus-app.exe manage migrate                -> every app's migrations applied against real Postgres
campus-app.exe serve --port 8001             -> waitress up
caddy run --config Caddyfile                 -> certificate obtained (local CA), server running on :443

curl https://localhost/api/healthz/  -> 200 {"status": "ok", "service": "campus"}
curl http://localhost/               -> 308 (HTTP->HTTPS redirect, as designed)
```

That is the same request path a real install produces once `install.ps1`
registers Postgres/Caddy/App as Windows services instead of plain
processes — proof the bundled binaries and the app agree with each other,
not just that each one runs in isolation. The drill root was torn down
afterward (processes stopped, Postgres shut down cleanly, directory
deleted) — nothing persisted outside the repo's own `install.ps1` fix and
the (gitignored) staged binaries.

### 5 — what the drill missed: three bugs the real Windows-service install found

The scratch drill above ran the binaries as plain processes. A real
`Campus-Setup.exe` run on a real machine goes through the Windows-service
path, and that surfaced three more genuine bugs — each one only visible
because the install was actually performed, not simulated.

**Bug — "refused to connect" (no app / proxy services).** `campus.iss`
ran `install.ps1` from `[Run]` with `Flags: runascurrentuser`. On an
elevated Setup that flag runs the script with the *non-elevated* user
token, and `nssm install <service>` needs admin to call `CreateService` —
so both `Campus App` and `Campus Proxy` failed to register, `nssm` exited
non-zero, `Register-CampusService` ignored that and returned `$true`, and
the script ran to the end and exited 0. `Campus PostgreSQL` had registered
(that step ran earlier, before whatever token quirk bit the later ones),
so the install *looked* half-right: a database, no web tier, nothing on
443. Fixes:

- `campus.iss`: dropped `runascurrentuser` — `install.ps1` now inherits
  Setup's elevated token.
- `install.ps1`: a hard elevation guard at the top (throw, don't
  half-install); `Register-CampusService` checks `$LASTEXITCODE` **and**
  re-queries `Get-Service` afterward (nssm can exit 0 without creating the
  service); an `Invoke-Manage` wrapper runs `campus-app.exe manage …` with
  `$ErrorActionPreference` dropped to `Continue` so Django/axes' normal
  stderr logging can't be promoted to a terminating error (that had been
  aborting the run right after `migrate`, before any service registration);
  a URL-safe Postgres password (the old alphabet could put `@` / `#` / `%`
  straight into `DATABASE_URL`); the `.env` write reopens write access if a
  prior install left the file ACL-locked to SYSTEM+Administrators.
- `install.ps1` step 10 (new): after starting services, **throw** if any of
  the three is missing or if `https://<host>/` doesn't answer 200 within
  ~30s. A half-install now fails Setup loudly instead of reporting success.

**Bug — 404 at `/` (SPA never served).** With the services finally up, the
response headers showed `server: waitress` and `via: 1.1 Caddy` — the whole
chain was working — but `GET /` returned a Django 404. The Caddyfile
proxied every non-`/api` path to waitress, and Django has no route for `/`
and no `WHITENOISE_ROOT`; the bundled `frontend_out/` export was collected
into `staticfiles/` but only reachable under `/static/`. Fix:
`deploy/proxy/Caddyfile` now has **Caddy serve the static export directly**
(`root * {$CAMPUS_WEB_ROOT}` + `try_files {path} {path}/index.html
{path}.html /index.html` + `file_server`) and proxies only
`/api /admin /static /media` to waitress. `install.ps1` templates the new
`{$CAMPUS_WEB_ROOT}` placeholder to `<InstallRoot>/app/frontend_out` with
forward slashes (a bare backslash in a Caddyfile `root` is an escape).
Validated with `caddy validate` / `caddy fmt`.

**Bug — no first-run admin path.** The only way to make the initial
account was a `manage shell -c "from apps.accounts.services import
bootstrap_superadmin; …"` one-liner that is near-impossible to quote
correctly through PowerShell. First fix: a real
`campus-app.exe manage create_admin` management command
(`apps/accounts/management/commands/create_admin.py`) — wraps
`bootstrap_superadmin`, takes `--username/--email/--password` or the
`CAMPUS_ADMIN_*` env vars or a hidden prompt, runs Django's password
validators, first-run-only.

**Then made it a browser flow (2026-09-07).** Requiring an operator to open
an elevated terminal for the very first step was the wrong first impression.
`GET /api/auth/setup/status/` (`{needs_setup}`) + `POST /api/auth/setup/admin/`
(`AllowAny`, `throttle_scope="auth"`, self-disables with 409 once a superadmin
exists, then signs the new session in) back a `/setup` "Welcome to Campus"
screen; the login page redirects to it while `needs_setup` is true. The
`create_admin` command stays as the headless/automation path. `install.ps1`'s
closing message now points at the URL. Suite 151 → 157 (`test_setup.py`, 6
cases). `deploy/create-campus-admin.ps1` remains for installs whose frozen
exe predates either mechanism.

### `deploy/repair-campus.ps1`

Bundled into the installer. One-shot, idempotent, run-as-Administrator fix
for an install that came up wrong (either of the first two bugs above):
strips a `.env` BOM, applies migrations if none are present, rewrites the
Caddyfile to the SPA-serving layout, (re)registers `Campus App` /
`Campus Proxy` via nssm, restarts everything, and health-checks
`/api/healthz/` and `/` with TLS 1.2 forced (the Windows PowerShell 5.1
client won't negotiate it with modern Caddy by default). This is the
recovery path for anyone who installed 0.9.0 before these fixes shipped.

### `Campus Scheduler` registered but wouldn't start: a real frozen-exe bug (2026-10-09)

Damien hit this on a real install: `nssm install` succeeded, the service showed
up, but `Start-Service "Campus Scheduler"` failed outright. Root cause, found
by reasoning from `django_q/cluster.py`'s own source rather than guessing: it
spawns worker processes with `multiprocessing.Process` (`multiprocessing.get_
context()`, which is `"spawn"` on Windows — there's no `"fork"` there). A
frozen PyInstaller exe needs `multiprocessing.freeze_support()` called before
anything else, or every spawned child **re-executes the whole frozen exe from
scratch** — which lands back in `campus_app.py`'s own `main()`, fails its
`sys.argv[1] not in ("serve", "manage")` check (multiprocessing's own internal
bootstrap argv isn't either of those), and exits immediately — crashing the
parent `qcluster` process a moment after NSSM starts it. This is a generic
PyInstaller-on-Windows gotcha, not specific to django_q or to Campus; it just
had never been hit before because `serve` (waitress) is single-process.

Fixed: `multiprocessing.freeze_support()` added as the first line under
`if __name__ == "__main__":` in both `campus_app.py` and `central_app.py`
(the latter defensively — Central has no multiprocessing-using command today).
**Actually verified, not just reasoned about**: re-froze `campus-app.exe`,
then ran `campus-app.exe manage qcluster` directly against a migrated
throwaway SQLite database — it now logs `Q Cluster ... running`, with worker
processes actually reaching `ready for work`/`monitoring`/`pushing tasks`,
instead of the service dying instantly. `Campus-Setup.exe` was recompiled with
this fixed build (304,714,735 bytes, exit 0).

### The fourth service: `Campus Scheduler` (2026-10-09)

`Q_CLUSTER` has been configured in settings since before this phase, but no
`manage.py qcluster` worker process was ever registered anywhere — so no
feature of Campus's, not just Central sync, could actually run anything on
a timer (see `docs/CENTRAL_SYNC_SCOPE.md`'s C5/C7a). Fixed as a fourth
NSSM-wrapped Windows service, "Campus Scheduler" (`campus-app.exe manage
qcluster`), registered in `install.ps1` right after "Campus App", using the
exact same `Register-CampusService` helper — no new code in `campus_app.py`
needed, since `manage` already proxies arbitrary Django commands.
`repair-campus.ps1` and `uninstall-services.ps1` updated to match. Verified
by parsing all three edited scripts with PowerShell's own AST parser (no
syntax errors); **not** run for real against this dev machine — registering
a Windows service is exactly the kind of real, shared-machine-state action
this project avoids taking just to validate a mechanical, already-proven
pattern (see `docs/DEPLOYMENT.md`'s "two real Postgres services already on
this box" note).

### Co-locating Campus + Campus Central on one box: three real port collisions found and fixed (2026-10-09)

Damien hit this live, linking a real Campus install to a real Central install
on the same machine for a definitive end-to-end test. Each was found by
actually reading the resulting Caddy log, not guessed:

1. **Caddy's admin API is a fixed `127.0.0.1:2019`, independent of the
   site's own port.** Two `caddy.exe` processes on one box always collide
   there. Fixed: `admin off` in Central's Caddyfile (neither install ever
   calls the admin API at runtime — both only rewrite the Caddyfile and
   restart the service).
2. **The site itself defaulted to port 443/80**, which Campus's own Caddy
   ("Campus Proxy") already owns on a co-located box. Fixed: Central's
   Caddy now binds `:8443` (`CENTRAL_WEB_PORT`, `install-central.ps1`'s
   `-WebPort` param) — the same collision-avoidance reasoning already
   applied to Postgres's port 5433. `CSRF_TRUSTED_ORIGINS` in `.env.central`
   needed the port added too (`https://localhost:8443`), or Django rejects
   every POST/login with a CSRF origin mismatch once the Origin header
   itself carries the port.
3. **Caddy's `auto_https` feature opens its own SEPARATE port-80 redirect
   listener whenever any site uses TLS — independent of what port the site
   itself is on.** Moving the site to `:8443` alone did not stop Caddy from
   still trying to grab `:80` for that redirect helper, which failed with
   the same "Only one usage of each socket address" error, leaving the
   service `Paused`. Fixed: `auto_https disable_redirects` in the global
   options block (confirmed via the log: `"automatic HTTP->HTTPS redirects
   are disabled"`) — the site's own explicit `tls internal` still works
   fine with this off; only the extra listener is disabled.

**Verified, not just reasoned about**: validated the fixed Caddyfile with
`caddy validate`, then actually ran it live (`caddy run`) alongside Damien's
real, running "Campus Proxy" service — both answered simultaneously on their
own ports with zero bind conflict.

## Campus Central's own packaging (`Campus-Central-Setup.exe`)

A second, independent pipeline, deliberately mirroring every file and every
fix above rather than rediscovering them — Central is a separate product
(separate database, separate installer, per `docs/CENTRAL_SYNC_SCOPE.md`),
but the packaging *mechanics* (PyInstaller onedir, NSSM-wrapped services,
Inno Setup, the same staged third-party binaries) are identical.

```
frontend_central/   npm run build                 -> frontend_central/out/      (static SPA)
backend/             pyinstaller central.spec      -> dist/central-app/          (frozen Django + waitress)
deploy/_thirdparty/  (same staged binaries as Campus's own build - generic, not product-specific)
deploy/central.iss   iscc central.iss              -> dist/installer/Campus-Central-Setup.exe
```

`central_app.py` is Central's one entrypoint (`serve` / `manage`), the
counterpart of `campus_app.py` — same waitress `trusted_proxy` fix, same
hotfix-overlay mechanism (both generic, not Campus-specific). It deliberately
has **no** `_ensure_native_pdf_libs()` step: nothing under `apps/central`
uses WeasyPrint (confirmed by grep before writing the spec), so Central
needs no GTK3 runtime staged — a real, intentional difference from Campus's
own entrypoint, not an oversight.

Build it yourself:

```powershell
cd frontend_central; npm run build; cd ..

cd backend
$env:DJANGO_SETTINGS_MODULE = "central.settings.prod"
$env:CENTRAL_SECRET_KEY = "<any 50+ char placeholder>"
$env:CENTRAL_FIELD_ENCRYPTION_KEY = "<any 32-byte base64 placeholder>"
.\.venv\Scripts\pyinstaller ..\deploy\central.spec --distpath ..\dist --workpath ..\build --noconfirm
cd ..

# stage deploy/_thirdparty/{pgsql,caddy} — same binaries as Campus's own build;
# nothing extra to stage if a Campus build has already staged them

cd deploy
& "C:\...\Inno Setup 6\ISCC.exe" central.iss
```

Smoke-test before compiling, same reasoning as Campus's own:

```powershell
$env:DJANGO_SETTINGS_MODULE = "central.settings.prod"
$env:CENTRAL_SECRET_KEY = "<placeholder>"; $env:CENTRAL_FIELD_ENCRYPTION_KEY = "<placeholder>"
.\dist\central-app\central-app.exe manage check     # expect: no issues
```

**Actually run this phase** (not just written): `pyinstaller central.spec`
hit the exact same `AttributeError: 'Settings' object has no attribute
'ROOT_URLCONF'` this doc already documents for Campus's own build (the
PyInstaller Django hook imports settings during the freeze itself, before
`DJANGO_SETTINGS_MODULE`/the placeholder secrets are set) — same cause, same
fix, confirming this isn't a one-off Campus quirk but a real PyInstaller +
Django interaction every frozen Django build here will hit. With the env
vars set, the freeze completed clean (one `central-app.exe`, ~99 MB onedir,
same ballpark as Campus's own). `manage check` then reported "System check
identified no issues". Beyond that, `central-app.exe serve --host 127.0.0.1
--port 8099` was started against a throwaway SQLite database (never
touching either of this machine's real Postgres services), and
`curl http://127.0.0.1:8099/api/healthz/` returned `301` — the correct,
expected `SECURE_SSL_REDIRECT` redirect-to-HTTPS behaviour, the exact same
signal Campus's own `install.ps1`/`repair-campus.ps1` already treat as
"the app tier is working" at that same health-check step.

`deploy/install-central.ps1` mirrors `install.ps1` end to end, with three
deliberate differences, not oversights:

- **`.env.central`, not `.env`** — a different filename, matching
  `central/settings/base.py`'s own `_env_file` read, so the two can never be
  confused on a box that somehow runs both.
- **Postgres on port 5433, not 5432** — a deliberate collision-avoidance
  choice: a Ministry test box might run a Campus install (for support/demo)
  alongside Campus Central, and the two must never fight over the same port.
- **No fourth, scheduler service** — `central/settings/base.py`'s
  `INSTALLED_APPS` has no `django_q`; Central has no scheduled jobs of its
  own, so unlike Campus (see above) it registers exactly three services
  ("Campus Central PostgreSQL", "Campus Central App", "Campus Central
  Proxy"), not four.

**Compiled successfully**: `& "C:\Program Files\Inno Setup 7\ISCC.exe"
central.iss` ran clean — 361.984 sec, exit 0 — producing a real
264,635,770-byte `dist\installer\Campus-Central-Setup.exe`. The compile log
confirms every staged piece actually went in: the frozen `central-app`, the
`frontend_central` export, the Caddyfile template, and the full
`deploy/_thirdparty\pgsql\*` (including its debug symbols) and
`deploy/_thirdparty\caddy\*` trees — the same binaries Campus's own build
stages, reused rather than duplicated. The entire pipeline above — freeze,
smoke test, compile — is now real and verified end to end, not just
written. Still not built: Central backup/restore tooling (no
`backup.ps1`/`restore.ps1` equivalent exists for Central) and an actual
recurring `Schedule` row for `central_sync` (the scheduler worker now
exists, product-wide, per the section above — but nothing inserts a
`Schedule` row yet; that remains its own, separate, unbuilt decision).
