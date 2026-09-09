# Campus — ASVS-lite Review

Part of the Phase 8 hardening pass: a self-review against a representative
slice of the [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/)
(v4), levels 1–2, picking the requirements that matter for an on-site PII
system with no public internet exposure by default (optional off-premises
access and its trust boundary are covered in V1.8 / V9.2.1). "Lite" means: every row cites the
actual code or test that satisfies it, not a checkbox — and a row marked
**Deferred** says exactly which phase closes it, not "later."

Status key: **Pass** — verified in code/tests · **Partial** — the mechanism
exists, follow-up is scoped · **Deferred** — intentionally out of scope until
a named phase · **N/A** — doesn't apply to this system's shape.

## V1 — Architecture, design, threat modeling

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1.1 | A documented, up-to-date architecture | Pass | `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md` |
| 1.4 | Trusted enforcement points (server-side, not client) | Pass | Every permission/scoping decision is a DRF permission class or a queryset filter (`apps/core/permissions.py`); the SPA has no authority |
| 1.5 | Deny-by-default access control | Pass | DRF default `IsAuthenticated` (`settings.base`); `RoleRequired` denies an unlisted role, including a viewset that forgot to subclass it (`apps/core/tests/test_permissions.py`) |
| 1.9 | Single, vetted authentication/access-control library | Pass | Django's own auth + `django-otp` + `django-axes` — no bespoke crypto or session handling |
| 1.14 | Segregated architecture tiers | Pass | Static SPA / DRF API / Postgres are separate processes even in the single-box installer (`docs/ARCHITECTURE.md`) |
| 1.8 | Trust boundaries documented, incl. optional remote access | Pass (with note) | Base case has no public exposure. **Optional** off-premises access (`deploy/remote-setup.ps1`) adds one trust boundary: <br>• **Cloudflare Tunnel** — Cloudflare's edge terminates TLS to enforce Access, so request/response plaintext is *transiently* processable there (not stored; connection metadata logged). Compensating controls: Cloudflare Access is a mandatory auth gate *before* Campus; Campus login + staff MFA still apply; `RemoteClientIPMiddleware` restores the true client IP for axes/audit **only from a loopback peer** (`apps/core/remote_proxy.py`, `test_remote_proxy.py`); `/admin` stays on the `127.0.0.1` allow-list and is unreachable off-LAN; the feature is `.env`-gated and reversible. <br>• **WireGuard / plain gateway** — TLS terminates on the Campus box; no third party sees plaintext. <br>Data at rest never leaves the box in any mode (`docs/REMOTE_ACCESS_AND_YOUR_DATA.md`). |

## V2 — Authentication

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 2.1.1 | Minimum password length ≥ 12 | Pass | `MinimumLengthValidator` at 12 (`settings.base`); enforced again server-side on invite accept (`accounts/services.py`) |
| 2.1.7 | Reject breached/common passwords | Pass | `CommonPasswordValidator` |
| 2.1.10 | No password composition rules that reduce entropy (no forced symbols) | Pass | Only length + similarity + common-password + not-all-numeric |
| 2.2.1 | Anti-automation / lockout on repeated failed logins | Pass | `django-axes`, 5 tries per (username, IP) → 429, tested (`accounts/tests/test_auth.py`) |
| 2.5.2 | Secrets never printed/logged | Pass | `PIIScrubFilter` redacts `password`/`token`/`secret`/`authorization` key=value pairs (`core/logging.py`, tested) |
| 2.6.1–2.6.3 | Time-based OTP MFA, standard algorithm, resistant to replay | Pass | `django-otp` TOTP, RFC 6238; a session must clear `is_verified()` before any sensitive endpoint answers (`accounts/mfa.py`, `core/permissions.py MFAVerified`) |
| 2.7 | Out-of-band / recovery flow doesn't bypass MFA | Partial | No self-service MFA reset exists yet — an admin re-enrolls via `mfa/setup`; acceptable for a small on-site staff, revisit if the parent portal ever needs MFA |
| 2.10.x | Registration / first-account bootstrap not abusable | Pass (with note) | There is no open self-registration. The only unauthenticated account-creation path is `POST /api/auth/setup/admin/` — it creates the *initial* SUPERADMIN, returns 409 the instant any superadmin exists (self-disabling), is on the `auth` rate-limit scope, and `bootstrap_superadmin` audits it. The residual exposure is the minutes between install and first-admin creation on a single-tenant LAN appliance; the operator is instructed to complete `/setup` immediately, and `create_admin` remains a headless alternative. |

## V3 — Session management

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 3.2.1 | Session tokens unpredictable, generated server-side | Pass | Django's own session framework (CSPRNG-backed) |
| 3.2.3 | Session inactivity / absolute timeout | Pass | 8-hour hard cap, `SESSION_EXPIRE_AT_BROWSER_CLOSE` (`settings.base`) |
| 3.3.1 | Logout invalidates the session server-side | Pass | `LogoutView` calls Django `logout()`, tested |
| 3.4.1–3.4.3 | Cookie flags: `Secure`, `HttpOnly`, `SameSite` | Pass | prod: `SESSION_COOKIE_SECURE=True`; both envs: `HTTPONLY=True`, `SAMESITE="Lax"` |
| 3.7.1 | Re-authentication for a sensitive action | Deferred | No step-up re-auth on e.g. "erase this person" beyond the standing MFA + role check; the break-glass admin path (`admin_guard.py`) is the mitigating control today — a dedicated step-up flow is a possible Phase 11+ feature, not something packaging closes |

## V4 — Access control

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 4.1.1 | Enforced server-side, not just hidden UI | Pass | Every viewset — see V1.4 |
| 4.1.3 | Deny-by-default | Pass | See V1.5 |
| 4.2.1 | Object-level access control (not just function-level) | Pass | `is_visible_to(user)` on every sensitive model + `IsObjectOwnerOrStaff`; the full visibility matrix is unit-tested per role (`people/tests/test_models.py`, `test_api.py`, repeated per app) |
| 4.2.2 | A user cannot act outside their own data by ID substitution (IDOR) | Pass | Tested directly: a parent hitting another child's URL gets 404, not the record (`people/tests/test_api.py::test_parent_sees_only_their_child`), same pattern repeated in health/registration/communication/grades/booking/billing/portal |
| 4.3.1 | Admin functionality gated beyond a normal role check | Pass | `apps/core/admin_guard.py` — superuser + IP allow-list + MFA-verified session, else 404 + audit; tested |

## V5 — Validation, sanitization, encoding

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 5.1.3 | Server-side validation of all input | Pass | DRF serializers on every write path; nothing trusts client-computed values (e.g. `Booking`/`Invoice` totals are always server-computed) |
| 5.2.2/5.2.8 | Output encoding prevents XSS | Pass | React (Next.js) escapes by default; API is JSON-only, no server-rendered HTML from user input except the report-card template, which only interpolates `html.escape()`-wrapped values (`grades/services.py render_report_card_html`) |
| 5.3.4 | Structured mechanisms for DB access (no string-built SQL) | Pass | Django ORM everywhere; the one raw SQL in the codebase is in tests, reading a fixed column list with parameterized `%s` |

## V6 — Cryptography

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 6.1.1 | Classify data requiring encryption at rest | Pass | `SensitiveModel.PII_FIELDS`/`PII_PURPOSE` on every sensitive model; `docs/DATA_MODEL.md` |
| 6.2.1 | Approved, vetted cryptographic primitives | Pass | `cryptography` (pyca), AES-256-GCM (AEAD — confidentiality + integrity) for both field values (`core/fields.py`) and document bytes (`core/storage.py`) |
| 6.2.3 | Encryption key never in source, config-in-repo, or logs | Pass | `FIELD_ENCRYPTION_KEY` env-only, not in the repo (`.gitignore`), prod refuses to boot without it (`settings/prod.py`), scrubbed from logs if it ever appeared in a message |
| 6.2.5 | Authenticated encryption; tampering is detected, not silently decrypted | Pass | GCM tag verification; a flipped bit raises `ValueError` (`core/tests/test_fields.py::test_tampered_ciphertext_is_rejected`) |
| 6.4.1 | Key management process documented | Partial | Generation is real and proven (`deploy/install.ps1`, `docs/PACKAGING.md`) and the "never in repo/logs" rule is enforced now; **key rotation** procedure is still not written — a `FIELD_ENCRYPTION_KEY` change today re-encrypts nothing, it just breaks existing ciphertext, so this stays a named gap rather than a false Pass |

## V7 — Error handling and logging

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 7.1.1 | No sensitive data in log output | Pass | `PIIScrubFilter`, tested |
| 7.2.1 | Authorization failures logged | Pass | Every `PermissionDenied`/`NotAuthenticated` writes a `PERMISSION_DENIED` audit entry (`core/exceptions.py`), tested |
| 7.4.1 | Log entries include actor, action, target, timestamp | Pass | `AuditEntry` shape (`audit/models.py`) |
| 7.1.2 | Logs cannot themselves be tampered with by an attacker who gets app-level access | Partial | Append-only at the model/DB layer (`AuditEntry.save`/`delete` + queryset guards, tested); no write-once storage or external log shipping yet — that's an operator/Phase-9 deployment decision, not a code gap |

## V8 — Data protection

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 8.1.1 | Sensitive data identified and inventoried | Pass | `docs/DATA_MODEL.md` PII tables per app |
| 8.2.1 | No caching of sensitive responses by intermediaries | Pass | Session-authenticated API responses; no `Cache-Control: public` anywhere; same-origin behind Caddy in prod |
| 8.3.1 | Sensitive data minimized in transit/URLs | Pass | All writes are POST/PATCH bodies; DRF routers use opaque UUID path segments, never a query-string secret |
| 8.3.4 | Data-subject rights: access + erasure implemented | Pass | `reporting/services.py data_subject_export`, `erase_person`; drilled for real, see `docs/RETENTION_ERASURE_DRILL.md` |
| 8.3.7 | Retention limits enforced automatically | Pass | `reporting/jobs.py retention_sweep`; legal-hold exception verified in the drill |

## V9 — Communications

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 9.1.1 | TLS for all communication carrying sensitive data | Pass (prod) | Caddy `tls internal` + `SECURE_SSL_REDIRECT`/HSTS in `settings/prod.py`; dev is plaintext localhost by design (documented) |
| 9.1.2 | Old/weak TLS versions and ciphers disabled | Pass | Delegated to Caddy's modern defaults (TLS 1.2+); no custom cipher config to get wrong |
| 9.2.1 | Third parties in the connection path are trusted deliberately, not by default | Pass (with note) | LAN-only by default — no third party. If a site opts into **Cloudflare Tunnel** via `remote-setup.ps1`, Cloudflare is a deliberate, documented, opt-in intermediary that terminates TLS at its edge; the school signs off on transient in-transit visibility and metadata logging on non-domestic infrastructure (`docs/REMOTE_ACCESS_AND_YOUR_DATA.md`). WireGuard and gateway modes exist precisely for a site that will not accept this — TLS then terminates only on the Campus box. |

## V10 — Malicious code / supply chain

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 10.3.1 | Dependencies scanned for known vulnerabilities | Pass | `pip-audit` + `npm audit` gate CI on every push (`.github/workflows/ci.yml`); this pass's `npm audit` actually found 2 real advisories (1 high) — a transitive PostCSS pulled in by Next's own build tooling — fixed with a `package.json` `overrides` pin (`postcss@^8.5.28`) rather than a breaking Next major bump; re-verified clean below |
| 10.3.2 | Unused/unreferenced dependencies removed | Pass | `requirements/*.txt` reviewed each phase; WeasyPrint stays prod-only precisely because it's a heavy optional path (`grades/services.py`) |

## V11 — Business logic

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 11.1.2 | Business-logic limits enforced server-side (can't be bypassed by replay/race) | Pass | `Enrolment`/`Booking` uniqueness via DB constraints, not just application checks; `Booking.book()` uses `select_for_update()` so two simultaneous requests can't both win the last seat (`booking/services.py`) |
| 11.1.4 | Anti-automation on sensitive business transactions | Partial | Covered generally by the `auth`/`sensitive` DRF throttle scopes; no per-endpoint rate limit tuned for e.g. booking yet — low risk on a LAN-only install, revisit if the portal ever faces the internet |

## V12 / V13 — Files and API

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 12.3.1 | Uploaded files not served from a path that executes them | Pass | `MEDIA_URL`/`whitenoise` serve static assets only; uploaded documents go through `EncryptedFileSystemStorage`, decrypted only via the Django view layer, never a raw static path |
| 12.4.1 | File content-type / size validated server-side | Partial | DRF `FileField` validates it's a file; no explicit MIME allow-list or max-size cap yet on `Document`/report-card uploads — an operator-tunable quota belongs to a future Phase, not packaging |
| 13.1.1 | API only accepts JSON it expects, rejects the rest | Pass | DRF `JSONParser` default; serializers reject unknown-shaped payloads |
| 13.2.1 | Every endpoint's authorization is tested, not assumed | Pass | 135 tests, the large majority of which assert a *specific* role gets 200/403/404 — see any `apps/*/tests/test_*.py` |

## Dependency / static-analysis scan — this pass

```
ruff check .                                    All checks passed!
bandit -q -c pyproject.toml -r apps config       0 issues
pip-audit -r requirements/base.txt --strict      No known vulnerabilities found
npm audit --omit=dev                             0 vulnerabilities
manage.py check --deploy --fail-level WARNING    System check identified no issues (1 silenced)
pytest                                           135 passed
```

## Summary

No **Pass**-required row in this review is failing. Everything marked
**Partial** or **Deferred** is a named, scoped follow-up (self-service MFA
recovery, log shipping/WORM storage, key rotation runbook, upload MIME/size
limits, booking-specific rate limiting, step-up re-auth) rather than an
unknown gap — each one is either an operator decision now covered in
`docs/DEPLOYMENT.md` (BitLocker, TLS via bundled Caddy, encrypted backups —
all real as of Phase 9, see `docs/PACKAGING.md`), or low-risk enough on a
LAN-only, single-tenant install to defer deliberately to a future feature
phase. None of them block packaging, which is itself now complete.
