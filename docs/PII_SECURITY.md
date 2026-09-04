# Campus — PII &amp; Security

Campus holds children's names, birth dates, home addresses, photos, medical
conditions, allergies, medications, custody and legal arrangements, and
guardian contact (and later financial) details. The controls below are
**built in Phase 1, before any feature code**, and `python manage.py check
--deploy` must pass clean before any package is built.

Status key: **[scaffolded]** structure exists in Phase 0 · **[phase 1]** built next · **[later]** a named later phase.

## 1. Data protection

| Control | Where | Status |
|---|---|---|
| Field-level **AES-256-GCM encryption at rest** for medical/allergy/medication/action-plan, custody &amp; legal notes, government IDs, uploaded documents | `apps/core/fields.py` (`EncryptedTextField`, `EncryptedCharField`) | **[scaffolded]** |
| Encryption key from `FIELD_ENCRYPTION_KEY` (env / installer-generated), **never** in DB, repo, or logs | `settings.base`, `deploy/install.ps1` | **[scaffolded]** |
| Prod refuses to start with no key | `settings/prod.py` | **[done]** |
| Encrypted storage volume for PostgreSQL + backups (BitLocker on the host) — installer checks &amp; warns | `deploy/install.ps1` | **[phase 9]** |
| TLS on the LAN, HSTS, HTTP→HTTPS redirect | `deploy/proxy/Caddyfile`, `settings/prod.py` | **[scaffolded]** |
| Encrypted backups (`pg_dump` \| age/GPG) + a restore drill | `deploy/backup.ps1`, `restore.ps1` | **[phase 8]** |
| No PII in logs — a filter redacts emails, phone numbers, and known-sensitive `key=value` before any record is emitted | `apps/core/logging.py` (`PIIScrubFilter`) | **[scaffolded]** |

## 2. Access control

| Control | Where | Status |
|---|---|---|
| Custom `User` with an explicit `role` | `apps/accounts/models.py` | **[scaffolded]** |
| DRF **deny-by-default** (`IsAuthenticated`), every viewset adds an explicit `RoleRequired` subclass | `settings.base` REST_FRAMEWORK, `apps/core/permissions.py` | **[scaffolded]** |
| **Object-level scoping** — parent sees only their children, teacher only their classes, health data gated to a named staff subset | `IsObjectOwnerOrStaff` + per-model `is_visible_to(user)` | **[phase 1 / per feature]** |
| **TOTP MFA** mandatory for staff roles, optional for parents | `django-otp`, `User.must_use_mfa`, a Phase-1 login-gate mixin | **[phase 1]** |
| **Argon2** password hashing, 12-char minimum, common-password + similarity validators | `settings.base` | **[done]** |
| **Login lockout** (`django-axes`) + endpoint rate limits (DRF ScopedRateThrottle: `auth` 10/min, `sensitive` 30/min) | `settings.base` | **[scaffolded]** |
| Session hardening — `Secure`/`HttpOnly`/`SameSite` cookies, 8-hour hard cap, rotate on login, full `SECURE_*` header set, CSRF enforced | `settings.base` / `prod` | **[scaffolded]** |
| **Break-glass Django admin** — superuser only, MFA + IP allow-list, every action audited | `settings/prod.py` `CAMPUS_ADMIN_IP_ALLOWLIST`, a Phase-1 admin mixin | **[phase 1]** |

## 3. Governance &amp; auditability

| Control | Where | Status |
|---|---|---|
| **Append-only audit log** — every create/update/delete **and every read** of a sensitive record (actor, action, object type+id, time, source IP). No values, ever. No update/delete path in the app; admin view is read-only. | `apps/audit/` (`AuditEntry`, `middleware`, `services.record()`) | **[scaffolded]** — automatic CRUD/READ hooks in **[phase 1]** |
| **Data minimization** — every PII field annotated with purpose + retention on the model (`SensitiveModel.PII_FIELDS` / `PII_PURPOSE`), mirrored into `DATA_MODEL.md` | `apps/core/models.py` | **[scaffolded]** |
| **Retention** — configurable window per record type; a scheduled `django-q2` job purges or anonymizes past-student data | `apps/reporting/`, `RETENTION_*` settings | **[phase 2]** |
| **Erasure** — admin "erase this person" action, blocked by a legal-hold flag, fully audited | `apps/reporting/` | **[phase 2]** |
| **Consent tracking** — each consent recorded with version + timestamp; portal review | `apps/registration/` | **[phase 2]** |
| **Data-subject access** — one-click "export everything we hold about this child" (admin + portal) | `apps/reporting/` | **[phase 2]** |
| **Soft delete** — records are not hard-deleted through the app; only retention/erasure jobs remove data, and they audit it | `apps/core/models.py` `SoftDeleteModel` | **[scaffolded]** |

## 4. Secure SDLC

| Control | Where | Status |
|---|---|---|
| Secrets only in `.env` (git-ignored) + a committed `.env.example`; installer generates unique secrets per deployment | `.gitignore`, `.env.example`, `deploy/install.ps1` | **[scaffolded]** |
| `ruff` + `bandit` + `pip-audit` + `npm audit` + `manage.py check --deploy` in CI, gating every merge | `.github/workflows/ci.yml` | **[scaffolded]** |
| `makemigrations --check` in CI — no un-migrated model change ships | CI | **[scaffolded]** |
| All fixtures / demo data synthetic — no real child, family, or staff record in the repo | `model-bakery`, test factories | **[convention]** |
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
