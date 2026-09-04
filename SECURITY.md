# Security Policy

Campus holds children's names, birth dates, addresses, medical and custody
information, and guardian contact detail. Reports about a real or suspected
vulnerability are taken seriously and handled privately.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security report.** Email
**dunwaresolutions@gmail.com** with:

- what you found and why it's a vulnerability (not just a bug),
- the steps to reproduce it,
- the affected version / commit,
- your assessment of impact, if you have one.

Expect an acknowledgement within a few days. Campus is currently a
single-maintainer project — a fix timeline will follow the acknowledgement
once severity is assessed. Coordinated disclosure is welcome: please hold
public details until a fix has shipped to installs, since this is an on-site
product without a central "everyone auto-updates today" release channel.

## Supported versions

Campus has not had a v1.0 release yet (see `docs/DATA_MODEL.md` build
phases). Once it does, security fixes will target the current major version;
this section will be updated with the specifics at that point.

## What's already built in

This is not a from-scratch security posture — see `docs/PII_SECURITY.md` for
the full control matrix and `docs/ASVS_LITE_REVIEW.md` for a control-by-control
self-review against OWASP ASVS. Headlines:

- AES-256-GCM field- and document-level encryption at rest, key never in the
  repo or logs, production refuses to start without it.
- Mandatory TOTP MFA for staff, Argon2 password hashing, login lockout
  (django-axes), full session-cookie hardening.
- Deny-by-default access control with object-level scoping tested per role
  (`apps/*/tests/`) and exercised end to end (`tests_e2e/`).
- An append-only audit log recording every write **and every read** of a
  sensitive record.
- Data-subject access export and a legal-hold-aware erasure path
  (`docs/RETENTION_ERASURE_DRILL.md`).
- `ruff` + `bandit` + `pip-audit` + `npm audit` + `manage.py check --deploy`
  gate every CI run (`.github/workflows/ci.yml`).

## Scope

In scope: the Django/DRF backend, the Next.js frontend, the deployment
scripts under `deploy/`. Out of scope: the third-party services a school
operator chooses to run alongside Campus (their own SMTP provider, their own
network), and denial-of-service against a single on-site LAN box, which isn't
a meaningful threat model for this product.
