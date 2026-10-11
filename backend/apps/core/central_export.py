"""The curated Campus Central sync bundle (C2). See docs/CENTRAL_SYNC_SCOPE.md
for the exact field list this must not exceed -- every table function here is
an ALLOWLIST projection built directly from the source models, never a
trimmed copy of a wider serializer (e.g. apps.reporting.services's
data_subject_export), so a field added there can never leak into this bundle
by accident. Health, custody notes, government IDs, message bodies, incident
narratives, individual marks and per-family invoices never appear below --
some because the source model is never even imported here.

Row-level tables (``students``, ``guardians``, ``groups``, ``enrolments``,
``consents``, ``report_cards``) respect ``since`` (an incremental export).
The rest -- ``staff`` (no ``updated_at`` on ``User``) and the four genuinely
aggregate tables (``registration_counts``, ``attendance_summary``,
``incident_summary``, ``billing_summary``) -- are small, cheap to recompute,
and always exported in full regardless of ``since``: there is no meaningful
"only the changed counts" for a pre-aggregated summary table this size.

``build_bundle_bytes()`` turns the table dict into the actual wire format
(a gzipped tar of ``<table>.jsonl`` files + ``manifest.json``) -- shared by
`manage central_export` (writes it to a file) and the C5 sync agent
(apps/core/central_sync.py, POSTs it straight to Central) so the two never
drift into building the bundle two different ways.
"""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import datetime

from django.db.models import Count
from django.utils import timezone

SNAPSHOT_SCHEMA_VERSION = 1

# Table build order also fixes the order tables are written to the bundle.
TABLE_NAMES = (
    "students", "guardians", "staff", "groups", "enrolments", "consents",
    "report_cards", "registration_counts", "attendance_summary",
    "incident_summary", "billing_summary",
)


def _dt(value) -> str | None:
    return value.isoformat() if value else None


def _students(since: datetime | None) -> list[dict]:
    from apps.people.models import Student

    qs = Student.objects.alive()
    if since:
        qs = qs.filter(updated_at__gte=since)
    return [
        {
            "id": str(s.pk),
            "first_name": s.first_name,
            "last_name": s.last_name,
            "date_of_birth": _dt(s.date_of_birth),
            "student_number": s.student_number,
            "status": s.status,
            "primary_group_id": str(s.primary_group_id) if s.primary_group_id else None,
            "guardian_count": s.guardian_links.count(),
            "updated_at": _dt(s.updated_at),
        }
        for s in qs.select_related("primary_group")
    ]


def _guardians(since: datetime | None) -> list[dict]:
    from apps.people.models import Guardian

    qs = Guardian.objects.all()
    if since:
        qs = qs.filter(updated_at__gte=since)
    rows = []
    for g in qs:
        rows.append({
            "id": str(g.pk),
            "first_name": g.first_name,
            "last_name": g.last_name,
            "email": g.email,
            "phone": g.phone,
            "children": [
                {"student_id": str(link.student_id), "relationship": link.relationship}
                for link in g.links.all()
            ],
            "updated_at": _dt(g.updated_at),
        })
    return rows


def _staff(since: datetime | None) -> list[dict]:
    from apps.accounts.models import STAFF_ROLES, User

    return [
        {"id": str(u.pk), "username": u.username, "role": u.role, "active": u.is_active}
        for u in User.objects.filter(role__in=STAFF_ROLES)
    ]


def _groups(since: datetime | None) -> list[dict]:
    from apps.people.models import Group

    qs = Group.objects.all()
    if since:
        qs = qs.filter(updated_at__gte=since)
    return [
        {
            "id": str(g.pk),
            "name": g.name,
            "kind": g.kind,
            "stage_label": g.stage_label,
            "capacity": g.capacity,
            "active": g.active,
            "live_count": g.enrolments.filter(status="ACTIVE").count(),
            "updated_at": _dt(g.updated_at),
        }
        for g in qs
    ]


def _enrolments(since: datetime | None) -> list[dict]:
    from apps.registration.models import Enrolment

    qs = Enrolment.objects.all()
    if since:
        qs = qs.filter(updated_at__gte=since)
    return [
        {
            "id": str(e.pk),
            "student_id": str(e.student_id),
            "group_id": str(e.group_id),
            "start_date": _dt(e.start_date),
            "end_date": _dt(e.end_date),
            "status": e.status,
            "updated_at": _dt(e.updated_at),
        }
        for e in qs
    ]


def _consents(since: datetime | None) -> list[dict]:
    from apps.registration.models import Consent

    qs = Consent.objects.all()
    if since:
        qs = qs.filter(updated_at__gte=since)
    return [
        {
            "id": str(c.pk),
            "student_id": str(c.student_id),
            "kind": c.kind,
            "version": c.version,
            "granted": c.granted,
            "recorded_at": _dt(c.recorded_at),
            "updated_at": _dt(c.updated_at),
        }
        for c in qs
    ]


def _report_cards(since: datetime | None) -> list[dict]:
    from apps.grades.models import ReportCard

    qs = ReportCard.objects.alive()
    if since:
        qs = qs.filter(updated_at__gte=since)
    return [
        {
            "id": str(r.pk),
            "student_id": str(r.student_id),
            "term_id": str(r.term_id),
            "status": r.status,
            "updated_at": _dt(r.updated_at),
        }
        for r in qs
    ]


def _registration_counts(since: datetime | None) -> list[dict]:
    from apps.registration.models import Application, WaitlistEntry

    by_status = Application.objects.alive().values("status").annotate(count=Count("id"))
    by_group = (
        WaitlistEntry.objects.filter(active=True).values("group_id").annotate(count=Count("id"))
    )
    return [{
        "applications_by_status": {r["status"]: r["count"] for r in by_status},
        "waitlist_by_group": {str(r["group_id"]): r["count"] for r in by_group},
    }]


def _attendance_summary(since: datetime | None) -> list[dict]:
    from apps.attendance.models import AttendanceRecord
    from apps.scheduling.models import Term

    present_statuses = {"PRESENT", "LATE"}
    late_statuses = {"LATE"}
    absent_statuses = {"ABSENT", "EXCUSED"}

    rows = []
    for term in Term.objects.all():
        per_student: dict[str, dict[str, int]] = {}
        records = AttendanceRecord.objects.filter(
            date__gte=term.start_date, date__lte=term.end_date,
        ).values("student_id", "status")
        for rec in records:
            counts = per_student.setdefault(
                str(rec["student_id"]), {"present": 0, "absent": 0, "late": 0}
            )
            if rec["status"] in late_statuses:
                counts["late"] += 1
            elif rec["status"] in present_statuses:
                counts["present"] += 1
            elif rec["status"] in absent_statuses:
                counts["absent"] += 1
        for student_id, counts in per_student.items():
            total = counts["present"] + counts["absent"] + counts["late"]
            rows.append({
                "term_id": str(term.pk),
                "student_id": student_id,
                "present": counts["present"],
                "absent": counts["absent"],
                "late": counts["late"],
                "present_pct": round(100 * counts["present"] / total, 1) if total else None,
            })
    return rows


def _incident_summary(since: datetime | None) -> list[dict]:
    from apps.communication.models import IncidentReport
    from apps.scheduling.models import Term

    rows = []
    for term in Term.objects.all():
        counts = (
            IncidentReport.objects.alive()
            .filter(occurred_at__date__gte=term.start_date, occurred_at__date__lte=term.end_date)
            .values("category", "severity", "status")
            .annotate(count=Count("id"))
        )
        for row in counts:
            rows.append({
                "term_id": str(term.pk),
                "category": row["category"],
                "severity": row["severity"],
                "status": row["status"],
                "count": row["count"],
            })
    return rows


def _billing_summary(since: datetime | None) -> list[dict]:
    from apps.billing.models import Invoice
    from apps.core.models import SiteConfiguration
    from apps.scheduling.models import Term

    if not SiteConfiguration.load().collects_fees:
        return []

    rows = []
    for term in Term.objects.all():
        qs = Invoice.objects.filter(term=term).exclude(status=Invoice.Status.VOID)
        issued = paid = outstanding = 0
        for inv in qs:
            issued += inv.total_cents
            paid += inv.paid_cents
            outstanding += inv.balance_cents
        if issued or paid:
            rows.append({
                "term_id": str(term.pk),
                "issued_cents": issued,
                "paid_cents": paid,
                "outstanding_cents": outstanding,
            })
    return rows


_BUILDERS = {
    "students": _students,
    "guardians": _guardians,
    "staff": _staff,
    "groups": _groups,
    "enrolments": _enrolments,
    "consents": _consents,
    "report_cards": _report_cards,
    "registration_counts": _registration_counts,
    "attendance_summary": _attendance_summary,
    "incident_summary": _incident_summary,
    "billing_summary": _billing_summary,
}


def build_central_export(since: datetime | None = None) -> dict[str, list[dict]]:
    """Every table in the curated snapshot, as plain dicts ready for
    ``json.dumps``. Pure read -- writes nothing, touches no network."""
    return {name: builder(since) for name, builder in _BUILDERS.items()}


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes, mtime: int) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = mtime
    tar.addfile(info, io.BytesIO(data))


def build_bundle_bytes(
    school_id, since: datetime | None = None,
) -> tuple[bytes, dict]:
    """The actual wire format: a gzipped tar of ``<table>.jsonl`` files plus
    ``manifest.json``, built from :func:`build_central_export`. Returns
    ``(bundle_bytes, manifest)`` -- the caller (the ``central_export``
    command, or the C5 sync agent) decides what to do with the bytes; this
    function touches no file and no network itself."""
    tables = build_central_export(since)
    table_payloads = {}
    for name, rows in tables.items():
        text = "\n".join(json.dumps(row, default=str) for row in rows)
        if rows:
            text += "\n"
        table_payloads[name] = text.encode("utf-8")

    hasher = hashlib.sha256()
    for name in sorted(table_payloads):
        hasher.update(name.encode("utf-8"))
        hasher.update(table_payloads[name])

    manifest = {
        "school_id": str(school_id),
        "generated_at": timezone.now().isoformat(),
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": "INCREMENTAL" if since else "FULL",
        "since": since.isoformat() if since else None,
        "tables": {name: len(rows) for name, rows in tables.items()},
        "content_hash": hasher.hexdigest(),
    }

    mtime = int(timezone.now().timestamp())
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in table_payloads.items():
            _add_bytes(tar, f"{name}.jsonl", payload, mtime)
        _add_bytes(tar, "manifest.json", json.dumps(manifest, indent=2).encode("utf-8"), mtime)

    return buf.getvalue(), manifest
