# Campus — Data Model

Filled in per phase. Each app owns its models; this file is the index and the
place where every **PII field** is listed with its **purpose** and **retention**
(the model carries the same via `SensitiveModel.PII_FIELDS` / `PII_PURPOSE`).

**Phase 8 added no new models** — it's the hardening & test pass. See
`docs/ASVS_LITE_REVIEW.md`, `docs/BACKUP_RESTORE_DRILL.md`,
`docs/RETENTION_ERASURE_DRILL.md`, `SECURITY.md`, and
`tests_e2e/test_role_journeys.py`.

## Conventions

- All domain models inherit `apps.core.models.BaseModel` (UUID pk + timestamps).
- Anything holding high-sensitivity PII inherits `SensitiveModel` — the audit
  layer logs *reads* of these, and retention treats them with the shortest
  configured window.
- Records are `SoftDeleteModel` where a delete could orphan history; only
  retention/erasure jobs hard-delete, and they audit it.
- Encrypted columns use `EncryptedTextField` / `EncryptedCharField`
  (`apps/core/fields.py`). They are not queryable by value, by design.

## accounts  *(Phase 0/1)*

- `User(AbstractUser)` — `role`, `must_use_mfa`, `last_password_change`,
  `status` (`StaffStatus`: active / sick leave / on leave / sedentary duty /
  transferred / suspended / terminated — distinct from `is_active`, which
  gates login entirely; `status` instead tells the roster/directory *why* a
  staff member isn't in class without disabling their account. Meaningful
  for staff roles only; portal accounts stay `ACTIVE`).
- `StaffInvite` — single-use, expiring, no password.

| PII field | purpose | retention |
|---|---|---|
| `User.email`, `first_name`, `last_name` | account identity, notifications | while the account is active + 90 days |

## audit  *(Phase 0/1)*

- `AuditEntry` — append-only. Object type + id + action + actor snapshot + IP.
  No field values.
- Retention: `RETENTION_AUDIT_LOG_DAYS` (default ~10 years).

## people  *(Phase 2 — done)*

- `Group` (+ `GroupStaff`) — the age-agnostic unit; `GroupStaff` drives
  instructor visibility.
- `Student(SensitiveSoftDeleteModel)` — spine. `is_visible_to()` /
  `visible_queryset()` are the one scoping authority. `legal_hold` blocks
  retention + erasure; `left_on` starts the retention clock; `anonymized_at`
  records an erasure.
- `Guardian` + `GuardianLink` (relationship, custody, pickup, comms flags),
  `EmergencyContact`, `AuthorizedPickup`, `Observation`
  (`visible_to_guardians` gate), `Document` (file bytes AES-GCM encrypted on
  disk via `EncryptedFileSystemStorage`).
- `ContactChangeRequest(SensitiveModel)` *(Phase 6)* — a guardian's proposed
  edit to their own `email` / `phone` / `address` (or a per-child
  `receives_communications` / `lives_with` flag). `current_value` /
  `proposed_value` encrypted; `PENDING → APPROVED / REJECTED`. On approve the
  service applies the change to the target and audits it. Guardians never edit
  their record directly.

| PII field | purpose | retention |
|---|---|---|
| `Student.first_name/last_name/preferred_name` | identification on rosters, report cards | while enrolled + `RETENTION_PAST_STUDENT_DAYS` after `left_on`, then anonymized |
| `Student.date_of_birth` | age-band placement, ratio compliance | same |
| `Student.government_id` *(encrypted)* | government reporting where legally required | same; blanked on erase |
| `Student.government_id_type` *(plain — national ID / passport / birth cert / social insurance / voter ID / other)* | labels what kind of ID `government_id` holds; not itself an identifying value, so not encrypted | with the student |
| `Student.custody_notes` *(encrypted)* | custody / access affecting pickup | same |
| `Guardian.email` | announcements, incident reports, invoices | while linked to a current student + 1 yr |
| `Guardian.phone` *(encrypted)*, `Guardian.address` *(encrypted)* | urgent contact / correspondence | same |
| `GuardianLink.custody_notes` *(encrypted)* | who may collect / be told | with the link |
| `EmergencyContact.*`, `AuthorizedPickup.*` *(name plain, phones encrypted)* | emergency contact / pickup validation | with the student |
| `Observation.body` *(encrypted)* | developmental / incident record | with the student; erased on request |
| `Document.file` *(encrypted on disk)* | birth cert, custody order, IEP, immunization | with the student; deleted on erase |

## health  *(Phase 2 — done, all encrypted)*

- `HealthAccessGrant` — the **named staff subset**. `HealthProfile` (O2O),
  `Allergy`, `Condition`, `Medication`, `ActionPlan(SensitiveSoftDeleteModel)`.
- Encrypted: `blood_type`, `notes`, `allergen`, `reaction`, condition `name` +
  `details`, medication `name` / `dose` / `schedule` / `prescriber`, action-plan
  `plan`. Plain flags only: `severity`, `epipen_required`, `route`, `prn`,
  `ongoing` — the operational minimum a non-clinical front desk needs.
- Retention: shortest window; deleted outright by `erase_person`.

## registration  *(Phase 2 — done)*

- `Application(SensitiveSoftDeleteModel)` (+ `ApplicationDocument`, encrypted),
  `WaitlistEntry`, `Offer`, `Enrolment` (authoritative student⇄group span;
  one ACTIVE per pair), `Consent`.
- `Consent` is **versioned** — a change is a new row; `Consent.current_for(
  student, kind)` returns the latest. `kind` covers photo / media / field trip
  / data sharing / medical treatment / technology / sunscreen.
- Encrypted: `Application.applicant_phone` + `notes`, `Consent.notes`,
  `ApplicationDocument.file`.
- Lifecycle in `apps/registration/services.py`: `make_offer` → `respond_to_offer`
  → `convert_application` (creates the `Student` + `Enrolment`), each audited.

## scheduling  *(Phase 3 — done)*

- `Room`, `AcademicYear` → `Term` (kind = semester / trimester / quarter /
  rolling / year-round — the configurable term model), `Closure` (site-wide
  when `group` is null), `SessionTemplate` (weekly recurring meeting for a
  group in a term), `SessionOccurrence` (a concrete dated meeting).
- `apps/scheduling/services.py generate_occurrences(template, from_date,
  to_date)` — expands a template across the term, skips `Closure`s, idempotent
  on `(template, date)`. `SessionOccurrence.roster()` reads active
  `registration.Enrolment` rows as of the date — never a duplicate list.
- Not PII. Instructors are scoped to the groups they staff (`GroupStaff`).
- **Three different calendars read the same `SessionOccurrence` data, but
  are not the same view**: the Scheduling page's own calendar is a
  whole-school *exceptions* view (closures / early dismissals only — at
  hundreds of students, listing every class period there is unreadable and
  isn't its job); a student's Timetable tab and the parent/student portal's
  "Upcoming schedule" each show *her* actual class-by-class day
  (`ScheduleCalendar`'s `fixedStudentId`, filtered server-side to every
  group she's actively enrolled in — homeroom **and** every course-of-study
  section). `frontend/components/ScheduleCalendar.tsx`'s `showSessions`
  prop toggles between the two.

  A senior student (grade 10+) sits in two worlds at once — her homeroom
  (compulsory subjects) and her course-of-study section(s). The synthetic
  demo data (`seed_demo.py`) models this by reserving one period a day
  exclusively for course-of-study sections in those grades, so a homeroom
  subject can never double-book a track subject for the same student.
  That's a seed-data construction detail, not a schema rule — a real
  deployment's own scheduling policy (which subjects meet which day) comes
  from the school, not a hardcoded assumption.

## attendance  *(Phase 3 — done)*

- `AttendanceRecord(SensitiveModel)` — one per `(student, group, date)`.
  Sign-in / sign-out fields plus who dropped off / collected. `PII_FIELDS`:
  `dropped_off_by_name`, `collected_by_name`, `note`. Reads audited.
- `apps/attendance/services.py`: `check_in`, `mark_absent`, and `check_out` —
  which **only** releases a child to an active `AuthorizedPickup` for that
  student or a `GuardianLink` with `can_pickup=True`; anything else raises
  `NotAuthorizedToCollect` (API → 403). Every action audited.

## lessons  *(Phase 3 — done)*

- `CurriculumUnit`, `LessonPlan(SoftDeleteModel)` (draft → published,
  `author`), `LessonResource` (link / file / note). Not PII — teaching
  material. Instructor-scoped to their groups; admin sees all.
## communication  *(Phase 4 — done, email only)*

- `Announcement(SoftDeleteModel)` — audience (all staff / all parents / one
  group / whole site); `publish` action stamps `published_at` and emails the
  audience.
- `MessageThread(SensitiveModel)` + `Message` (body `EncryptedTextField`) —
  staff ↔ parent threads, participant-scoped.
- `IncidentReport(SensitiveModel, SoftDeleteModel)` — `description` /
  `action_taken` encrypted; `DRAFT → SENT → ACKNOWLEDGED`. `notify` emails the
  guardians; a parent records an `IncidentAcknowledgement`, and once every
  comms-guardian has, the report auto-flips to `ACKNOWLEDGED`.
- `OutboundEmail` — a log of every send (kind, subject, recipients, what it was
  about — **never the body**), so an operator can prove notification.
- `apps/communication/services.py`: `send_announcement`, `notify_incident`.
  **No SMS path anywhere.**

## grades  *(Phase 4 — done)*

- `AssessmentScheme` (kind = marks / rubric / narrative / mixed) +
  `RubricCriterion`; `Assessment` (`released` → parent-visible);
  `AssessmentResult(SensitiveModel)` (`narrative` encrypted, unique per
  student) + `RubricScore`.
- `ReportCard(SensitiveModel, SoftDeleteModel)` — `DRAFT → FINALIZED →
  RELEASED`; `summary_narrative` encrypted; `document` written through the
  encrypted storage. `ReportCardEntry` (`comment` encrypted) per subject.
  Also carries `grading_scheme` (FK, `SET_NULL`) and `cumulative_gpa`
  (nullable) — both **frozen at generation time**, so activating a different
  scheme later never rewrites an already-generated card.
- `GradingScheme` — a school's report-card grading policy: `name`,
  `uses_gpa`, `gpa_scale`, `is_active` (`.activate()` deactivates every other
  scheme transactionally; exactly zero or one active at a time). `GradeBand`
  (scheme FK, `label`, `min_percent`/`max_percent`, `gpa_points` nullable,
  `order`; unique per `(scheme, label)`) — the letter/level bands a mark
  falls into. Four real presets ship via a data migration (not a fixture):
  Bahamas 4.0 GPA, Ontario elementary 4-level, South Africa NCS 7-point,
  Botswana letter bands — none activated by default. Not PII; front office
  manages schemes/bands, everyone else reads.
- `apps/grades/services.py`: `render_report_card_html()` always;
  `html_to_pdf()` uses WeasyPrint when present (bundled in the installer,
  Phase 9) and raises `PdfEngineUnavailable` otherwise; `generate_report_card()`
  stores a `.pdf` or falls back to `.html`, and freezes the active scheme +
  `compute_cumulative_gpa(entries)` (unweighted mean of the term's
  GPA-bearing grade-band points — no credit-hour model to weight by) onto
  the card. `grade_for_mark(mark, scheme=...)` resolves a `GradeBand`.
  `release_report_card()` emails the guardians.
## booking  *(Phase 5 — done)*

- `Offering` — a bookable service (tutoring / music / sport / club). `provider`,
  `room`, `duration_minutes`, `capacity_per_slot`, `cancellation_hours`,
  `price_cents` (**placeholder** — Phase-7 billing hook, no charge in v1).
- `AvailabilityWindow` — recurring weekly availability, valid between two dates.
- `Slot` — a concrete bookable datetime with a capacity; `seats_left`,
  `refresh_status()` (`OPEN` / `FULL` / `CANCELLED`).
- `Booking(SensitiveModel)` — one student in one slot: `CONFIRMED` /
  `WAITLISTED` (with `waitlist_position`) / `CANCELLED` / `ATTENDED` /
  `NO_SHOW`. Unique per `(slot, student)` among non-cancelled. Reads audited.
- `apps/booking/services.py`: `generate_slots()` (expands windows, skips
  site-wide `Closure`s, idempotent), `book()` (confirm until capacity then
  waitlist), `cancel_booking()` (enforces the cutoff for non-staff; promotes
  the first waitlisted booking when a confirmed one is freed),
  `bookings_to_ics()` (RFC-5545 `VCALENDAR`, no dependency). `GET
  /api/bookings/ics/` returns the caller's bookings as a `.ics` download.
## billing  *(Phase 7 manual workflow + online payments, added 2026-09-16)*

Real models and two ways to be paid: recorded by hand, or online through the
school's own gateway account. **Campus never handles card data** — online
payments use each provider's hosted checkout page (PCI SAQ-A). Amounts are
integer cents throughout.

- `FeeSchedule` — a priced template (one-time / monthly / per-term / annual).
- `Invoice(SensitiveModel)` — `DRAFT → ISSUED → PARTIALLY_PAID → PAID` (or
  `VOID`); `total_cents` / `paid_cents` / `balance_cents` computed via
  `.aggregate()` (never a stale prefetch cache) over `InvoiceLine` /
  `Payment`. `invoice_number` (`INV-000001`-style, unique, assigned on
  creation) is what staff and guardians actually see on statements and
  payment records — never the raw internal id. Reads audited.
- `InvoiceLine` — fee-schedule-linked or ad hoc; `amount_cents` = quantity ×
  unit.
- `Invoice` (fields added with online payments) — `currency` (ISO-4217, defaulted from
  `SiteConfiguration` when the invoice is created) and `guardian` (the
  **billing guardian**, defaulted to the primary contact — a parent's access is
  checked against this guardian, not merely "linked to the child").
- `Payment` — either **manual** (`source=MANUAL`: cash / cheque / e-transfer /
  card-terminal / other + a `reference`, `received_by`, created through
  `ManualGateway.charge()`) or **gateway** (`source=GATEWAY`: `gateway` +
  `gateway_reference`, created only by resolving a `PaymentAttempt`).
- `Credit` — a manual adjustment in the family's favour. Refunds stay manual.
- `GatewayConfig` — the install's one configured gateway: `gateway`
  (`MANUAL` / `PAYSTACK` / `FLUTTERWAVE` / `STRIPE`), `mode` (`TEST` / `LIVE`),
  `public_key`, **`secret_key` (`EncryptedCharField`, AES-256-GCM)**,
  `subaccount_id` (reserved), `configured_by` / `configured_at`. Written only by
  `manage set_gateway_config` / the Payments Setup window — there is no browser
  write endpoint for keys.
- `PaymentAttempt` (`SensitiveModel`) — the checkout audit trail: `gateway`,
  unique `reference`, `amount_cents`, `currency`, `status` (`INITIALIZED` /
  `PENDING` / `SUCCESS` / `FAILED` / `ABANDONED` / `MISMATCH`), `checkout_url`,
  `gateway_session_id`, `channel`, **`raw_response` (`EncryptedTextField`)**,
  `initialized_by`, `last_checked_at`.
- `PaymentAttemptInvoice` — through table, one row per invoice per attempt with
  its `allocated_cents`; a combined charge is split proportionally
  (largest-remainder, so the cents sum exactly). A single-invoice attempt is one
  row, so the success path never branches on invoice count.
- `apps/billing/gateways.py` — the `PaymentGateway` interface: `ManualGateway`
  (`refund()` intentionally unimplemented — issue a `Credit`) and
  `OnlineGateway` (`initialize()` / `verify()`) with `PaystackGateway`,
  `FlutterwaveGateway` (v3 hosted checkout) and `StripeGateway` (Checkout).
  `get_gateway()` reads `GatewayConfig` first, then falls back to
  `settings.FEATURE_PAYMENTS_GATEWAY` (default `"manual"`). Kanoo is not
  implemented.
- `apps/billing/services.py`: `issue_invoice`, `mark_paid` (→ the gateway),
  `void_invoice`, `portal_summary(student)` (read-only, per-invoice `currency`,
  no card fields, ever), `initiate_online_payment` (rejects a combined charge
  whose invoices differ in billing guardian or currency),
  `resolve_payment_attempt` (a verified success with matching amount **and**
  currency creates the `Payment`; a mismatch is logged as `MISMATCH` and never
  auto-applied) and `allocate_payment`.
- API: `POST /api/invoices/pay/` (`invoice_ids` + optional `amount_cents`; a
  parent may combine only invoices billed to them, staff may generate a link for
  any family) and `GET /api/payment-attempts/{reference}/` (resolves live
  against the provider, at most one real check per 5 s). There is **no
  background reconciliation job yet**.
- Access: front office (admin tier) manage everything; a parent reads their
  own child's non-draft invoices/payments only. No instructor access. The whole
  Billing surface is closed when `SiteConfiguration.collects_fees` is false.

## core — site settings  *(SiteConfiguration added 2026-09-09/16)*

- `SchoolProfile` (singleton) — the school's identity for letterheads and the
  console: `name`, `legal_name`, `motto`, address, contact, `principal_name` /
  `principal_title`, `principal_user` (the designated principal), `signature`,
  `logo`, `report_card_footer`. Only the designated principal or a superadmin
  can upload or replace the signature (enforced server-side).
- `SiteConfiguration` (singleton) — `country` (ISO-3166), `currency` (ISO-4217;
  locks once any invoice exists), `locale`, `collects_fees`, `deployment_mode`
  (`SINGLE` / `SCHOOL`; `HEADQUARTERS` exists on the enum but is refused at
  save time — Campus is never Central, see docs/CENTRAL_SYNC_SCOPE.md).
  Edited under **School settings → Region & fees** or `manage set_site_config`.
  **Campus Central link** (C1, added 2026-10-08, SCHOOL mode only): `school_id`
  (UUID issued by Central), `central_url`, `central_token` (encrypted —
  `EncryptedCharField`, same treatment as a payment gateway's secret key, never
  exposed through `/api/config/`), `sync_enabled`, `sync_interval_minutes`,
  `last_synced_at`, `last_sync_error`, `last_full_synced_at` (C5, added
  2026-10-09 — tracked separately so a full resync can be forced at least
  weekly even when every sync in between was incremental). Set via
  **Start Menu → "Campus — Central Link Setup"** or `manage link_central` /
  `unlink_central` / `central_sync`.
- **Central export bundle** (C2, added 2026-10-08, no new tables —
  `apps/core/central_export.py` reads existing models into an allowlisted,
  denormalised snapshot): `manage central_export --out <path>` writes a
  gzipped tar of `<table>.jsonl` files + `manifest.json` (school_id,
  generated_at, schema version, per-table row counts, a SHA-256 content
  hash). See docs/CENTRAL_SYNC_SCOPE.md for the exact field list. Nothing
  reads `sync_enabled`/`sync_interval_minutes` yet — the sync agent that
  actually sends this file is C5.

## apps.central  *(C3, added 2026-10-09 — a separate Django project, not part of the `config` app above)*

Campus Central's own data model, in its own database (`backend/central/`,
`manage_central.py`) — see docs/CENTRAL_SYNC_SCOPE.md for the full writeup.
Reuses `apps.core`/`apps.accounts`/`apps.audit`; never the school-operational
apps. Three Ministry-only roles were added to the *shared* `accounts.Role`
enum for this (`MINISTRY_ADMIN`, `MINISTRY_ANALYST`, `DISTRICT_OFFICER`) — a
Campus/school install never creates a user with one.

- `CentralSettings` (singleton) — `name`, `region`, `snapshot_schema_version_supported`.
- `School` (the registry) — `name`, `district`, `sync_token_hash` (SHA-256,
  `issue_token()` returns the plaintext once), `last_synced_at`,
  `sync_status`, `snapshot_schema_version`, `contact_email`, `active`.
  `School.pk` *is* the `school_id` a linked Campus install stores in its own
  `SiteConfiguration.school_id`.
- `SnapshotBatch` — one row per received bundle: `school`, `kind`
  (FULL/INCREMENTAL), `manifest` (JSON), `content_hash`, `applied`,
  `rejected_reason`. Nothing creates one yet (C4).
- `Central*` read tables, one per C2 export-bundle table, each upserted by
  `(school, source_id)` with a real unique constraint: `CentralStudent`,
  `CentralGuardian`, `CentralStaff`, `CentralGroup`, `CentralEnrolment`,
  `CentralConsent`, `CentralReportCard`, `CentralRegistrationCounts` (one row
  per school, not source-keyed — it's an aggregate), `CentralAttendanceSummary`,
  `CentralIncidentSummary`, `CentralBillingSummary`.

Tests run with their own settings/database, never Campus's own:
`pytest apps/central --ds=central.settings.test`.

**Ingest (C4, added 2026-10-09, no new tables):** `POST /api/central/ingest/<school_id>/`
(bearer-token auth against `School.verify_token()`) accepts a
`central_export` bundle and upserts it into the tables above via
`apps/central/ingest.py`'s `ingest_bundle()`. `register_school` /
`rotate_school_token` management commands create a `School` row and mint
its token.

**Console backend (C6, added 2026-10-09, backend only — no frontend yet):**
- `DistrictAssignment` (new table) — `user`, `district`. Which island/district
  a `DISTRICT_OFFICER` may see (`apps/central/scoping.py`'s
  `schools_visible_to()`); meaningless for `MINISTRY_ADMIN`/`MINISTRY_ANALYST`,
  who see every school.
- `GET`/`POST /api/central/schools/`, `GET /api/central/schools/<id>/`,
  `POST /api/central/schools/<id>/rotate-token/` — the school registry over
  HTTP (`MINISTRY_ADMIN` only for the writes), replacing `register_school`/
  `rotate_school_token` being CLI-only.
- `GET /api/central/search/?q=` — cross-school search over
  `CentralStudent`/`CentralGuardian`/`CentralStaff`. Refused outright for
  `MINISTRY_ANALYST` (`IndividualRecordAccess`'s role list excludes it) —
  per C0 decision 7, enforced by an explicit permission class, not by
  filtering fields out of a shared response.
- `GET /api/central/dashboard/` (`?school_id=`, `?group_by=district`) and
  `GET /api/central/dashboard/export.csv` — aggregate-only figures
  (`apps/central/dashboard.py`): enrolment totals, attendance %,
  consent-compliance %, incidents by category. Open to all three roles,
  including the analyst, since nothing here is an individual record.
- Every one of the above writes an `AuditEntry` (`apps.audit`, reused as-is)
  — Central's own append-only audit of every cross-school view, search and
  export, per the plan's own privacy section.
- PDF export is not built this pass — it reads naturally as a console/frontend
  concern (rendering), not backend data, and no PDF library is a dependency
  of this project yet.
- **Permission fix, same pass**: the shared bootstrap flow
  (`apps.accounts`'s `SetupAdminView`) creates the first account with role
  `SUPERADMIN`, not a Central role — `apps/central/permissions.py` and
  `scoping.py`'s `schools_visible_to()` both now treat `is_superuser` as a
  break-glass superset (same way Campus's own `ADMIN_ROLE_NAMES` already
  treats `SUPERADMIN`), or the very first login on a fresh install would
  have been refused by every endpoint. **Known, documented, not-yet-fixed
  gap**: `apps.accounts`'s staff-invite flow only accepts Campus's own
  `STAFF_ROLES`, so there is no way yet to create a *second* Central account
  with a proper Ministry role.

**Console frontend (C6 part 2, added 2026-10-09):** `frontend_central/` — a
separate Next.js 15 project (own port, own `package.json`), not a new area
of Campus's own `frontend/`. Reuses `lib/api.ts`/`components/ui.tsx`/
`components/Toast.tsx` verbatim (confirmed zero Campus coupling first);
adapts `lib/auth.ts` to Central's three roles. Pages: `/login`, `/setup`,
`/mfa`, `/` (dashboard), `/schools` (list + register), `/schools/detail`
(detail + rotate-token), `/search` (hidden from `MINISTRY_ANALYST`'s nav
entirely, matching the backend's own refusal). `tsc`/`lint`/`next build`
all clean; the full login → MFA → register-school → dashboard → search
flow was verified against a real, live Django dev server (throwaway
SQLite, no shared service touched), not just pytest.

## portal  *(Phase 6 — done, no new app)*

The restricted parent / student surface. No new tables beyond
`people.ContactChangeRequest` — everything else is read-scoped through the
same `Student.visible_queryset` / `is_visible_to` the staff API uses.

- `GET /api/portal/dashboard/` — one call: the caller's children, each with
  upcoming sessions, recent attendance, released report cards, upcoming
  bookings, open (sent) incidents, outstanding consent kinds, and **`invoices`**
  (`billing.services.portal_summary` — status/total/balance/due date, never a
  card field); plus visible announcements, the caller's message threads, and
  their contact-change requests.
- `GET /api/portal/calendar/?student=ID&from=&to=` — the same
  sessions/closures/early-dismissals shape as the staff
  `/api/sessions/calendar/` (both built from the one shared
  `scheduling.views.calendar_payload()`), but scoped to a single student the
  caller already passes `Student.is_visible_to()` for — a 403 otherwise, a
  guardian never gets another family's schedule. Backs the portal's own
  embedded weekly/monthly calendar; not a relaxation of the staff-only
  session endpoints.
- `POST /api/portal/contact-change-requests/` — submit a change; front office
  `approve` / `reject`. `POST /api/portal/consents/` — record a consent
  decision as a new versioned `registration.Consent` row (never an update).
- Portal users cannot reach the dashboard as staff, and vice-versa.

## reporting  *(Phase 2 — done)*

No models of its own. `apps/reporting/services.py`:
- `data_subject_export(student)` — everything held about one child, decrypted,
  as a dict (audited `EXPORT`). CLI: `manage.py export_student --student <id>`.
- `erase_person(student)` — anonymize in place (names → "ERASED", encrypted
  fields blanked, health rows deleted), keeping the row so audit / financial
  history resolves. Blocked by `legal_hold`. Audited `ERASE`. CLI:
  `manage.py erase_student --student <id>`.
- `jobs.retention_sweep()` — audit-log anonymization + past-student erasure +
  stale-application purge. CLI: `manage.py run_retention` (django-q2 schedule
  in Phase 8).

Synthetic demo data: `manage.py seed_demo` (refuses under `DEBUG=False`
without `--force`).
