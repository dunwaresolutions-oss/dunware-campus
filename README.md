# Campus

> Day-to-day operations for a daycare through a small secondary school — student CRM, registration, scheduling, attendance, lessons, grades, extra-curricular booking, family communication, fee tracking, and a parent/student portal — delivered as one bundled Windows installer that runs on the school's own server.

**Status:** working MVP · every module built, tested, and packaged · portfolio project
**Stack:** Django 5.2 LTS + Django REST Framework (served by `waitress`) · Next.js 15 (static export, no Node in production) · PostgreSQL 16 · Caddy (bundled reverse proxy + LAN HTTPS)
**Part of the [Dunware](https://github.com/dunwaresolutions-oss) portfolio.** Replaces the retired `student_management_system`.

<!-- Screenshots: dashboard, student record, scheduling calendar, parent portal -->

## Why

A licensed daycare or small school runs the same handful of things every day: who is here, where they should be, who taught what, who booked what, who registered, who to notify, and who owes what. Campus puts that in one authenticated app, on the school's own hardware, with the PII controls that a system holding children's medical, custody, and contact data has to have — encryption at rest for sensitive fields, per-record permissions, an audit log that records reads as well as writes, configurable retention and erasure, and versioned consent tracking.

## What's built

Eleven staff-console modules plus a restricted parent/student portal, all on one DRF API:

| Module | What it does |
|---|---|
| **Dashboard** | role-aware overview — today's roster, open incidents, live counts |
| **Students** | the child record + guardians, emergency contacts, authorized pickups, observations, health, documents; a change-request queue from the portal |
| **Registration** | application → review → offer / waitlist → enrolment; versioned consent |
| **Scheduling** | academic years, terms, rooms, closures, weekly session templates → generated dated sessions with live rosters |
| **Attendance** | group + date roster; check-out is refused to anyone not on the child's authorized-pickup list |
| **Lessons** | curriculum units, lesson plans (draft → published), resources |
| **Grades** | assessment schemes (marks / rubric / narrative / mixed), results, and a report-card editor — entries, preview, generate, release |
| **Booking** | tutoring & extra-curricular offerings, availability windows, capacity slots with a waitlist, ICS export |
| **Messages** | announcements, staff↔parent threads, structured incident reports with guardian acknowledgement — email only |
| **Billing** | **placeholder** — invoices, a fee ledger, and a manual "mark paid" workflow; no card processing |
| **Staff** | invite-based onboarding, a directory, and group assignments that drive instructor scoping |

Security and privacy are part of the data model, not a later pass: mandatory TOTP MFA for staff, `django-axes` lockout, Argon2, object-level permissions on every endpoint, field-level AES-256-GCM encryption at rest, an append-only read-and-write audit log, a break-glass admin behind an IP allow-list, retention / erasure / data-subject-export jobs, and an operator checklist mapping the controls to PIPEDA, Ontario CCEYA, FIPPA, PHIPA (Canada) and FERPA, COPPA, and US state law. `manage.py check --deploy` passes clean; the backend test suite runs behind `ruff`, `bandit`, and `pip-audit`.

## Design commitments

- **On-site only.** All data on the client's server. No SaaS, no cloud database, no vendor access. Single-tenant per install.
- **One installer.** `Campus-Setup.exe` bundles everything — a frozen Django app, the Next.js static build, a portable PostgreSQL, and Caddy — installs to `%ProgramData%\Campus`, runs as Windows services, and starts on boot. No Docker, Python, or Node needed on the target. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) and [`docs/PACKAGING.md`](docs/PACKAGING.md).
- **Security built first.** The encryption layer, roles, permissions, and audit log landed in Phase 1, before any feature code. See [`docs/PII_SECURITY.md`](docs/PII_SECURITY.md) and [`docs/ASVS_LITE_REVIEW.md`](docs/ASVS_LITE_REVIEW.md).
- **API-first.** Every screen — staff console and parent portal alike — talks to the same DRF API with explicit per-view permission classes.

## Repository layout

```
backend/          Django 5.2 + DRF
  config/         settings (base / dev / prod), urls, asgi, wsgi
  apps/
    core/         EncryptedField, base models, permission mixins, shared utils
    accounts/     custom User + roles, auth, MFA, portal access
    audit/        append-only audit log + access log + middleware
    people/       students, guardians, emergency contacts, authorized pickups
    health/       allergies, conditions, medications, action plans   (ENCRYPTED)
    registration/ applications, waitlist, offers, enrolment, consents
    scheduling/   class / room / resource calendars, staff rosters, closures
    attendance/   check-in / check-out, daily roster
    lessons/      curriculum units, lesson plans, resources
    grades/       assessment schemes, marks / rubrics / narratives, report cards
    booking/      tutor & extra-curricular offerings, availability, slots, waitlist
    communication/ announcements, threads, incident reports  (email only, no SMS)
    billing/      PLACEHOLDER — invoices, fee items, manual payment, gateway stub
    reporting/    exports, data-subject access / erasure, retention jobs
  requirements/   base.txt  dev.txt  prod.txt
frontend/         Next.js 15 (App Router, TS, Tailwind) — output: 'export'
  app/(console)/  staff app
  app/portal/     parent / student portal
  lib/            api client, auth, types
deploy/           campus.spec (PyInstaller), campus.iss (Inno Setup), install / repair /
                  backup / restore scripts, Caddyfile, docker-compose.yml (DEV ONLY)
docs/             ARCHITECTURE · DATA_MODEL · PII_SECURITY · ASVS_LITE_REVIEW ·
                  DEPLOYMENT · PACKAGING · OPERATOR_PRIVACY_CHECKLIST
```

## Run it (development)

```powershell
# backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements\dev.txt
copy ..\.env.example .env        # then edit; or use the dev compose for Postgres
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver 127.0.0.1:8001

# frontend (separate terminal)
cd frontend
npm install
npm run dev                       # http://localhost:3000, proxies /api to :8001
```

`deploy/docker-compose.yml` brings up PostgreSQL for development. It is **not** the shipped artifact — production is the bundled installer.

Load a synthetic school to explore the whole app:

```powershell
.venv\Scripts\python manage.py seed_demo --force        # grades 1-6, 2 classes each, 300 pupils
```

## Portfolio note

All fixtures and demo data are synthetic. No real child, family, or staff record is in this repository. Sensitive fields are encrypted at rest in a real deployment; see `docs/PII_SECURITY.md`.

## License

**All rights reserved** — published for portfolio and evaluation only, see [`LICENSE`](LICENSE). Not licensed for reuse. Licensing enquiries: dunwaresolutions@gmail.com
