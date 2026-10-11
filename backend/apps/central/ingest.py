"""C4 -- the ingest side of the sync mechanism. ``ingest_bundle()`` is the
whole thing: parse the tar.gz a school's `central_export` produced, validate
it against this ``School`` and this install's own understanding of the
snapshot schema, and transactionally upsert every table into the matching
``Central*`` read tables. Kept separate from the DRF view (apps/central/views.py)
so it's fully testable without HTTP.

Field-name mapping note: the bundle's own JSONL rows use the school's own
naming (``id``, ``student_id``, ``updated_at``, ...); Central's models use
``source_id``/``*_source_id``/``source_updated_at`` to make unmistakably
clear, everywhere a Central row is read, that these are copies of another
database's ids, never Central's own. The mapping lives entirely in this
file's ``_UPSERTERS`` table.
"""
from __future__ import annotations

import hashlib
import json
import tarfile
from io import BytesIO

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.central.models import (
    CentralAttendanceSummary,
    CentralBillingSummary,
    CentralConsent,
    CentralEnrolment,
    CentralGroup,
    CentralGuardian,
    CentralIncidentSummary,
    CentralRegistrationCounts,
    CentralReportCard,
    CentralSettings,
    CentralStaff,
    CentralStudent,
    School,
    SnapshotBatch,
)

# Tables keyed by (school, source_id) -- tombstoned only on a FULL bundle,
# since an INCREMENTAL one only ever contains what changed, and absence from
# it says nothing about whether the rest still exists.
SOURCE_KEYED_TABLES = (
    "students", "guardians", "staff", "groups", "enrolments", "consents", "report_cards",
)
# The four aggregate tables (apps/core/central_export.py's own _attendance_summary
# etc.) are recomputed and sent IN FULL by the school on every export, regardless
# of --since -- so Central always fully replaces its own copy of them on every
# ingest, FULL or INCREMENTAL alike.
AGGREGATE_TABLES = (
    "registration_counts", "attendance_summary", "incident_summary", "billing_summary",
)


class IngestError(Exception):
    """A bundle was rejected. The message is safe to return to the caller --
    never includes anything from inside the bundle's own PII-bearing rows."""


def _dt(value):
    if not value:
        return None
    return parse_datetime(value)


def _d(value):
    if not value:
        return None
    return parse_date(value)


def _extract(raw_bytes: bytes) -> tuple[dict, dict[str, bytes]]:
    """Returns (manifest, {table_name: raw jsonl bytes}). Raises IngestError
    on anything that isn't a well-formed tar.gz with a manifest.json."""
    try:
        with tarfile.open(fileobj=BytesIO(raw_bytes), mode="r:gz") as tar:
            members = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
    except (tarfile.TarError, OSError) as e:
        raise IngestError(f"not a valid gzipped tar bundle: {e}") from e

    if "manifest.json" not in members:
        raise IngestError("bundle has no manifest.json")
    try:
        manifest = json.loads(members.pop("manifest.json"))
    except json.JSONDecodeError as e:
        raise IngestError(f"manifest.json is not valid JSON: {e}") from e

    tables = {}
    for name, data in members.items():
        if name.endswith(".jsonl"):
            tables[name[: -len(".jsonl")]] = data
    return manifest, tables


def _verify_content_hash(manifest: dict, raw_tables: dict[str, bytes]) -> None:
    hasher = hashlib.sha256()
    for name in sorted(raw_tables):
        hasher.update(name.encode("utf-8"))
        hasher.update(raw_tables[name])
    computed = hasher.hexdigest()
    if computed != manifest.get("content_hash"):
        raise IngestError("content hash does not match -- the bundle is corrupt or was altered")


def _rows(raw_tables: dict[str, bytes], name: str) -> list[dict]:
    data = raw_tables.get(name, b"")
    text = data.decode("utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def _upsert_students(school: School, rows: list[dict]) -> set:
    seen = set()
    for r in rows:
        source_id = r["id"]
        CentralStudent.objects.update_or_create(
            school=school, source_id=source_id,
            defaults={
                "first_name": r["first_name"], "last_name": r["last_name"],
                "date_of_birth": _d(r["date_of_birth"]), "student_number": r["student_number"],
                "status": r["status"],
                "primary_group_source_id": r.get("primary_group_id"),
                "guardian_count": r.get("guardian_count", 0),
                "source_updated_at": _dt(r.get("updated_at")),
            },
        )
        seen.add(source_id)
    return seen


def _upsert_guardians(school: School, rows: list[dict]) -> set:
    seen = set()
    for r in rows:
        source_id = r["id"]
        CentralGuardian.objects.update_or_create(
            school=school, source_id=source_id,
            defaults={
                "first_name": r["first_name"], "last_name": r["last_name"],
                "email": r.get("email", ""), "phone": r.get("phone", ""),
                "children": r.get("children", []),
                "source_updated_at": _dt(r.get("updated_at")),
            },
        )
        seen.add(source_id)
    return seen


def _upsert_staff(school: School, rows: list[dict]) -> set:
    seen = set()
    for r in rows:
        source_id = r["id"]
        CentralStaff.objects.update_or_create(
            school=school, source_id=source_id,
            defaults={"username": r["username"], "role": r["role"], "active": r["active"]},
        )
        seen.add(source_id)
    return seen


def _upsert_groups(school: School, rows: list[dict]) -> set:
    seen = set()
    for r in rows:
        source_id = r["id"]
        CentralGroup.objects.update_or_create(
            school=school, source_id=source_id,
            defaults={
                "name": r["name"], "kind": r["kind"], "stage_label": r.get("stage_label", ""),
                "capacity": r.get("capacity"), "active": r.get("active", True),
                "live_count": r.get("live_count", 0),
                "source_updated_at": _dt(r.get("updated_at")),
            },
        )
        seen.add(source_id)
    return seen


def _upsert_enrolments(school: School, rows: list[dict]) -> set:
    seen = set()
    for r in rows:
        source_id = r["id"]
        CentralEnrolment.objects.update_or_create(
            school=school, source_id=source_id,
            defaults={
                "student_source_id": r["student_id"], "group_source_id": r["group_id"],
                "start_date": _d(r["start_date"]), "end_date": _d(r.get("end_date")),
                "status": r["status"], "source_updated_at": _dt(r.get("updated_at")),
            },
        )
        seen.add(source_id)
    return seen


def _upsert_consents(school: School, rows: list[dict]) -> set:
    seen = set()
    for r in rows:
        source_id = r["id"]
        CentralConsent.objects.update_or_create(
            school=school, source_id=source_id,
            defaults={
                "student_source_id": r["student_id"], "kind": r["kind"], "version": r["version"],
                "granted": r["granted"], "recorded_at": _dt(r["recorded_at"]),
                "source_updated_at": _dt(r.get("updated_at")),
            },
        )
        seen.add(source_id)
    return seen


def _upsert_report_cards(school: School, rows: list[dict]) -> set:
    seen = set()
    for r in rows:
        source_id = r["id"]
        CentralReportCard.objects.update_or_create(
            school=school, source_id=source_id,
            defaults={
                "student_source_id": r["student_id"], "term_source_id": r["term_id"],
                "status": r["status"], "source_updated_at": _dt(r.get("updated_at")),
            },
        )
        seen.add(source_id)
    return seen


_SOURCE_KEYED_UPSERTERS = {
    "students": (_upsert_students, CentralStudent),
    "guardians": (_upsert_guardians, CentralGuardian),
    "staff": (_upsert_staff, CentralStaff),
    "groups": (_upsert_groups, CentralGroup),
    "enrolments": (_upsert_enrolments, CentralEnrolment),
    "consents": (_upsert_consents, CentralConsent),
    "report_cards": (_upsert_report_cards, CentralReportCard),
}


def _replace_registration_counts(school: School, rows: list[dict]) -> None:
    if not rows:
        return
    row = rows[0]
    CentralRegistrationCounts.objects.update_or_create(
        school=school,
        defaults={
            "applications_by_status": row.get("applications_by_status", {}),
            "waitlist_by_group": row.get("waitlist_by_group", {}),
        },
    )


def _replace_attendance_summary(school: School, rows: list[dict]) -> None:
    seen = set()
    for r in rows:
        CentralAttendanceSummary.objects.update_or_create(
            school=school, student_source_id=r["student_id"], term_source_id=r["term_id"],
            defaults={
                "present": r.get("present", 0), "absent": r.get("absent", 0),
                "late": r.get("late", 0), "present_pct": r.get("present_pct"),
            },
        )
        seen.add((str(r["student_id"]), str(r["term_id"])))
    for row in list(CentralAttendanceSummary.objects.filter(school=school)):
        if (str(row.student_source_id), str(row.term_source_id)) not in seen:
            row.delete()


def _replace_incident_summary(school: School, rows: list[dict]) -> None:
    seen = set()
    for r in rows:
        key = (r["term_id"], r["category"], r["severity"], r["status"])
        CentralIncidentSummary.objects.update_or_create(
            school=school, term_source_id=r["term_id"], category=r["category"],
            severity=r["severity"], status=r["status"],
            defaults={"count": r.get("count", 0)},
        )
        seen.add(key)
    for row in list(CentralIncidentSummary.objects.filter(school=school)):
        if (str(row.term_source_id), row.category, row.severity, row.status) not in {
            (str(a), b, c, d) for a, b, c, d in seen
        }:
            row.delete()


def _replace_billing_summary(school: School, rows: list[dict]) -> None:
    seen = set()
    for r in rows:
        CentralBillingSummary.objects.update_or_create(
            school=school, term_source_id=r["term_id"],
            defaults={
                "issued_cents": r.get("issued_cents", 0), "paid_cents": r.get("paid_cents", 0),
                "outstanding_cents": r.get("outstanding_cents", 0),
            },
        )
        seen.add(r["term_id"])
    for row in list(CentralBillingSummary.objects.filter(school=school)):
        if str(row.term_source_id) not in {str(s) for s in seen}:
            row.delete()


def ingest_bundle(school: School, raw_bytes: bytes) -> SnapshotBatch:
    """Parses, validates and applies a sync bundle for ``school``. Always
    creates a SnapshotBatch -- ``applied=True`` on success, or raises
    IngestError (with ``batch.rejected_reason`` already recorded) on
    failure. Never partially applies a bundle: the upsert runs inside one
    transaction."""
    manifest, raw_tables = _extract(raw_bytes)

    if manifest.get("school_id") != str(school.pk):
        raise IngestError("this bundle's school_id does not match the school it was sent to")

    _verify_content_hash(manifest, raw_tables)

    settings_row = CentralSettings.load()
    bundle_version = manifest.get("snapshot_schema_version", 0)
    if bundle_version > settings_row.snapshot_schema_version_supported:
        raise IngestError(
            f"this install only understands snapshot schema version "
            f"{settings_row.snapshot_schema_version_supported}; the bundle is version "
            f"{bundle_version}. Upgrade Campus Central first."
        )

    batch = SnapshotBatch.objects.create(
        school=school, kind=manifest.get("kind", SnapshotBatch.Kind.FULL),
        manifest=manifest, content_hash=manifest.get("content_hash", ""),
    )

    try:
        with transaction.atomic():
            is_full = manifest.get("kind") == SnapshotBatch.Kind.FULL
            for table_name, (upsert, model) in _SOURCE_KEYED_UPSERTERS.items():
                rows = _rows(raw_tables, table_name)
                seen = upsert(school, rows)
                if is_full:
                    model.objects.filter(school=school).exclude(source_id__in=seen).delete()

            _replace_registration_counts(school, _rows(raw_tables, "registration_counts"))
            _replace_attendance_summary(school, _rows(raw_tables, "attendance_summary"))
            _replace_incident_summary(school, _rows(raw_tables, "incident_summary"))
            _replace_billing_summary(school, _rows(raw_tables, "billing_summary"))
    except Exception as e:  # noqa: BLE001 - always recorded on the batch, then re-raised
        batch.rejected_reason = str(e)
        batch.save(update_fields=["rejected_reason"])
        school.sync_status = School.SyncStatus.ERROR
        school.save(update_fields=["sync_status", "updated_at"])
        raise IngestError(f"upsert failed: {e}") from e

    batch.applied = True
    batch.save(update_fields=["applied"])
    school.sync_status = School.SyncStatus.OK
    school.last_synced_at = timezone.now()
    school.snapshot_schema_version = bundle_version
    school.save(
        update_fields=["sync_status", "last_synced_at", "snapshot_schema_version", "updated_at"]
    )
    return batch
