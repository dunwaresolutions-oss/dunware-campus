# Campus

> Day-to-day operations for a daycare through a small secondary school — student CRM, registration, scheduling, attendance, lessons, grades, booking, communication, and a parent/student portal — delivered as one bundled Windows installer that runs on the school's own server.

**Status:** in development · Phase 0 scaffold · portfolio project
**Stack:** Django 5.2 LTS + Django REST Framework (served by `waitress`) · Next.js 15 (static export, no Node in production) · PostgreSQL 16 · Caddy (bundled reverse proxy + LAN HTTPS)
**Part of the [Dunware](https://github.com/dunwaresolutions-oss) portfolio.** Replaces the retired `student_management_system`.

<!-- Screenshots: dashboard, student record, scheduling calendar, parent portal -->

## Why

A licensed daycare or small school runs the same handful of things every day: who is here, where they should be, who taught what, who booked what, who registered, who to notify, and who owes what. Campus puts that in one authenticated app, on the school's own hardware, with the PII controls that a system holding children's medical, custody, and contact data has to have — encryption at rest for sensitive fields, per-record permissions, an audit log that records reads as well as writes, configurable retention and erasure, and consent tracking.

## Design commitments

- **On-site only.** All data on the client's server. No SaaS, no cloud database, no vendor access. Single-tenant per install.
- **One installer.** `Campus-Setup.exe` bundles everything — a frozen Django app, the Next.js static build, a portable PostgreSQL, and Caddy — installs to `%ProgramData%\Campus`, runs as Windows services, and starts on boot. No Docker, Python, or Node needed on the target. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
- **Security is built first.** The encryption layer, roles, permissions, and audit log land in Phase 1, before any feature code. `python manage.py check --deploy` must pass clean before any package is built. See [`docs/PII_SECURITY.md`](docs/PII_SECURITY.md).
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
deploy/           docker-compose.yml (DEV ONLY), Caddyfile, install / backup / restore scripts
docs/             ARCHITECTURE · DATA_MODEL · PII_SECURITY · DEPLOYMENT · OPERATOR_PRIVACY_CHECKLIST
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

`deploy/docker-compose.yml` brings up PostgreSQL for development. It is **not** the shipped artifact.

## Portfolio note

All fixtures and demo data are synthetic. No real child, family, or staff record is in this repository. Sensitive fields are encrypted at rest in a real deployment; see `docs/PII_SECURITY.md`.

## License

**All rights reserved** — published for portfolio and evaluation only, see [`LICENSE`](LICENSE). Not licensed for reuse. Licensing enquiries: dunwaresolutions@gmail.com
