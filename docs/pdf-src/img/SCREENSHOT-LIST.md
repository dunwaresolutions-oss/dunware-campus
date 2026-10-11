# Campus screenshot shot list

**Status, Sunday, September 27, 2026: 23 of these are captured for real**, programmatically, against a throwaway
local dev instance (SQLite, the real 1400-student "Windward Cay High School" seed data, MFA satisfied with a
computed TOTP code) driven headless over CDP — not mocked, not hand-drawn. Three corrections were found doing this
that the table below already reflects; see "Findings from the capture run" at the bottom.

Mirrors how Dunware's own screenshot set is organized (`D:\projects\dunware\docs\guide-src\img` /
`docs\pdf-src\img`, one PNG per real screen, lowercase-hyphenated filenames, `m-` prefix for phone/portal
views) — for use in the User Guide, whitepaper/technical guide, and the free Google Sites marketing site.
Every entry below corresponds to a real route in `frontend/app` (checked against the source tree, not
invented), so nothing on this list requires a screen that doesn't exist yet. Capture with realistic demo
data (a populated school, not an empty state) unless noted, at consistent browser width (same as Dunware's
guide captures) with no personally identifiable real-student data if taken against a live school's install.

## Console (staff-side, `(console)` route group)

| Status | Filename | Screen / route | Notes |
|---|---|---|---|
| ✅ | `dashboard.png` | `(console)` root | Overview landing page after sign-in. |
| ✅ | `people.png` | `(console)/people` | Student + guardian directory list view. |
| ✅ | `people-student-detail.png` | `(console)/people/student` | Single student profile (guardians, emergency contacts, authorized pickups, documents). |
| ✅ | `staff.png` | `(console)/staff` | Staff directory / roles view. |
| ✅ | `registration.png` | `(console)/registration` | Application → offer/waitlist → enrollment workflow. |
| ✅ | `attendance.png` | `(console)/attendance` | Attendance grid, tied to authorized pickups. |
| ✅ | `scheduling.png` | `(console)/scheduling` | Calendar / class scheduling view. |
| ✅ | `lessons.png` | `(console)/lessons` | Lesson / curriculum management. |
| ✅ | `grades.png` | `(console)/grades` | Gradebook / marks entry view. |
| ✅ | `grades-report-card.png` | `(console)/grades?tab=reportcards&focus=<id>` | Report card drawer for a real released card. Not a rendered PDF page — the in-app drawer; a PDF export shot would need a separate download+open step. |
| ✅ | `booking.png` | `(console)/booking` | Tutoring / extracurricular booking with waitlists. |
| ✅ | `billing.png` | `(console)/billing` | Invoice list / billing overview. |
| ✅ | `billing-invoice-detail.png` | `(console)/billing` (invoice detail modal) | Single invoice, lines, payments. Captured as the real row-click modal, not a separate route — none exists. |
| ❌ not captured | `billing-recurring-plan.png` | — | **Correction:** no distinct frontend route/tab for recurring billing plans was found in `frontend/app` as of this run, even though the backend/export side was built 2026-09-27 — likely UI-in-progress or config-only today. Re-check the repo before recapturing; don't invent this screen. |
| ✅ | `iep.png` | `(console)/iep` | IEP module — goals/accommodations/services (demo data, not a real student). |
| ✅ | `communication.png` | `(console)/communication` | Staff intranet chat / alerts. |
| ✅ | `audit.png` | `(console)/audit` | Audit log viewer (append-only — caption accordingly, never "unalterable"). |
| ✅ | `backups.png` | `(console)/backups` | Encrypted backup status/schedule view. |
| ✅ | `remote-access.png` | `(console)/remote-access` | Remote access mode switcher (Cloudflare Tunnel / WireGuard / public gateway) — caption as built, not yet field-tested. |
| ✅ | `settings.png` | `(console)/settings` | School profile, logo/letterhead, general settings. |

## Auth / onboarding

| Status | Filename | Screen / route | Notes |
|---|---|---|---|
| ✅ | `login.png` | `login` | Sign-in screen (username/password/authenticator-code fields). |
| ✅ | `mfa.png` | `mfa` | Real QR + secret + code entry, captured from an account mid-enrolment. |
| ❌ not captured | `invite.png` | `invite/accept` | Needs a real, unexpired staff-invite token (`POST /api/accounts/invite/` as an admin, then open the link) — skipped this pass for time; straightforward to add. |
| ❌ dropped | `setup.png` | `setup` | Only renders before any superadmin exists; once one does (needed for every other console shot), it just redirects to `login`, so it's not independently capturable in the same run without a second from-empty database. |

## Parent/guardian portal (`portal`)

| Status | Filename | Screen / route | Notes |
|---|---|---|---|
| ✅ | `m-portal.png` | `portal` | Real guardian login, schedule, attendance, consents-needed, announcements. |
| ❌ **not a real screen** | `m-portal-pay.png` | — | **Correction:** there is no `portal/pay` page in `frontend/app` — only `portal/pay/return`. The "Pay" action on the portal page goes straight to the gateway's own hosted checkout (Stripe/Paystack/Flutterwave), off-site, not a Campus screen. Drop this filename; use `m-portal.png`'s own Billing card (has a Pay button) instead. |
| ⚠️ captured, weak | `m-portal-pay-return.png` | `portal/pay/return` | Real screen, but captured with no real gateway session, so it shows the "we couldn't find that payment" empty state rather than a success receipt. Fine for a "here's the confirmation screen" mention; not a compelling proof screenshot — recapture after a real sandbox checkout completes if a stronger shot is wanted later. |

## Suggested use per Google Sites page (from the marketing plan)

- **Home:** `dashboard.png`, `billing-invoice-detail.png`, `m-portal.png` (top-of-page proof strip).
- **Features:** `people-student-detail.png`, `attendance.png`, `grades-report-card.png`, `booking.png`, `iep.png`, `communication.png`, `audit.png`.
- **Payments:** `billing.png`, `billing-invoice-detail.png`, `m-portal.png` (its Billing card), `m-portal-pay-return.png` (optional, weak — see note above).
- **Security & Privacy:** `mfa.png`, `audit.png`, `backups.png`, `remote-access.png`.
- **Pricing:** none needed (text/table page).
- **Compare / Bahamas / FAQ:** reuse dashboard.png and one relevant feature shot rather than new captures.

## Not on this list (don't screenshot yet)

Multi-school/Ministry "Campus Central" rollup, the Bahamas Kanoo/CaribPay gateway, the LemonSqueezy licensing
flow, and the data-import tool are all planned but not built — there is no real screen to capture for any of
these, so they must stay text-only claims (or omitted) on the marketing site until built.

## Findings from the capture run, Sunday, September 27, 2026

Captured programmatically (not by hand): a throwaway local dev instance was stood up (SQLite DB at
`backend/screenshot_run.sqlite3`, `backend/.env` with a generated `FIELD_ENCRYPTION_KEY` and
`CAMPUS_ADMIN_REQUIRE_MFA=False`, both dev-only and gitignored), seeded with `manage.py seed_demo --force`
(the real 1400-student "Windward Cay High School" dataset — the old 300-pupil primary-school seed has been
replaced since the 2026-09-12 note that called the high-school rewrite "not yet built"; worth reflecting that
in the Campus product note separately). A superadmin (`shotadmin`) was created and TOTP-enrolled by computing
a real 6-digit code from the API's own returned secret (RFC 6238, no external authenticator app needed for
automation). 23 of the 26 originally-listed screens were captured this way, driven headless over Chrome DevTools
Protocol — real rendered pages, real seeded data, not placeholders. Three corrections came out of doing this for
real rather than guessing from route names: **`m-portal/pay` doesn't exist** as an in-app screen (checkout is an
off-site redirect), **`billing-recurring-plan.png` has no frontend screen yet** despite the backend capability,
and **`setup.png` is mutually exclusive with every other console screenshot** (it only shows before any admin
account exists). `invite.png` was skipped for time, not blocked — same technique as `mfa.png` would work (create
a `StaffInvite` via the API as the superadmin, then open its accept link).

The two throwaway dev servers used to capture these (`backend` on `127.0.0.1:8002`, `frontend` on
`127.0.0.1:3011`) may still be running locally in the background from this session — safe to leave (throwaway
SQLite DB, no real data, not exposed off this machine) or close the terminal windows/processes when done with
them. `backend/.env` should stay out of git (already covered by `.gitignore`) and can be deleted once no longer
needed for a rerun.
