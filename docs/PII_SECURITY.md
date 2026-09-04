# Campus — PII &amp; Security

Campus holds children's names, birth dates, home addresses, photos, medical
conditions, allergies, medications, custody and legal arrangements, and
guardian contact (and later financial) details. The controls below are
**built in Phase 1, before any feature code**, and `python manage.py check
--deploy` must pass clean before any package is built.

Status key: **[done]** built &amp; tested · **[scaffolded]** structure only · **[phase N]** a named later phase.

Phases 1–4 are **complete**: staff MFA + axes lockout + Argon2; append-only
audit log with automatic write **and** read hooks; AES-256-GCM field + document
encryption across `people` / `health` / `registration` / `communication` /
`grades`; object-level visibility, a named health-access subset, versioned
consent, data-subject export, legal-hold-aware erasure, retention sweep;
calendars / rosters / templates + closures; attendance with a check-out
authorization rule; **email-only** communication (announcements, encrypted
staff↔parent threads, incident reports with a parent-acknowledgement flow, an
`OutboundEmail` send-log that never stores the body); assessment schemes
(rubric + narrative + marks) and report cards (encrypted narrative + encrypted
document, released before parent-visible). 106 backend tests; `ruff` / `bandit`
/ `pip-audit` / `check --deploy --fail-level WARNING` all clean.

## 1. Data protection

| Control | Where | Status |
|---|---|---|
| Field-level **AES-256-GCM encryption at rest** for medical/allergy/medication/action-plan, custody &amp; legal notes, government IDs, uploaded documents | `apps/core/fields.py` (`EncryptedTextField`, `EncryptedCharField`); `apps/core/storage.py` (`EncryptedFileSystemStorage` for document bytes) | **[done]** — applied across `people` / `health` / `registration`; DB + on-disk ciphertext verified by tests |
| Encryption key from `FIELD_ENCRYPTION_KEY` (env / installer-generated), **never** in DB, repo, or logs | `settings.base`, `deploy/install.ps1` | **[done]** |
| Prod refuses to start with no key | `settings/prod.py` | **[done]** |
| Encrypted storage volume for PostgreSQL + backups (BitLocker on the host) — installer checks &amp; warns | `deploy/install.ps1` | **[phase 9]** |
| TLS on the LAN, HSTS, HTTP→HTTPS redirect | `deploy/proxy/Caddyfile`, `settings/prod.py` | **[scaffolded]** |
| Encrypted backups (`pg_dump` \| age/GPG) + a restore drill | `deploy/backup.ps1`, `restore.ps1` | **[phase 8]** |
| No PII in logs — a filter redacts emails, phone numbers, and known-sensitive `key=value` before any record is emitted | `apps/core/logging.py` (`PIIScrubFilter`) | **[done]** — tested (`apps/core/tests/test_logging.py`) |

## 2. Access control

| Control | Where | Status |
|---|---|---|
| Custom `User` with an explicit `role` | `apps/accounts/models.py` | **[done]** |
| DRF **deny-by-default** (`IsAuthenticated`), every viewset adds an explicit `RoleRequired` subclass | `settings.base` REST_FRAMEWORK, `apps/core/permissions.py` | **[done]** — `RoleRequired` (deny-by-default), `MFAVerified`, `StaffAndMFAVerified`, tested |
| **Object-level scoping** — parent sees only their children, teacher only their groups, health data gated to a named staff subset | `IsObjectOwnerOrStaff` + `Student.is_visible_to()` / `visible_queryset()`; `health.HealthAccessGrant` + `HealthDataPermission` | **[done]** — full visibility matrix tested (people + health API) |
| **TOTP MFA** mandatory for staff roles, optional for parents | `django-otp`, `User.must_use_mfa`, `apps/accounts/mfa.py` + `LoginView` gate + `MFAVerified` | **[done]** — setup/confirm/status endpoints, login refuses staff without a code, session must be OTP-verified for sensitive endpoints; tested |
| **Argon2** password hashing, 12-char minimum, common-password + similarity validators | `settings.base` | **[done]** |
| **Login lockout** (`django-axes`, 5 tries / (user, IP) / 1 h → 429) + endpoint rate limits (DRF ScopedRateThrottle: `auth` 10/min, `sensitive` 30/min) | `settings.base`, `apps/accounts/lockout.py` | **[done]** — lockout returns 429 + audit `LOCKOUT`, tested |
| Session hardening — `Secure`/`HttpOnly`/`SameSite` cookies, 8-hour hard cap, rotate on login, full `SECURE_*` header set, CSRF enforced | `settings.base` / `prod` | **[done]** — `check --deploy` clean |
| **Break-glass Django admin** — superuser only, MFA + IP allow-list, every action audited | `apps/core/admin_guard.py` (`AdminBreakGlassMiddleware`), `CAMPUS_ADMIN_IP_ALLOWLIST` / `CAMPUS_ADMIN_REQUIRE_MFA` | **[done]** — non-qualifying requests get 404 + audit entry; tested |

## 3. Governance &amp; auditability

| Control | Where | Status |
|---|---|---|
| **Append-only audit log** — every create/update/delete **and every read** of a sensitive record (actor, action, object type+id, time, source IP). No values, ever. No update/delete path in the app; admin view is read-only. | `apps/audit/` (`AuditEntry`, `middleware`, `services.record()` / `record_safe()`, `signals`, `mixins.AuditReadMixin`, `registry`) | **[done]** — `save()`/`delete()`/queryset guards, auto CRUD signals for registered + `SensitiveModel` models, DRF read mixin, login/logout/failed + permission-denied + lockout hooks; tested |
| **Data minimization** — every PII field annotated with purpose + retention on the model (`SensitiveModel.PII_FIELDS` / `PII_PURPOSE`), mirrored into `DATA_MODEL.md` | `people` / `health` / `registration` models; `docs/DATA_MODEL.md` | **[done]** — `PII_FIELDS` / `PII_PURPOSE` set on every sensitive model; table filled in |
| **Retention** — configurable window per record type; a scheduled `django-q2` job purges or anonymizes past-student data | `apps/reporting/jobs.py` `retention_sweep()` (`sweep_past_students` + `purge_terminal_applications` + audit anonymize), `RETENTION_*` settings, `manage.py run_retention` | **[done]** — tested; django-q2 *schedule* wired in Phase 8 |
| **Erasure** — "erase this person" action, blocked by a legal-hold flag, fully audited | `apps/reporting/services.py` `erase_person()`, `manage.py erase_student`, `Student.legal_hold` | **[done]** — anonymize-in-place, health rows deleted, `ERASE` audit; legal-hold raises; tested |
| **Consent tracking** — each consent recorded with version + timestamp | `registration.Consent` (append-only rows, `current_for()`) | **[done]** — portal review surface in Phase 6 |
| **Data-subject access** — "export everything we hold about this child" | `apps/reporting/services.py` `data_subject_export()`, `manage.py export_student` | **[done]** — decrypted dict + `EXPORT` audit; portal button in Phase 6 |
| **Soft delete** — records are not hard-deleted through the app; only retention/erasure jobs remove data, and they audit it | `apps/core/models.py` `SoftDeleteModel` | **[scaffolded]** |

## 4. Secure SDLC

| Control | Where | Status |
|---|---|---|
| Secrets only in `.env` (git-ignored) + a committed `.env.example`; installer generates unique secrets per deployment | `.gitignore`, `.env.example`, `deploy/install.ps1` | **[scaffolded]** |
| `ruff` + `bandit` + `pip-audit` + `npm audit` + `manage.py check --deploy` in CI, gating every merge | `.github/workflows/ci.yml` | **[scaffolded]** |
| `makemigrations --check` in CI — no un-migrated model change ships | CI | **[scaffolded]** |
| All fixtures / demo data synthetic — no real child, family, or staff record in the repo | `apps/people/management/commands/seed_demo.py` (made-up names, refuses `DEBUG=False` without `--force`), test factories | **[done]** |
| `SECURITY.md` (how to report) + an OWASP ASVS-lite review before packaging | `docs/`, Phase 8 | **[phase 8]** |

## 5. Regulatory mapping

Campus implements the **superset of common controls** so it is defensible
under any of the regimes a client school might fall under.
`OPERATOR_PRIVACY_CHECKLIST.md` tells a given operator which switches to set
and which paperwork to keep, mapped to:

- **Canada** — PIPEDA; in Ontario, child care under the Child Care and Early
  Years Act, plus FIPPA/MFIPPA where a public body is involved and PHIPA for
  health information.
- **United States** — FERPA (education records), COPPA (collection from
  under-13s), and state student-data-privacy laws.

Defaults are Canada-first (the developer's locale); nothing is hard-coded to a
jurisdiction.
