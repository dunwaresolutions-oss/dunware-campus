# Campus — Retention & Erasure Drill

Part of the Phase 8 hardening pass. Unlike the backup/restore drill, this one
needs no Postgres or bundled binaries — it exercises the Django ORM directly
— so it was run **for real** against a persistent (file-backed, not
in-memory) SQLite database seeded with `seed_demo`, not simulated.

## What was run

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings.dev"
$env:DATABASE_URL = "sqlite:///_retention_drill.sqlite3"
$env:FIELD_ENCRYPTION_KEY = "<32 bytes, base64>"
manage.py migrate --run-syncdb
manage.py seed_demo --students 10 --seed 99
```

Loaded a full synthetic daycare + secondary-school dataset: 6 groups, 4
teachers, 10 students, 15 guardians, allergies/conditions/medications,
observations, 6 applications, 29 consents, 78 scheduled sessions, 10
attendance check-ins, 12 lesson plans, 2 booking offerings with 24 slots and
36 bookings, and 10 invoices (8 paid).

### 1 — Data-subject access export

```
manage.py export_student --student <id> --out _drill_export.json
```

Result: a JSON file with the student's core record **decrypted** —
`government_id`, `custody_notes` read back in plaintext despite being
AES-GCM ciphertext in the database — plus every linked guardian (`phone`,
`address` decrypted), emergency contacts, pickups, observations, documents,
health data, enrolments, and consents. Confirmed an `EXPORT` audit entry was
written.

### 2 — Erasure ("erase this person")

```
manage.py erase_student --student <id> --reason "drill: guardian requested erasure" --yes
```

```
erased ecb11160-...: {'allergies': 0, 'conditions': 0, 'medications': 0,
                       'actionplans': 0, 'health_profile': 1}
```

Verified after the run:

| Field | Before | After |
|---|---|---|
| `first_name` / `last_name` | real name | `ERASED` |
| `anonymized_at` | `None` | set |
| `deleted_at` (soft-delete) | `None` | set |
| health rows (`Allergy`/`Condition`/`Medication`/`ActionPlan`/`HealthProfile`) | present | deleted |
| `AuditEntry` with `action=ERASE` | — | **1**, referencing the student |

### 3 — Retention sweep, including the legal-hold exception

Aged two withdrawn students to 3,000 days past `left_on` (well past the
default 2,555-day / ~7-year window) — one plain, one with `legal_hold=True`:

```
manage.py run_retention
{
  "audit": {"anonymized": 0},
  "students_erased": 1,
  "applications_purged": 0
}
```

| Student | `legal_hold` | Result |
|---|---|---|
| aged, no hold | `False` | anonymized (`first_name = ERASED`, `anonymized_at` set) |
| aged, on hold | `True` | **untouched** — real name intact, `anonymized_at` still `None` |

This is the control that matters most: a legal hold reliably blocks the
automated sweep from erasing a record it must not touch, while everything
else past the window is cleaned up without operator intervention.

## Result

**Pass.** Export, erasure, and retention-with-legal-hold all behaved exactly
as designed against real data in a real (if disposable) database. Drill
artifacts (`_retention_drill.sqlite3`, `_drill_export.json`) were deleted
after the run — nothing from it is committed to the repo.

## Re-running the drill

```powershell
cd backend
$env:DJANGO_SETTINGS_MODULE = "config.settings.dev"
$env:DATABASE_URL = "sqlite:///_retention_drill.sqlite3"
$env:FIELD_ENCRYPTION_KEY = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="   # test-only key
$env:SECRET_KEY = "drill-only-secret-key-not-for-production-use-0123456789"
.\.venv\Scripts\python.exe manage.py migrate --run-syncdb
.\.venv\Scripts\python.exe manage.py seed_demo --students 10
# pick a student id from the admin or a shell, then:
.\.venv\Scripts\python.exe manage.py export_student --student <id>
.\.venv\Scripts\python.exe manage.py erase_student  --student <id> --reason "drill"
.\.venv\Scripts\python.exe manage.py run_retention
Remove-Item _retention_drill.sqlite3
```

The equivalent as automated regression tests lives in
`apps/reporting/tests/test_governance.py` (runs on every CI build, against
SQLite in-memory) — this drill is the same code path exercised once, by hand,
end to end, with a human reading the output.
