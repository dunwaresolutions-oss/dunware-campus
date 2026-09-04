# Campus — Architecture

## Shape

```
        Browser: staff console            Browser: parent / student portal
                    \                              /
                     \------- HTTPS (LAN) --------/
                                 |
                          Caddy  (bundled, Windows service)
                           |   TLS termination + reverse proxy
                           |   /api, /admin, /static, /media, and the SPA
                                 |
                    waitress  (bundled, Windows service)
                    serving  config.wsgi  (Django 5.2 + DRF)
                    + whitenoise serving frontend/out (the static SPA)
                                 |
                    PostgreSQL 16  (bundled portable build, Windows service)
                    data dir: %ProgramData%\Campus\pgdata  (encrypted volume)
```

Background jobs: `django-q2` (own Windows service), DB-backed broker — no Redis.

## Why these choices

| Choice | Reason |
|---|---|
| Next.js **static export** (`output: 'export'`) | Removes the Node runtime from production. The SPA is just files; Django/whitenoise serves them. Trade-off: no SSR / Server Components for data — fine, Campus is API-first. |
| **Django + DRF** on `waitress` | `waitress` is pure-Python and Windows-native — no gunicorn/uwsgi, no Unix sockets. Freezes cleanly with PyInstaller. |
| **Session auth**, same-origin behind Caddy | No token storage in the browser, CSRF is standard, revocation is a session delete. JWT would add moving parts and risk for a PII system. |
| **PostgreSQL 16** (not SQLite) | Concurrent staff + portal writes, real constraints, JSON, full-text, row-level thinking for object permissions. Portable Windows build bundles without Docker. |
| **Caddy** | One small binary, automatic local TLS (`tls internal`), trivial reverse-proxy config. |
| **Single-tenant per install** | One school per box. No cross-tenant data path to get wrong. |

## Request auth flow

1. `GET /api/auth/csrf/` sets the CSRF cookie.
2. `POST /api/auth/login/` (username, password, and — Phase 1 — a TOTP code for staff). On success Django opens a session; the cookie is `HttpOnly`, `Secure` (prod), `SameSite=Lax`.
3. Every mutating call sends `X-CSRFToken` from the cookie.
4. DRF default permission is `IsAuthenticated`; each viewset adds a `RoleRequired` subclass and, for a single object, `IsObjectOwnerOrStaff`.
5. `django-otp` middleware marks the request verified; Phase-1 mixins refuse staff endpoints for an unverified session.
6. `AuditContextMiddleware` puts the actor + IP in a context var; `apps.audit.services.record()` and the Phase-1 automatic hooks write the log.

## App boundaries

`core` (shared: `EncryptedField`, base models, permission mixins, PII log scrub) · `accounts` (User + roles + MFA) · `audit` (append-only log + middleware) · then the domain apps: `people`, `health` (encrypted, stricter), `registration`, `scheduling`, `attendance`, `lessons`, `grades`, `booking`, `communication` (email only), `billing` (placeholder), `reporting` (export / erasure / retention jobs).

## Build & ship

- Frontend: `npm run build` → `frontend/out/`.
- Backend: `pip install -r requirements/prod.txt`, `collectstatic` (picks up `frontend/out`), PyInstaller onedir freeze of a small entrypoint that runs `waitress.serve(config.wsgi:application)`.
- Bundle: the frozen app + portable PostgreSQL + Caddy + the Caddyfile + `install.ps1` → Inno Setup → `Campus-Setup.exe`.

See `DEPLOYMENT.md` for the on-site install.
