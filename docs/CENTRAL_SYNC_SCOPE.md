# Campus Central — Sync Scope & C0 Decisions

**Status: C0 through C6 all done, including the console frontend —
2026-10-08/09.** This is the deliverable the Multi-School / Ministry
Deployment Action Plan (`Campus_MultiSchool_Action_Plan.html`, draft
2026-09-09) calls for before any Central code is written. It settles the C0
decision list from that plan. C1 (the `SiteConfiguration` link fields + the
companion link window), C2 (the export bundle), C3 (the Campus Central
Django skeleton), C4 (the ingest API), C5 (the sync agent) and C6 (the
console, backend *and* frontend) are built on top of it — see below. **C3
deliberately does not include the installer/packaging half of its own plan
scope** (`Campus-Central-Setup.exe`, PyInstaller, bundled Postgres/Caddy) —
Damien scoped this round to "Django skeleton + models only," given the
plan's own ~2–3 week estimate for that half alone. **C5 surfaced a real,
separate gap**: Campus has no scheduled-job worker process at all today, for
anything. **C6 shipped in two passes**: backend only first (Damien's own
call), then — after Damien chose "the Central frontend" as the next piece
to build — the real `frontend_central/` Next.js project too. The Central
installer and the scheduling gap remain two separate, unscheduled decisions;
neither is bundled into whatever comes next by default.

**Sequencing note:** Payments P1 (`SiteConfiguration` singleton, currency, fee
toggle — commit `a02b6f4`) has already landed, and `deployment_mode`
(`SINGLE`/`SCHOOL`/`HEADQUARTERS`) was scaffolded onto it at the same time.
C0/C1 are therefore unblocked and can proceed now, not "in parallel with" or
"after" payments as the plan's own note hedged — payments is simply done.

## Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| 1 | Sync scope — exact field list | See tables below. **Billing summary is included** (per-term totals issued/paid/outstanding only — never a per-family invoice). |
| 2 | One installer vs two | **Two.** `Campus-Setup.exe` (unchanged, handles `SINGLE`/`SCHOOL`) and a new `Campus-Central-Setup.exe`. No way to install HQ by accident. |
| 3 | Sync auth | **Bearer token** for v1 (per-school, minted/rotatable at Central). mTLS client certs noted as a future stronger option, not built now. |
| 4 | Cadence | **Nightly + on-demand.** Configurable interval, default 02:00 local with jitter, plus a manual trigger in the school's companion. |
| 5 | Read-only at HQ | **Confirmed.** No edit path from Central to a school, anywhere, in v1. An HQ→school "publish" channel (consent versions, circulars) stays a separate, later project. |
| 6 | Health data | **Confirmed excluded by default.** Allergies, conditions, medications, action plans never leave the school in v1. The "emergency health summary" opt-in (allergen + EpiPen flag only) stays noted, not built. |
| 7 | Central roles | **Resolved — see table below.** `MINISTRY_ANALYST` is aggregate/summary-only, no individual names. |
| 8 | Retention at Central | **90 days** after a student leaves or a school leaves the programme, then purged by Central's own retention job (built in C7). |
| 9 | Sequencing | **Resolved — start now** (see sequencing note above). |

## Central roles

| Role | Scope |
|---|---|
| `MINISTRY_ADMIN` | All schools, all synced modules, individual-record detail, the school registry, token issuance, the audit log. |
| `MINISTRY_ANALYST` | All schools, **aggregate/summary only** — dashboards, counts, trends, compliance rates. No individual student/guardian/staff name, email, phone or DOB ever rendered or returned by this role's endpoints. Enforced the same way Campus enforces every other role: an explicit permission class per endpoint, not a UI-only hide. |
| `DISTRICT_OFFICER` | Only the schools in one island/district, same detail level as `MINISTRY_ADMIN` within that scope. |

`MINISTRY_ANALYST` being aggregate-only means the `central_*` read tables need
a parallel aggregate view/serializer (counts and percentages, never a row with
a name in it) — call this out explicitly in C6 (Central console) so it isn't
built as "same table, hide some columns in the UI," which would be bypassable.

## What syncs — the curated snapshot

Unchanged from the plan's own tables, confirmed as-is for v1:

| Included by default | Detail |
|---|---|
| Directory | Students (name, DOB, student number, status, primary group, guardian count), guardians (name, email, phone, which children + relationship), staff (username, role, active). |
| Enrolments & groups | Student ⇄ group ⇄ dates ⇄ status; group name/kind/stage/capacity/live count. |
| Consents | Student, kind, granted/withheld, form version, recorded date. |
| Registration counts | Applications by status, waitlist sizes. |
| Attendance summaries | Per student per term: present/absent/late counts and %. Not every check-in row. |
| Report-card status | Per student per term: draft/finalised/released. Not individual marks. |
| Incident summary | Counts by category/severity/status per school per term. |
| **Billing summary** (confirmed in C0) | Per term: total issued/paid/outstanding. Not per-family. |

| Excluded by default | Why |
|---|---|
| Health & medical detail | Most sensitive PII. Opt-in-only emergency summary stays a later, not-v1 config flag. |
| Custody notes, government IDs | Never leave the school — excluded at the export stage. |
| Message threads, individual marks, per-family invoices, documents, individual attendance rows | Operational detail HQ has no standing need for. |

## Still outstanding before a real Ministry deployment (not blocking C1–C6 code)

- **Data-sharing agreement (DSA) template** — the Ministry becomes a data
  controller receiving PII; a signed DSA per school is a legal prerequisite
  before any school is actually linked to a live Central, even though the
  software itself can be built and tested (synthetic data) without one.
  Not drafted yet — flag before C8 (pilot), not before C1.
- The exact per-deployment configurability of this scope (a Ministry asking
  for a narrower or wider bundle than the defaults above) is designed for
  (the plan already calls for config-gated scope) but the *governance
  process* for approving a deviation isn't written down anywhere yet. Also a
  pre-C8 item, not a pre-C1 one.

## C1 — done (2026-10-08)

Built against the repo as it actually is today, not the plan's original
assumption (written before Payments P1 landed) of a single unified
first-run wizard: `deployment_mode` and "Region & fees" are already edited
from the in-browser **School settings** page, and integration secrets
(payment gateway keys) are already companion/CLI-only, never exposed to the
browser. C1 follows both of those existing patterns rather than inventing a
third:

- `SiteConfiguration` gained the `SCHOOL`-side link fields: `school_id`
  (UUID issued by Central), `central_url`, `central_token` (`EncryptedCharField`
  — same treatment as a payment gateway's secret key, never exposed through
  `/api/config/`), `sync_enabled`, `sync_interval_minutes`, `last_synced_at`,
  `last_sync_error`. Migration `0004_siteconfiguration_central_token_and_more`.
- **Campus can never be set to `HEADQUARTERS`** — enforced at the model
  (`SiteConfiguration.save()`), the `/api/config/` PATCH view, and
  `set_site_config`, all three refusing with the same plain explanation
  ("that's a separate product, Campus Central, with its own installer").
  This is the plan's "Headquarters → wrong installer" messaging, implemented
  as a hard refusal rather than a wizard dead-end.
- New management commands: `link_central` (requires `deployment_mode=SCHOOL`
  already set), `unlink_central` (clears the link, leaves the mode alone),
  `central_link_test` (pure reachability check — honestly always fails today,
  since Central's health endpoint doesn't exist until C3/C4).
- New companion window, **Campus — Central Link Setup**
  (`deploy/campus-central-setup-ui.ps1`), added to `campus.iss` the same way
  Remote Access Setup and Payments Setup are. No Headquarters option is
  offered in it at all.
- `docs/DEPLOYMENT.md` and `docs/DATA_MODEL.md` updated. 12 new tests
  (`apps/core/tests/test_central_link.py`); full suite 388 passed.

## C2 — done (2026-10-08)

`manage central_export --out <path> [--since <iso-datetime>]` — writes a
gzipped tar archive (`<table>.jsonl` per table + `manifest.json`), honouring
exactly the field list above. Refuses if this install has no `school_id`
(i.e. hasn't been linked via C1 yet).

- The actual table-building logic lives in `apps/core/central_export.py`
  (`build_central_export(since=None)`), kept separate from the command so it
  can be unit-tested directly without shelling out or writing a file — 16
  tests, each asserting both the right rows AND that an excluded field
  (government ID, custody notes, health, report-card narrative, incident
  description, individual invoice/application detail) genuinely never
  appears anywhere in the serialized output, not just that the intended
  fields are present.
- Every table function is an **allowlist projection built straight from the
  source models** — never a trimmed copy of a wider serializer (e.g.
  `apps.reporting.services.data_subject_export`) — so a field added to a
  model later can't silently leak into the bundle just because some other,
  broader export function happened to include it.
- **Row-level tables** (`students`, `guardians`, `groups`, `enrolments`,
  `consents`, `report_cards`) respect `--since` via each row's own
  `updated_at`. **`staff`** has no `updated_at` (`User` is Django's
  `AbstractUser`) and the four genuinely aggregate tables
  (`registration_counts`, `attendance_summary`, `incident_summary`,
  `billing_summary`) are always recomputed in full regardless of
  `--since` — they're small, cheap, and "only the changed counts" isn't a
  coherent idea for a pre-aggregated summary table this size.
- `billing_summary` is empty outright when `SiteConfiguration.collects_fees`
  is false, matching the C0 decision table's own "(if the school collects
  fees)" qualifier.
- The manifest's `content_hash` is a SHA-256 over every table's own name and
  JSONL bytes in sorted order — deterministic regardless of tar metadata
  (mtimes etc.), so Central can verify a bundle wasn't altered in transit
  once C4 exists to check it.
- 16 new tests (`apps/core/tests/test_central_export.py`); full backend
  suite 404 passed, ruff clean.

**Still nothing actually moves.** `central_export` only ever writes a local
file — no network call, no awareness that Central doesn't exist yet. Nothing
reads `sync_enabled`/`sync_interval_minutes` either; that's C5's job once
there's a C3/C4 Central to send the file to.

## C3 — done (Django skeleton + models only, 2026-10-09)

A genuine second Django project in the same repo, not a new app bolted onto
Campus's own `config/` — the isolation the whole plan is built around
(docs/CENTRAL_SYNC_SCOPE.md's own privacy section: a compromised school must
never expose Central, and vice versa) means Central's data can never share a
database with any school's own data, even for dev convenience.

- **New project**: `backend/central/` (`settings/{base,dev,test,prod}.py`,
  `urls.py`, `wsgi.py`, `asgi.py`) + `backend/manage_central.py` (Central's
  own `manage.py`-equivalent, distinct from Campus's, so there is never any
  ambiguity about which project's database a command is about to touch).
  Own `.env.central` (distinct filename from Campus's own `.env`), own
  `CENTRAL_DATABASE_URL`/`CENTRAL_FIELD_ENCRYPTION_KEY`/`CENTRAL_SECRET_KEY`
  env vars, own session cookie name (`campus_central_session`).
- **Reused as-is**, by the plan's own explicit instruction: `apps.core`
  (pulls in two harmless, always-empty, Campus-specific tables —
  `SchoolProfile`/`SiteConfiguration` — a known, accepted wart of "same repo,
  shared apps," not a bug), `apps.accounts` (User/Role/MFA — Central's own
  Ministry-staff accounts are rows in the *same* model class, just in
  Central's own separate database), `apps.audit`. **Not** reused: every
  school-operational app (people, health, registration, scheduling,
  attendance, lessons, grades, iep, booking, communication, staffchat,
  billing, reporting) — Central never runs a school's own modules.
- **Three new Ministry-only roles** on the shared `accounts.Role` enum:
  `MINISTRY_ADMIN`, `MINISTRY_ANALYST`, `DISTRICT_OFFICER` (a Campus/school
  install never creates a user with one of these — there's no feature that
  would). Fixed a real gap while adding them: `User.save()` only required
  MFA for `STAFF_ROLES`, which would have let a Ministry account — reading
  cross-school PII — skip MFA entirely; now requires it for `CENTRAL_ROLES`
  too.
- **New `apps/central` app**, 14 models: `CentralSettings` (singleton),
  `School` (the registry — `School.pk` *is* the `school_id` a linked Campus
  install stores in its own `SiteConfiguration.school_id`; `issue_token()`
  returns a bearer token once and stores only its SHA-256 hash, same
  shown-once convention as Campus's own MFA recovery codes), `SnapshotBatch`,
  and one `Central*` read table per table in the C2 export bundle
  (`CentralStudent`, `CentralGuardian`, `CentralStaff`, `CentralGroup`,
  `CentralEnrolment`, `CentralConsent`, `CentralReportCard`,
  `CentralRegistrationCounts`, `CentralAttendanceSummary`,
  `CentralIncidentSummary`, `CentralBillingSummary`) — each upserted by
  `(school, source_id)`, enforced with a real unique constraint, not just
  application-level discipline.
- **First-admin browser flow**: reuses `apps.accounts`'s existing
  `SetupStatusView`/`SetupAdminView` as-is via `central/urls.py` — they were
  already fully generic (just check whether any superuser exists), so no new
  view code was needed for this part of the plan's C3 scope.
- **Reusing `apps.core` without reusing Campus's own
  `INSTALLED_APPS`/settings** uncovered a real pytest wrinkle: a bare
  `pytest` (no path) recursively collects every `test_*.py` under
  `backend/`, including `apps/central/tests/`, which fails to even import
  under Campus's own `config.settings.test` (`apps.central` isn't in that
  project's `INSTALLED_APPS`, so Django's model registry refuses it). Fixed
  with `norecursedirs` in `pyproject.toml` — the default run skips `central`
  by directory name; the explicit invocation below still collects it. 14
  new tests, their own settings/database (in-memory SQLite, same as
  Campus's own test settings): `pytest apps/central --ds=central.settings.test`.
  Campus's own full suite (404 tests, unrelated to this app) still runs
  unchanged via plain `pytest`.
- `apps/accounts/models.py`, `backend/pyproject.toml` are the only
  Campus-side files this phase touched (beyond adding the new `central/` and
  `apps/central/` trees).

**Still nothing moves or connects.** No ingest endpoint exists (C4) — nothing
creates a real `SnapshotBatch` or populates a `Central*` row outside tests.
No console/dashboard (C6). No installer (deliberately deferred, see above).

## C4 — done (2026-10-09)

`POST /api/central/ingest/<school_id>/` (`apps/central/views.py`'s
`IngestView`) accepts the exact bundle `manage central_export` produces,
body-for-body: a raw `Authorization: Bearer <token>` header (no Django
session, no CSRF — this is a server-to-server call from a school's future
sync agent, C5, never a browser), verified against `School.verify_token()`.
An unknown school_id and an inactive one both 404 identically, so neither
can be distinguished from the other by a caller probing with a bad id.

The actual parse/validate/upsert logic lives in `apps/central/ingest.py`'s
`ingest_bundle(school, raw_bytes)`, kept separate from the view (same
reasoning as C2's `central_export.py`/command split) so it's fully testable
without HTTP:

- **Validates**, in order: the bundle's own `manifest["school_id"]` matches
  the school it was POSTed to (a bundle for the wrong school is rejected
  before a `SnapshotBatch` is even created — it's not this school's history
  to record); the manifest's `content_hash` against a fresh SHA-256 over the
  bundle's own raw table bytes (tamper/corruption detection, recomputed the
  same way `central_export`'s command built it — sorted table name + raw
  bytes, never a re-serialize-then-hash, which would risk a false mismatch
  from incidental JSON formatting differences); the bundle's
  `snapshot_schema_version` against `CentralSettings.snapshot_schema_version_supported`
  (refuses a bundle newer than this Central build understands).
- **Upserts** every row-level table (`students`, `guardians`, `staff`,
  `groups`, `enrolments`, `consents`, `report_cards`) into its matching
  `Central*` model by `(school, source_id)`, with an explicit field-name
  mapping from the bundle's own naming (`id`, `student_id`, `updated_at`) to
  Central's (`source_id`, `student_source_id`, `source_updated_at`).
- **Tombstones** deleted rows, but only correctly: a row-level table is only
  swept (delete anything for this school not present in *this* bundle) on a
  **FULL** bundle — an INCREMENTAL one only ever contains what changed, so
  absence proves nothing. The four aggregate tables
  (`registration_counts`, `attendance_summary`, `incident_summary`,
  `billing_summary`) are swept on **every** ingest regardless of `kind`,
  because the school's own export (C2) always sends these in full, every
  time, never partially — "only the changed counts" was never a coherent
  idea for them in the first place (see C2's own writeup above).
- **Runs the whole upsert inside one DB transaction**: a bundle is never
  partially applied. On failure, the `SnapshotBatch` records
  `rejected_reason` and `School.sync_status` flips to `ERROR`; on success,
  `applied=True`, `sync_status=OK`, `last_synced_at` and
  `snapshot_schema_version` are updated.
- **New management commands** `register_school` (creates a `School` row and
  calls `issue_token()` — the first thing in this whole effort that actually
  creates one outside a test) and `rotate_school_token`. No `.ps1` companion
  wrapper yet, deliberately: Central has no installer/frozen exe for a
  script to shell out to (see C3's own scope note) — wrapping a command that
  doesn't exist as a real executable yet would be a non-functional stub, not
  a usable tool. Add the wrapper once Central actually ships.
- 17 new tests (`apps/central/tests/test_ingest.py`) — including one that
  hand-builds a bundle in the exact tar.gz/JSONL/manifest format
  `apps/core/central_export.py` produces (that module lives in Campus's own,
  separate Django project and isn't importable under Central's settings —
  see C3's isolation note — so this is a deliberate *format contract* check,
  not a shortcut). Full `apps/central` suite now 31 tests; Campus's own
  404-test suite re-confirmed unaffected.

**Still nothing calls this automatically — see C5's own section, below, for why.**

## C5 — done, with one honest exception (2026-10-09)

The sync agent on the school (Campus) side: `apps/core/central_sync.py`'s
`run_sync(force_full=False)` builds the bundle (now via
`apps/core/central_export.py`'s `build_bundle_bytes()`, extracted this phase
so the `central_export` command and the sync agent can never build the
bundle two different ways) and POSTs it to
`<central_url>/api/central/ingest/<school_id>/` with the stored
`central_token` as a bearer header — no session, no CSRF, matching exactly
what C4's `IngestView` expects.

- **Decides FULL vs INCREMENTAL itself**: incremental (`since = last_synced_at`)
  normally, but forces a full export whenever `force_full` is passed, or
  `last_full_synced_at` is unset, or it's been 7+ days since the last one —
  the plan's own "weekly full reconcile," so a hard delete on the school
  side (which an incremental bundle's mere silence about a row can't prove)
  eventually reaches Central anyway. Tracked in a new field,
  `SiteConfiguration.last_full_synced_at`, kept deliberately separate from
  `last_synced_at` (migration `0005_siteconfiguration_last_full_synced_at`).
- **Records the real outcome, always**: success updates `last_synced_at`
  (and `last_full_synced_at` when the sync was full) and clears
  `last_sync_error`; a network failure or a non-2xx response from Central
  is recorded in `last_sync_error` instead, and `last_synced_at` is left
  exactly as it was — a failed attempt is not a sync.
- **`run_sync_with_retry()`** wraps `run_sync()` with exponential backoff
  (2s, 4s, ...) for whenever a real scheduled runner exists (see below). The
  on-demand path — the new `manage central_sync [--full]` command and the
  companion's new **"Sync now"** button/checkbox — calls `run_sync()`
  directly instead: blocking an interactive click for several seconds of
  retries on failure buys nothing a person can't get by just clicking again.
- 14 new tests (`apps/core/tests/test_central_sync.py`), all mocking
  `httpx.post` — no real network, no real Central needed to verify the
  FULL/INCREMENTAL decision, the retry/backoff behaviour, or that a failure
  is recorded without disturbing `last_synced_at`. Full Campus suite now 418
  tests; `apps/central`'s own 31 confirmed unaffected.

### The honest exception: nothing calls this on a timer

The plan's own C5 description assumes Campus already has a "payments-poller
infra" to reuse for scheduling. **It doesn't exist.** `django_q` is listed
in `THIRD_PARTY_APPS` and `Q_CLUSTER` is configured in settings, but no
`manage.py qcluster` worker process is registered anywhere in Campus's
installed topology — `campus.iss`/`deploy/*.ps1` register exactly three
Windows services (PostgreSQL, App, Proxy), none of them a job runner.
Registering a `django_q.models.Schedule` row for this feature would sit
inert on a real install: nothing would ever execute it. This is the *same
kind of plan-vs-reality mismatch found in C1* (the plan assumed a unified
first-run wizard that doesn't exist either) — except this one is a genuine
product-wide gap (**no** feature of Campus's can run on a schedule today,
not just this one), not something safe to quietly patch over as part of one
feature's own scope. It needs its own decision — a fourth Windows service? A
Windows Task Scheduler entry calling `manage central_sync` directly? — before
anything is registered against it. Noted here, left unscheduled, exactly
like the Central installer.

## C6 — done, backend only (2026-10-09)

Damien's explicit call: build the real data/API layer under a console, not
the console itself — no `frontend_central/` Next.js project exists, that's
its own, separately-sized follow-up (the plan's own estimate put the full
console at ~3–5 weeks, the single biggest remaining phase, and it's a whole
new piece of stack this effort hasn't touched at all).

- **New model**: `DistrictAssignment` (`user`, `district`) — which
  island/district a `DISTRICT_OFFICER` may see. `apps/central/scoping.py`'s
  `schools_visible_to(user)` is the *one* place this is decided; every view
  scopes through it rather than re-deriving district logic itself.
- **School registry over HTTP**: `GET`/`POST /api/central/schools/`,
  `GET /api/central/schools/<id>/`, `POST /api/central/schools/<id>/rotate-token/`
  — `MINISTRY_ADMIN`-only for the writes (registering a school / minting a
  token is an administrative action, not a reporting one), same shown-once
  token convention as the CLI commands (which still exist, for ops). A
  school outside a `DISTRICT_OFFICER`'s district 404s exactly like a school
  that doesn't exist — no confirmation either way.
- **Cross-school search**, `GET /api/central/search/?q=`, over
  `CentralStudent`/`CentralGuardian`/`CentralStaff` — and the C0 decision 7
  enforcement point: `MINISTRY_ANALYST` is refused this endpoint outright
  (`IndividualRecordAccess`'s role list simply excludes it) rather than
  being handed a response with fields filtered out. That was a deliberate
  design choice in the C0 doc itself ("enforced the same way Campus
  enforces every other role: an explicit permission class per endpoint, not
  a UI-only hide") — this is that promise actually kept in code, not just
  written down.
- **Aggregate dashboards**, `GET /api/central/dashboard/`
  (`?school_id=`, `?group_by=district`) and `.../export.csv` — enrolment
  totals, attendance %, consent-compliance %, incidents by category
  (`apps/central/dashboard.py`). Open to all three roles including the
  analyst, since every value here is a count or a percentage — the module's
  own docstring makes that the explicit reason it's safe, not an
  afterthought. CSV export needed a real fix mid-build: DRF's `Response`
  still runs the configured JSON renderer even when told a different
  `content_type`, silently re-encoding the CSV text as a JSON string — the
  view uses a plain Django `HttpResponse` instead.
- **Every one of the above calls `apps.audit.services.record()`** — reused
  completely as-is from Campus (confirmed generic, zero Campus-specific
  coupling, before relying on that). This is the plan's "Central runs its
  own append-only audit — every cross-school search, record view and export
  is logged" promise, now actually true, not just documented as a future
  intention.
- **PDF export is not built.** It reads naturally as a console/frontend
  rendering concern, and no PDF library is a dependency anywhere in this
  project yet — adding one speculatively, with no frontend to drive it, was
  judged not worth doing blind.
- 20 new tests (`apps/central/tests/test_console.py`) — covering district
  scoping (including the "no assignment = sees nothing" edge case), the
  admin-only writes, the analyst's search-vs-dashboard split specifically
  (one 403, one 200, same role), aggregate math correctness (including the
  no-data/no-crash case), and that every action actually left an
  `AuditEntry`. `apps/central` suite now 51 tests; Campus's own 418
  reconfirmed unaffected.

## C6, part 2 — the console frontend (2026-10-09)

A genuinely separate Next.js project, `frontend_central/` (own
`package.json`, own dev port `:3100`, rewriting `/api/*` to Central's own
backend on `:8002` in dev — the same pattern as Campus's own
`frontend/next.config.ts`, just pointed at a different backend). Not a new
area bolted onto Campus's `frontend/`, for the same reason C3's backend
isn't bolted onto `config/`: a genuinely different product.

- **Copied verbatim** (confirmed zero Campus-specific coupling first):
  `lib/api.ts`, `components/ui.tsx`, `components/Toast.tsx`. Design tokens
  (`app/globals.css`) are copied too but with the accent hue changed from
  teal to indigo — same variable *names* (`--campus-*`, kept so the copied
  components need zero edits), different colour, so Central looks visibly
  distinct from Campus to anyone running both side by side.
- **Adapted**: `lib/auth.ts` (Central's three roles, not Campus's seven),
  `lib/format.ts` (trimmed — no money()/currency, Central has no billing
  concept). **New**: `lib/schools.ts`, `lib/search.ts`, `lib/dashboard.ts`
  (incl. a CSV download that bypasses `api()`'s JSON assumption and
  triggers a real browser download), `lib/hooks.ts` (`useQueryParam` —
  dynamic route segments don't work under `output: "export"` without
  knowing every id at build time, so school detail is `/schools/detail/?id=`,
  the same query-param convention Campus's own frontend already uses for
  exactly this reason, not a new pattern).
- **Pages**: `/login`, `/setup`, `/mfa` (adapted from Campus's own, same
  flow, reusing `apps.accounts` on the backend); the console shell
  (`(console)/layout.tsx`) with role-filtered nav — **Search is hidden
  entirely from `MINISTRY_ANALYST`**, not just left to 403 if clicked, same
  C0-decision-7 spirit as the backend's own permission class; `/schools`
  (list + register-a-school form, showing the new token once); `/schools/detail`
  (full detail + rotate-token); `/search`; `/` (dashboard, with a school
  picker, a by-district toggle, and CSV export).
- **Found and fixed a real first-login dead end before it shipped**: the
  bootstrap account the shared `SetupAdminView` creates has role
  `SUPERADMIN` — not one of Central's three roles — so without a fix, the
  very first account on a fresh install would sign in, clear MFA, and then
  be refused by every single endpoint C6 built. Fixed by treating
  `is_superuser` as a break-glass superset in both
  `apps/central/permissions.py` (already updated) and
  `apps/central/scoping.py`'s `schools_visible_to()` (which had the exact
  same gap one layer down — permission check passing but the schools list
  itself still coming back empty). Caught *before* ever touching the
  frontend, by reasoning through what the shared bootstrap flow actually
  produces, not discovered by trial and error.
- **Found, scoped out, and documented rather than silently patched**: the
  shared `apps.accounts` staff-invite endpoint
  (`StaffInviteCreateSerializer`) only accepts Campus's own `STAFF_ROLES` as
  valid choices — `MINISTRY_ADMIN`/`MINISTRY_ANALYST`/`DISTRICT_OFFICER`
  are not selectable through it at all. **Creating additional Ministry
  accounts beyond the one break-glass bootstrap account doesn't work yet.**
  Not fixed this pass — broadening a serializer shared with Campus's own
  invite flow needs its own verification that it doesn't change Campus's
  behaviour, and "invite more Ministry staff" wasn't part of either backend
  or frontend C6 scope as actually asked. Flagged here as a real, known gap
  rather than quietly left for someone to discover later.
- **Verified live, not just built**: `tsc --noEmit` and `next lint` clean;
  `next build` produces a full static export (10 pages). Beyond that — since
  this introduces real frontend code that pytest can't exercise — ran
  Central's actual Django dev server (a throwaway SQLite database, never
  touching either of this machine's real Postgres services, to avoid any
  port collision with Campus's or Dunware's own running installs) and drove
  the *real* HTTP API end to end with a real session: login → MFA
  enrolment → MFA confirmation → register a school → read the dashboard →
  search — all against live code, not mocked, confirming the whole stack
  actually works together, not just in isolation.
- **One loose end, left open rather than hidden**: proxying through the
  Next.js *dev server's* rewrite (`frontend_central` on `:3100` → Central's
  backend on `:8002`) produced an extra redirect hop when tested with
  PowerShell's `Invoke-RestMethod`/`Invoke-WebRequest` (which enforce a
  stricter redirect-loop limit than a browser does) — hitting the backend
  directly on `:8002` never showed this. Likely a `trailingSlash: true` +
  dev-rewrite interaction inherited from the exact same `next.config.ts`
  pattern Campus's own frontend already uses, not something introduced
  here, and **irrelevant to production** (where Django serves the static
  export same-origin, no rewrite involved at all) — but not fully
  root-caused, and not verified clean in an actual browser (none available
  in this environment). Worth a real browser check before relying on the
  dev workflow day to day.

## C7 — done: the Central installer + Campus's own scheduler-gap fix (2026-10-09)

Damien asked for both of the two items C3/C5 had deliberately left
unscheduled, together, with no further scope-narrowing ("continue both").

### C7a — Campus's own missing job-scheduler worker (the C5 gap)

The literal gap: `Q_CLUSTER` has been configured in
`config/settings/base.py` since before this effort, but no
`manage.py qcluster` worker process was ever registered as a Windows
service — so no feature of Campus's, not just sync, could ever actually run
anything on a timer. Fixed as a fourth NSSM-wrapped service, "Campus
Scheduler" (`campus-app.exe manage qcluster`), registered exactly like
"Campus App" already is — no code change needed in `campus_app.py` itself,
since `cmd_manage` already proxies arbitrary Django management commands,
`qcluster` included.

- `deploy/install.ps1` — registers "Campus Scheduler" right after "Campus
  App"; added to the Automatic-start loop and the post-install verify step.
- `deploy/repair-campus.ps1` — (re)registers it, stops it before an
  `-RefreshAppFrom` binary swap (same exe as "Campus App" — a running
  `qcluster` process would otherwise lock the file), restarts/health-checks
  it alongside the other three.
- `deploy/uninstall-services.ps1` — stops and deletes it on uninstall.
- `deploy/campus.iss` — header comment updated; no `[Files]`/`[Run]` change
  needed (same frozen exe already shipped).
- `apps/core/central_sync.py`'s own docstring updated: the worker now
  exists, but **no `Schedule` row for `run_sync_with_retry` has been
  created yet** — that's a separate, still-open, feature-level decision
  (schedule unconditionally once linked? only when `sync_enabled`? on
  install or on `link_central`?), deliberately not bundled into this fix.
  Infra is unblocked; nothing is actually scheduled yet.
- **Verified**: all three edited `.ps1` files parsed clean with
  `[System.Management.Automation.Language.Parser]::ParseFile` (no syntax
  errors). Did **not** actually run `install.ps1`/`repair-campus.ps1`
  against this dev machine — both register real Windows services, and this
  machine already has two real Postgres services from other installs
  (`Campus PostgreSQL` stopped, `Dunware PostgreSQL` running); actually
  registering "Campus Scheduler" here was judged not worth the risk of
  touching real machine state for a mechanical, four-line addition that
  mirrors an already-registered, already-proven service pattern exactly.

### C7b — the Central installer (`Campus-Central-Setup.exe`)

New, separate installer producing a frozen Central build, mirroring every
file and every already-proven fix in Campus's own packaging (PACKAGING.md)
rather than rediscovering them:

- `backend/central_app.py` (new) — Central's own frozen entrypoint, the
  counterpart of `campus_app.py`. Same `serve`/`manage` contract, same
  waitress `trusted_proxy` fix (without it `SECURE_SSL_REDIRECT` loops
  behind Caddy — confirmed this is not Campus-specific, it's a generic
  waitress default). Same hotfix-overlay mechanism (generic, reused
  `apps.core` infra). **No** `_ensure_native_pdf_libs()` — confirmed (grep)
  nothing under `apps/central` uses WeasyPrint, so Central needs no GTK3
  runtime staged.
- `deploy/central.spec` (new) — PyInstaller spec, scoped to Central's actual
  `INSTALLED_APPS` (`apps.core`/`accounts`/`audit`/`central` only — no
  `django_q` hidden-import, Central has no scheduled jobs of its own).
  **Actually built**: `pyinstaller central.spec` → `dist/central-app/
  central-app.exe` (onedir), with the same build-time env vars Campus's own
  build needs (`DJANGO_SETTINGS_MODULE`, a placeholder `CENTRAL_SECRET_KEY`/
  `CENTRAL_FIELD_ENCRYPTION_KEY` — PyInstaller's Django hook imports
  settings during the freeze itself, confirmed by hitting and then fixing
  the exact `AttributeError: 'Settings' object has no attribute
  'ROOT_URLCONF'` PACKAGING.md already documents for Campus's build).
- **Actually smoke-tested**, not just built: `central-app.exe manage check`
  → "System check identified no issues"; `central-app.exe serve` against a
  throwaway SQLite database (never touching either of this machine's real
  Postgres services) answered `GET /api/healthz/` with `301` — the correct,
  expected `SECURE_SSL_REDIRECT` behaviour, matching exactly what Campus's
  own `install.ps1`/`repair-campus.ps1` already treat as "working" at that
  same health-check step.
- `deploy/proxy/central-caddyfile` (new) — Central's own Caddyfile template,
  own placeholder names (`CENTRAL_HOST`/`CENTRAL_API_BIND`/
  `CENTRAL_WEB_ROOT`) so it can never be confused with Campus's own if both
  are ever staged side by side; serves `frontend_central_out` directly off
  disk with the same `try_files`/`file_server` fix Campus's own Caddyfile
  needed (a bare `reverse_proxy /` would 404 the SPA, exactly as it did for
  Campus before that fix).
- `deploy/install-central.ps1` (new) — mirrors `install.ps1` end to end:
  secrets → `.env.central` (a **different filename** from Campus's own
  `.env`, matching `central/settings/base.py`'s own read of it, so the two
  can never be confused on a box running both), Postgres on **port 5433,
  not 5432** (a deliberate choice — a Ministry box running both a Campus
  install and Campus Central must never collide), migrate/collectstatic,
  Caddyfile templating, two NSSM services ("Campus Central App", "Campus
  Central Proxy" — no scheduler service, Central has no `django_q`), start
  + verify + trust-local-CA. Reuses the exact same staged
  `deploy/_thirdparty/{pgsql,caddy}` binaries Campus's own build uses — they
  are generic, not Campus-specific, so nothing extra needs staging in a
  checkout that already has them for a Campus build.
- `deploy/repair-campus-central.ps1`, `deploy/uninstall-central-services.ps1`
  (new) — mirror `repair-campus.ps1`/`uninstall-services.ps1`.
- `deploy/central.iss` (new) — Inno Setup script, mirrors `campus.iss`
  structure and its already-proven fixes (no `runascurrentuser`, optional
  third-party binaries at compile time). **Actually compiled**: Damien
  pointed at his local `C:\Program Files\Inno Setup 7`; `ISCC.exe
  central.iss` ran clean (361.984 sec, exit 0) and produced a real
  264,635,770-byte `dist\installer\Campus-Central-Setup.exe`, staging the
  frozen `central-app`, the `frontend_central` export, the Caddyfile
  template, and the same `deploy/_thirdparty/{pgsql,caddy}` binaries
  Campus's own installer uses. The entire pipeline — freeze, smoke test,
  compile — is now real and verified end to end, not just written.
- **Explicitly not built**: Central backup/restore tooling. Campus's own
  `backup.ps1`/`restore.ps1` have no Central equivalent — not asked for as
  part of "continue both," and not silently assumed to exist. A real,
  open gap for a future decision, not an oversight.

## C7c — two real bugs found in the sync agent during the live link test (2026-10-09)

Found while Damien actually tested `central_link_test`/`run_sync` against a
real, running Central install for the first time — both would have broken
**every** real sync, not just this test:

1. **TLS verification never trusted Caddy's own self-signed cert.**
   `httpx`'s default `verify=True` checks against its bundled `certifi` CA
   list, which never includes `tls internal`'s locally-generated cert — the
   *default* for both Campus's and Central's own Caddyfiles. `install.ps1`/
   `install-central.ps1`'s `Trust-CaddyLocalCA` already imports that cert
   into the Windows machine trust store so a *browser* stops warning about
   it, but `httpx` never looks there — confirmed by the exact same URL
   working fine in a browser and failing every `httpx` call with
   `CERTIFICATE_VERIFY_FAILED`. Fixed with the `truststore` package (new
   runtime dependency, `requirements/base.txt`), which makes Python's own
   `ssl` module delegate to the OS-native certificate store instead of
   `certifi` — closing the gap without weakening verification. New
   `apps/core/central_sync.py:trusted_ssl_context()`, passed as `verify=` to
   both the sync POST and `central_link_test`'s health GET.
2. **`central_link_test` hit the wrong health path.** It had
   `HEALTH_PATH = "/api/central/health/"`, written before C4 landed and the
   real path was known — `apps/central/urls.py` has no `/health/` route at
   all; the actual endpoint, registered in `central/urls.py`'s own
   `api_patterns`, is `/api/healthz/`. Fixed.

**Verified for real, twice**: once against the dev interpreter, once against
the actual frozen `campus-app.exe` (`truststore` needed an explicit
`collect_submodules("truststore")` hidden-import in `campus.spec` to bundle
cleanly) — both reached the real, live Central install's `/api/healthz/`
with `HTTP 200`, where every prior attempt had failed with
`CERTIFICATE_VERIFY_FAILED`. `Campus-Setup.exe` recompiled with the fix.

## C8 — case-file views, Ministry admin management, dashboard health metric (2026-10-09)

Damien reviewed the live console (C6) and found it "a bare skeleton" — no
way to create a second Ministry account, no individual record detail beyond
a bare search hit, and a dashboard with no actionable drill-down. Scoped as
three items (a fourth — syncing "who's authorized to pick up this child" —
deliberately deferred; the data doesn't exist in the sync bundle at all
yet). All three reuse data already synced; **no new migrations, no sync-
bundle changes** for any of them.

**C8a — per-student/guardian "case file" detail.** New `apps/central/
detail.py` (`build_student_detail`/`build_guardian_detail`) and two views,
`GET /api/central/students/<id>/` / `.../guardians/<id>/` — school, class,
enrolment history, attendance summary, guardians (with relationship +
contact), consents, report-card status for a student; contact info + every
synced child for a guardian. Same `IndividualRecordAccess` permission as
search (never `MINISTRY_ANALYST`), every view audited. Deliberately
on-demand only (assembled per-request from already-synced rows, nothing
fetched live from a school) — matches Damien's own stated principle:
Central should not constantly broadcast full student detail, but must
produce it immediately when genuinely needed (e.g. assisting a police
inquiry about a named student/guardian without the Ministry having to call
the school). Frontend: `/students/detail/?id=` and `/guardians/detail/?id=`
(query-param routing, matching every other detail page in this console),
linked from every search result (which also now shows which SCHOOL a
result belongs to — a real bug Damien reported in the same session: search
couldn't match a "first last" combined name query, and never showed the
school at all; both fixed in C7c, before this phase).

**C8b — Ministry administrator/account management.** The real,
already-documented gap: `apps.accounts`'s shared staff directory
(`UsersView`) and invite endpoint (`StaffInviteView`) only ever listed/
accepted Campus's own `STAFF_ROLES` — no way to create a second Central
account with a real Ministry role existed anywhere. Fixed by making both
**settings-driven** instead of hardcoding `STAFF_ROLES`: new
`ACCOUNTS_DIRECTORY_ROLES` / `ACCOUNTS_INVITE_MANAGER_ROLES` in
`config/settings/base.py` (Campus's own values, unchanged behaviour) and
`central/settings/base.py` (Central's three roles; `MINISTRY_ADMIN` +
break-glass `SUPERADMIN` may invite). Two new permission classes
(`apps.core.permissions.DirectoryAccess` / `InviteManagerOnly`) read the
setting at request time rather than importing one hardcoded role list —
the same view class now correctly serves two different role sets, one per
deployment, with zero new endpoints. New `apps/central/views.py`
`DistrictAssignmentsView`/`DistrictAssignmentDetailView` (`MinistryAdminOnly`)
— `DistrictAssignment` existed since C6 but had no API at all; a
`DISTRICT_OFFICER`'s actual scope (`schools_visible_to`) was previously
only settable via Django admin/shell. Frontend: new `/administrators/`
page (invite form, directory list, inline per-officer district
add/remove), and a genuinely missing `/invite/` accept page — Campus's own
frontend has had one since early on; `frontend_central` never did, so the
invite flow would have dead-ended at the final step. Both ported from
Campus's own proven pattern (zero Campus-specific coupling confirmed
before reusing).

**C8c — dashboard: a real, comparable health-concern metric.** Damien's
exact scenario: "someone with the right access should see that this
district has more illness than another." `IncidentReport.Category.ILLNESS`
was already a real Campus category and already flowing into
`CentralIncidentSummary` via C2's export — nothing new to sync. Added
`illness_count` and `illness_rate_per_100_students` to
`build_dashboard()`/`build_dashboard_by_district()` — a RAW count isn't a
fair cross-district comparison (a bigger district trivially has more
incidents), so the rate is normalized per 100 enrolled students. CSV export
fieldnames updated to match (would otherwise have hit a `ValueError` from
`csv.DictWriter` on the new dict keys). Frontend: a new dashboard card, and
the by-district view now sorts highest-illness-rate-first rather than an
arbitrary list — the point of grouping by district for health monitoring
is spotting which one stands out.

**Verified**: Campus's own full suite (418), Central's own full suite (76,
up from 52 — 24 new tests across `test_detail.py`,
`test_admin_management.py`, and additions to `test_console.py`), `ruff
check .` clean across the whole backend, `tsc --noEmit` / `eslint .`
clean, full `next build` (13 pages, up from 10). Shared `apps.accounts`
code was touched for C8b — both Campus's AND Central's full suites re-run
specifically to catch any cross-deployment regression; none found.

**Not built** (by design, this phase): syncing authorized-pickup data (C8
item 2, explicitly deferred); Central's own backup/restore tooling;
encryption-at-rest for Central's database when backups aren't running —
all separately flagged, not forgotten.

## C9 — Central's own backup/restore tooling + a continuous disk-encryption check (2026-10-09)

Damien, in the same feedback message that scoped C8: Central needs its own
backup capability (a confirmed, already-documented gap — Campus's
`backup.ps1`/`restore.ps1` had no Central equivalent), and "if no backup is
occurring the data should be at rest where it is encrypted."

**Backup/restore**: new `deploy/backup-central.ps1` / `restore-central.ps1`,
mirroring Campus's own proven pipeline exactly (pg_dump custom format +
`media_central` + a copy of `.env.central` as `env.backup`, GPG
symmetric-encrypted, never leaving plaintext on disk) with Central's own
paths/env-var names (`CENTRAL_DATABASE_URL`, `CENTRAL_FIELD_ENCRYPTION_KEY`,
`.env.central`, service `Campus Central App`). Archive filenames prefixed
`campus-central-` so Campus's and Central's backups can share a folder
without ever being confused. GnuPG is now staged into Central's own
installer (`install-central.ps1`, `central.iss`) — the same generic binary
Campus already uses; it wasn't before (a real gap: the scripts would have
had nothing to encrypt with). **Actually drilled**, not just written: ran
`backup-central.ps1 -Simulate` then `restore-central.ps1 -Simulate` in an
isolated scratch directory against the real staged `gpg.exe` — produced a
genuine encrypted archive, then genuinely decrypted and expanded it back,
proving the pipeline mechanically works end to end. **Deliberately not
built**: a `BackupRun`/"Backups" console page the way Campus's
`apps.reporting` provides — Central has no equivalent app; the scripts'
own exit code/output is the operator-facing signal for now, meant to be
wired into Task Scheduler same as Campus's own documented recommendation.

**Encryption at rest — a real architectural tension, resolved by NOT
breaking search.** Considered field-level AES-GCM encryption (the same
mechanism Campus already uses for health/custody/gov-ID fields) on
`CentralStudent`/`CentralGuardian`'s PII columns, the obvious first idea —
and rejected it: `apps/central/search.py` filters `first_name`/
`last_name`/`email`/`student_number` with `icontains`, a real SQL `LIKE`
match. Encrypted ciphertext has no substring relationship to its plaintext,
so encrypting any of those columns would silently and completely break
cross-school search — the literal "find a student by name so police don't
need to call the school" feature Damien described wanting, in the same
conversation. Campus's own existing encrypted fields are deliberately
never-searched for exactly this reason; Central's searchable name/email
fields are a different case, not a smaller version of the same one. A real
fix (searchable encryption via blind-indexed HMAC tokens) is a
meaningfully sized, separate piece of cryptographic engineering, not
something to bolt on silently — flagged here as a real open question, not
quietly built wrong or quietly skipped.

What WAS built instead, a real and more honestly-scoped gap: BitLocker
(volume-level encryption) was only ever checked **once, at install time**
(a PowerShell warning in `install.ps1`/`install-central.ps1`) — if disabled
afterward (a technician troubleshooting something unrelated, say), nothing
would ever warn again, silently and indefinitely. New `apps/core/checks.py`
`core.W002` (`disk_encryption_at_rest`) re-checks on every `manage check`
(and therefore `support_bundle`) via `manage-bde -status`, shared code so
both Campus and Central get it, not just Central. Frozen-only (a dev
checkout's drive status says nothing about a real deployment) and
fails-silently-safe on any error (missing tool, access denied, timeout,
unrecognized output) — an inconclusive read must never become a false
warning or a crash. **Verified**: 7 new tests covering every branch
(on/off/inconclusive/missing/denied/timeout/not-frozen); also actually run
against both real frozen exes on this machine — confirmed it fails safe
exactly as designed when `manage-bde` refuses a non-elevated caller
(`ERROR: An attempt to access a required resource was denied`, which this
dev shell genuinely hit), proving the fail-safe path for real, not just in
a mock. The real deployed services run as SYSTEM (full access), where the
positive on/off detection actually fires.

**Verified overall**: Campus's own full suite (425, up from 418) and
Central's own (76, unaffected — `apps.core` is shared) both clean, `ruff
check .` clean, both frozen exes re-built and smoke-tested, both
installers recompiled with everything above.

## Not scheduled

Nothing from the original C3/C5 deferral list remains open. Still
separately outstanding, flagged earlier and not re-raised since: the
Ministry data-sharing-agreement template and governance process for a
sync-scope deviation request (pre-C8 items); `apps.accounts`'s shared
staff-invite endpoint only accepting Campus's own `STAFF_ROLES` (C6's
documented, deliberately-not-fixed gap); an actual recurring `Schedule` row
for `run_sync_with_retry` (C7a, above); Central backup/restore tooling
(C7b, above). `Campus-Central-Setup.exe` itself has been compiled
successfully (Inno Setup 7, see C7b) — no longer open.
