# Campus — Packaging (Phase 9)

How the bundled installer gets built, what was actually proven this phase,
and what's staged separately. Two real bugs were found and fixed by actually
running the frozen build — not just writing the freeze scripts.

## The pipeline

```
frontend/          npm run build              -> frontend/out/            (static SPA)
backend/            pyinstaller campus.spec     -> dist/campus-app/         (frozen Django + waitress)
deploy/_thirdparty/  (staged by hand, see below) -> pgsql/, caddy/, nssm.exe
deploy/campus.iss   iscc campus.iss             -> dist/installer/Campus-Setup.exe
```

`campus_app.py` is the one entrypoint the frozen build ever runs:
`campus-app.exe serve` (what the "Campus App" Windows service runs) or
`campus-app.exe manage <django command>` (what `install.ps1` uses for
`migrate`/`collectstatic`, and what an operator uses for
`run_retention`/`export_student`/`erase_student` after install — there is no
Python on the target machine to run `manage.py` directly).

## Build it yourself

```powershell
cd frontend; npm run build; cd ..

cd backend
..\.venv\Scripts\pip install -r requirements\build.txt
$env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
$env:SECRET_KEY = "<any 50+ char placeholder — only used while PyInstaller imports settings>"
$env:FIELD_ENCRYPTION_KEY = "<any 32-byte base64 placeholder, same reason>"
..\.venv\Scripts\pyinstaller ..\deploy\campus.spec --distpath ..\dist --workpath ..\build --noconfirm
cd ..

# stage deploy/_thirdparty/{pgsql,caddy}[,nssm] — see "Third-party binaries" below

cd deploy
& "C:\...\Inno Setup 6\ISCC.exe" campus.iss
```

Output: `dist/installer/Campus-Setup.exe`. Like the `bookkeeping-tool`
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
  -> Successful compile (18.6 sec)
  -> dist/installer/Campus-Setup.exe   (36.7 MB)
```

Packages the frozen app, the exported frontend, the Caddyfile, and all four
deploy scripts. `Campus-Setup.exe` was **not run** this session — installing
it registers real Windows services and writes to `%ProgramData%` on a real
machine, which is Damien's call to make, not something to do silently while
"proving a build compiles." The `[Code]` uninstall logic (a "keep data?"
prompt, then a clean service teardown via `uninstall-services.ps1`) is
written but likewise unexercised — that's the acceptance test for whoever
runs the finished installer for the first time.

## Third-party binaries

Two binaries and one service-shim are **staged by hand**, never fetched or
committed — `deploy/_thirdparty/` is gitignored, and the placeholder files
inside it document exactly what replaces them:

| What | Where it goes | Get it from | License |
|---|---|---|---|
| PostgreSQL 16, portable Windows zip build | `deploy/_thirdparty/pgsql/` (so `pgsql/bin/pg_dump.exe` etc. exist) | https://www.enterprisedb.com/download-postgresql-binaries | PostgreSQL License (BSD/MIT-style) |
| Caddy, Windows amd64 | `deploy/_thirdparty/caddy/caddy.exe` | https://caddyserver.com/download | Apache 2.0 |
| NSSM (wraps `caddy.exe run` / `campus-app.exe serve` as Windows services — neither implements the Windows Service Control Protocol on its own) | `deploy/_thirdparty/caddy/nssm.exe` (install.ps1 looks for it next to `caddy.exe`) | https://nssm.cc/download | Public domain / permissive |

PostgreSQL itself needs no such shim — `pg_ctl register` implements the
service protocol directly, which is why `install.ps1`'s Postgres path uses
`pg_ctl register` and its Caddy/App paths use NSSM.

None of these were fetchable in this session (no internet access for binary
downloads here) — that is the honest boundary of this phase, exactly like
Phase 8's backup drill couldn't run a live `pg_dump` with no Postgres
installed. Everything on this side of that boundary — the freeze, the
installer compile, the secrets/ACL/templating/degradation logic in
`install.ps1` — was built and proven for real.
