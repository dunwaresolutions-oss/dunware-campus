# Campus — Data Model

Filled in per phase. Each app owns its models; this file is the index and the
place where every **PII field** is listed with its **purpose** and **retention**
(the model carries the same via `SensitiveModel.PII_FIELDS` / `PII_PURPOSE`).

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

- `User(AbstractUser)` — `role`, `must_use_mfa`, `last_password_change`.
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
- `apps/grades/services.py`: `render_report_card_html()` always;
  `html_to_pdf()` uses WeasyPrint when present (bundled in the installer,
  Phase 9) and raises `PdfEngineUnavailable` otherwise; `generate_report_card()`
  stores a `.pdf` or falls back to `.html`. `release_report_card()` emails the
  guardians.
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
## billing  *(Phase 7 — done, placeholder by design)*

Real models, a real manual workflow — **no card processing**, nothing here
for PCI scope to attach to. Amounts are integer cents throughout.

- `FeeSchedule` — a priced template (one-time / monthly / per-term / annual).
- `Invoice(SensitiveModel)` — `DRAFT → ISSUED → PARTIALLY_PAID → PAID` (or
  `VOID`); `total_cents` / `paid_cents` / `balance_cents` computed via
  `.aggregate()` (never a stale prefetch cache) over `InvoiceLine` /
  `Payment`. Reads audited.
- `InvoiceLine` — fee-schedule-linked or ad hoc; `amount_cents` = quantity ×
  unit.
- `Payment` — **manual only**: cash / cheque / e-transfer + a reference,
  `received_by`. Created exclusively through `ManualGateway.charge()`.
- `Credit` — a manual adjustment in the family's favour (no automated refund
  path in v1).
- `apps/billing/gateways.py` — the `PaymentGateway` interface:
  `ManualGateway` (the only real option; `refund()` is intentionally
  unimplemented — issue a `Credit` instead) and `StripeGateway` (**stub** —
  both methods raise `NotImplementedError`, `# TODO v2`). `get_gateway()`
  reads `settings.FEATURE_PAYMENTS_GATEWAY` (default `"manual"`).
- `apps/billing/services.py`: `issue_invoice`, `mark_paid` (→ the gateway),
  `void_invoice`, `portal_summary(student)` — the read-only shape the parent
  portal shows (no card fields, ever).
- Access: front office (admin tier) manage everything; a parent reads their
  own child's non-draft invoices/payments only. No instructor access.

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
