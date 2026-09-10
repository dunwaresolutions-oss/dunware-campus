"""
Role-scoped operational metrics for the console dashboard.

``build_metrics(user)`` returns a single JSON-able dict. The blocks it fills
depend on the caller's role:

* **instructor** (teacher / tutor) — scope, attendance, enrolment (basic),
  academics and wellbeing, all computed over *only* the groups the user
  staffs and the students in them (`Student.visible_queryset` already scopes
  this; group ids come from `GroupStaff`).
* **office** (front desk) — the above, school-wide, plus ``operations``
  (billing, consent compliance, booking, messages).
* **system** (admin / superadmin) — the above plus ``security`` and
  ``staffing``. Superadmin additionally gets ``platform`` (legal holds,
  retention, audit volume).

Every query here is an aggregate — it never triggers the audit-read path, so
loading the dashboard does not spam the audit log.
"""
from __future__ import annotations

import datetime as _dt

from django.conf import settings
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q, Sum
from django.utils import timezone

from apps.accounts.models import STAFF_ROLES, Role, User
from apps.billing.models import Invoice, InvoiceLine, Payment
from apps.booking.models import Booking, Slot
from apps.communication.models import IncidentReport, MessageThread
from apps.grades.models import Assessment, AssessmentResult, ReportCard
from apps.people.models import Group, GroupStaff, Observation, Student
from apps.registration.models import Application, Consent, Enrolment, Offer, WaitlistEntry
from apps.scheduling.models import AcademicYear, Term

_ATT_MARKED = ("PRESENT", "ABSENT", "LATE", "EXCUSED", "LEFT_EARLY")
_ATT_PRESENT = ("PRESENT", "LATE", "LEFT_EARLY")
_CONSENT_KINDS = [k.value for k in Consent.Kind]
_OFFICE_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}
_SYSTEM_ROLES = {Role.SUPERADMIN, Role.ADMIN}
_INSTRUCTOR_ROLES = {Role.TEACHER, Role.TUTOR}
_WINDOW_DAYS = 30


def _pct(part, whole) -> float | None:
    return round(100.0 * part / whole, 1) if whole else None


def _current_term(today):
    t = (
        Term.objects.filter(start_date__lte=today, end_date__gte=today)
        .order_by("-start_date")
        .first()
    )
    if t:
        return t
    yr = AcademicYear.objects.filter(is_current=True).first()
    return yr.terms.order_by("-start_date").first() if yr else None


def _scope(user):
    role = getattr(user, "role", None)
    if role in _SYSTEM_ROLES:
        level = "system"
    elif role == Role.FRONT_DESK:
        level = "office"
    else:
        level = "instructor"

    students = Student.visible_queryset(user)  # already role-scoped
    if level == "instructor":
        group_ids = list(
            GroupStaff.objects.filter(user=user, active=True).values_list(
                "group_id", flat=True
            )
        )
    else:
        group_ids = list(
            Group.objects.filter(active=True).values_list("id", flat=True)
        )
    return level, students, group_ids


# --------------------------------------------------------------------------- #

def _attendance(students, today):
    start = today - _dt.timedelta(days=_WINDOW_DAYS)
    # local import avoids a hard dependency cycle at module load
    from apps.attendance.models import AttendanceRecord

    att = AttendanceRecord.objects.filter(student__in=students, date__gte=start)
    agg = att.aggregate(
        records=Count("id"),
        marked=Count("id", filter=Q(status__in=_ATT_MARKED)),
        present=Count("id", filter=Q(status__in=_ATT_PRESENT)),
        absent=Count("id", filter=Q(status="ABSENT")),
        late=Count("id", filter=Q(status="LATE")),
        excused=Count("id", filter=Q(status="EXCUSED")),
    )
    per_student = (
        att.filter(status__in=_ATT_MARKED)
        .values("student")
        .annotate(
            marked=Count("id"),
            absent=Count("id", filter=Q(status="ABSENT")),
        )
    )
    chronic = sum(
        1
        for r in per_student
        if r["marked"] >= 5 and r["absent"] / r["marked"] > 0.10
    )
    return {
        "window_days": _WINDOW_DAYS,
        "records": agg["records"],
        "rate_pct": _pct(agg["present"], agg["marked"]),
        "present": agg["present"],
        "absent": agg["absent"],
        "late": agg["late"],
        "excused": agg["excused"],
        "chronic_absentees": chronic,
        "unmarked_today": att.filter(date=today, status="EXPECTED").count(),
    }


def _enrolment(level, students, group_ids, term):
    by_status = {
        r["status"]: r["n"]
        for r in students.values("status").annotate(n=Count("id"))
    }
    active = by_status.get(Student.Status.ENROLLED, 0)
    out = {
        "active": active,
        "prospective": by_status.get(Student.Status.PROSPECTIVE, 0),
        "graduated": by_status.get(Student.Status.GRADUATED, 0),
        "withdrawn_term": (
            students.filter(
                status=Student.Status.WITHDRAWN,
                left_on__gte=term.start_date,
            ).count()
            if term
            else students.filter(status=Student.Status.WITHDRAWN).count()
        ),
        "by_status": by_status,
    }
    if level == "instructor":
        return out

    # office / system: capacity, waitlist, application funnel, ratio
    caps = Group.objects.filter(id__in=group_ids, capacity__isnull=False).aggregate(
        s=Sum("capacity")
    )["s"]
    active_enrol = Enrolment.objects.filter(
        group_id__in=group_ids, status=Enrolment.Status.ACTIVE
    ).count()
    out["capacity_pct"] = _pct(active_enrol, caps) if caps else None
    out["waitlist"] = WaitlistEntry.objects.filter(
        active=True, group_id__in=group_ids
    ).count()

    instructors = User.objects.filter(
        is_active=True, role__in=[Role.TEACHER, Role.TUTOR]
    ).count()
    out["student_staff_ratio"] = (
        round(active / instructors, 1) if instructors else None
    )

    apps_qs = Application.objects.alive()
    a_by = {
        r["status"]: r["n"]
        for r in apps_qs.values("status").annotate(n=Count("id"))
    }
    offers = Offer.objects.all()
    resp = offers.filter(
        status__in=[Offer.Status.ACCEPTED, Offer.Status.DECLINED]
    ).count()
    out["applications"] = {
        "submitted": a_by.get(Application.Status.SUBMITTED, 0),
        "under_review": a_by.get(Application.Status.UNDER_REVIEW, 0),
        "offer_made": a_by.get(Application.Status.OFFER_MADE, 0),
        "waitlisted": a_by.get(Application.Status.WAITLISTED, 0),
        "enrolled": a_by.get(Application.Status.ENROLLED, 0),
        "declined": a_by.get(Application.Status.DECLINED, 0),
        "offer_acceptance_pct": _pct(
            offers.filter(status=Offer.Status.ACCEPTED).count(), resp
        ),
    }
    return out


def _academics(students, group_ids, term):
    assess = Assessment.objects.filter(group_id__in=group_ids)
    a_total = assess.count()
    a_released = assess.filter(released=True).count()

    results = AssessmentResult.objects.filter(
        assessment__group_id__in=group_ids
    ).count()
    enrol_by_group = dict(
        Enrolment.objects.filter(
            group_id__in=group_ids, status=Enrolment.Status.ACTIVE
        )
        .values("group_id")
        .annotate(n=Count("id"))
        .values_list("group_id", "n")
    )
    expected = sum(
        enrol_by_group.get(gid, 0) for gid in assess.values_list("group_id", flat=True)
    )

    avg_pct = AssessmentResult.objects.filter(
        assessment__group_id__in=group_ids,
        mark__isnull=False,
        assessment__max_mark__gt=0,
    ).aggregate(
        v=Avg(
            ExpressionWrapper(
                F("mark") * 100.0 / F("assessment__max_mark"),
                output_field=FloatField(),
            )
        )
    )["v"]

    rc = ReportCard.objects.alive().filter(student__in=students)
    if term:
        rc = rc.filter(term=term)
    rc_agg = rc.aggregate(
        draft=Count("id", filter=Q(status=ReportCard.Status.DRAFT)),
        finalized=Count("id", filter=Q(status=ReportCard.Status.FINALIZED)),
        released=Count("id", filter=Q(status=ReportCard.Status.RELEASED)),
    )
    rc_all = sum(rc_agg.values())

    return {
        "assessments": a_total,
        "assessments_released": a_released,
        "released_pct": _pct(a_released, a_total),
        "grading_completion_pct": _pct(results, expected),
        "avg_mark_pct": round(avg_pct, 1) if avg_pct is not None else None,
        "report_cards": {
            **rc_agg,
            "released_pct": _pct(rc_agg["released"], rc_all),
        },
    }


def _wellbeing(students, active_count, today):
    since = timezone.now() - _dt.timedelta(days=_WINDOW_DAYS)
    inc = IncidentReport.objects.alive().filter(
        student__in=students, occurred_at__gte=since
    )
    total = inc.count()
    return {
        "window_days": _WINDOW_DAYS,
        "incidents": total,
        "incidents_open": (
            IncidentReport.objects.alive()
            .filter(student__in=students)
            .exclude(status=IncidentReport.Status.ACKNOWLEDGED)
            .count()
        ),
        "per_100_students": (
            round(100.0 * total / active_count, 1) if active_count else None
        ),
        "by_severity": {
            str(r["severity"]): r["n"]
            for r in inc.values("severity").annotate(n=Count("id"))
        },
        "by_category": {
            r["category"]: r["n"]
            for r in inc.values("category").annotate(n=Count("id"))
        },
        "observations": Observation.objects.alive().filter(
            student__in=students, occurred_at__gte=since
        ).count(),
    }


def _operations(students):
    issued = Invoice.objects.filter(student__in=students).exclude(
        status__in=[Invoice.Status.DRAFT, Invoice.Status.VOID]
    )
    invoiced = InvoiceLine.objects.filter(invoice__in=issued).aggregate(
        s=Sum(F("quantity") * F("unit_amount_cents"))
    )["s"] or 0
    collected = Payment.objects.filter(invoice__in=issued).aggregate(
        s=Sum("amount_cents")
    )["s"] or 0

    active_students = students.filter(status=Student.Status.ENROLLED)
    n_active = active_students.count()
    have = {
        r["kind"]: r["n"]
        for r in Consent.objects.filter(student__in=active_students)
        .values("kind")
        .annotate(n=Count("student", distinct=True))
    }
    by_kind = {k: _pct(have.get(k, 0), n_active) for k in _CONSENT_KINDS}
    fully = (
        Consent.objects.filter(student__in=active_students)
        .values("student")
        .annotate(kinds=Count("kind", distinct=True))
        .filter(kinds__gte=len(_CONSENT_KINDS))
        .count()
    )

    now = timezone.now()
    up_slots = Slot.objects.filter(
        starts_at__gte=now, status__in=[Slot.Status.OPEN, Slot.Status.FULL]
    )
    seats = up_slots.aggregate(s=Sum("capacity"))["s"] or 0
    confirmed = Booking.objects.filter(
        slot__starts_at__gte=now, status=Booking.Status.CONFIRMED
    ).count()

    return {
        "billing": {
            "issued": issued.count(),
            "invoiced_cents": invoiced,
            "collected_cents": collected,
            "outstanding_cents": max(invoiced - collected, 0),
            "overdue": issued.filter(status=Invoice.Status.OVERDUE).count(),
            "collection_pct": _pct(collected, invoiced),
        },
        "consent": {
            "active_students": n_active,
            "by_kind": by_kind,
            "fully_covered_pct": _pct(fully, n_active),
        },
        "booking": {
            "upcoming_slots": up_slots.count(),
            "seats": seats,
            "confirmed": confirmed,
            "waitlisted": Booking.objects.filter(
                slot__starts_at__gte=now, status=Booking.Status.WAITLISTED
            ).count(),
            "fill_pct": _pct(confirmed, seats),
        },
        "messages": {
            "threads_open": MessageThread.objects.filter(closed=False).count(),
            "threads_total": MessageThread.objects.count(),
        },
    }


def _backup():
    from .models import BackupRun

    now = timezone.now()
    runs = BackupRun.objects.all()
    last_ok = (
        runs.filter(status=BackupRun.Status.SUCCESS)
        .exclude(kind=BackupRun.Kind.VERIFY)
        .order_by("-started_at")
        .first()
    )
    last_any = runs.order_by("-started_at").first()
    last_verify = (
        runs.filter(kind=BackupRun.Kind.VERIFY, status=BackupRun.Status.SUCCESS)
        .order_by("-started_at")
        .first()
    )
    age_hours = (
        round((now - last_ok.started_at).total_seconds() / 3600, 1)
        if last_ok
        else None
    )
    return {
        "configured": runs.exists(),
        "last_success_at": last_ok.started_at if last_ok else None,
        "last_success_age_hours": age_hours,
        "last_success_bytes": last_ok.size_bytes if last_ok else None,
        "last_status": last_any.status if last_any else None,
        "last_error": (last_any.error or "")[:200] if last_any else "",
        "runs_7d": runs.filter(started_at__gte=now - _dt.timedelta(days=7)).count(),
        "failures_7d": runs.filter(
            status=BackupRun.Status.FAILED,
            started_at__gte=now - _dt.timedelta(days=7),
        ).count(),
        "archives_retained": last_ok.archives_retained if last_ok else None,
        "last_verified_at": last_verify.started_at if last_verify else None,
        # amber if a backup has never succeeded, or the newest is over 48h old,
        # or the newest run of any kind failed.
        "stale": (
            last_ok is None
            or (age_hours is not None and age_hours > 48)
            or (last_any is not None and last_any.status == BackupRun.Status.FAILED)
        ),
    }


def _system(is_superadmin):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from apps.audit.models import AuditEntry

    since = timezone.now() - _dt.timedelta(hours=24)
    sec = AuditEntry.objects.filter(at__gte=since)
    security = {
        "failed_signins": sec.filter(action="LOGIN_FAILED").count(),
        "lockouts": sec.filter(action="LOCKOUT").count(),
        "access_denied": sec.filter(action="PERMISSION_DENIED").count(),
        "exports_erasures": sec.filter(action__in=["EXPORT", "ERASE"]).count(),
        "total": sec.count(),
    }

    staff = User.objects.filter(is_active=True, role__in=STAFF_ROLES)
    staff_total = staff.count()
    mfa_enrolled = (
        TOTPDevice.objects.filter(confirmed=True, user__in=staff)
        .values("user")
        .distinct()
        .count()
    )
    groups_no_lead = (
        Group.objects.filter(active=True)
        .exclude(staff__active=True, staff__role=GroupStaff.Role.LEAD)
        .count()
    )

    out = {
        "security_24h": security,
        "staffing": {
            "by_role": {
                r["role"]: r["n"]
                for r in staff.values("role").annotate(n=Count("id"))
            },
            "total_active": staff_total,
            "groups_without_lead": groups_no_lead,
            "mfa_coverage_pct": _pct(mfa_enrolled, staff_total),
        },
        "backup": _backup(),
    }
    if is_superadmin:
        cutoff = timezone.localdate() - _dt.timedelta(
            days=getattr(settings, "RETENTION_PAST_STUDENT_DAYS", 2555)
        )
        out["platform"] = {
            "legal_holds": Student.objects.filter(legal_hold=True).count(),
            "anonymized_records": Student.objects.filter(
                anonymized_at__isnull=False
            ).count(),
            "retention_eligible": Student.objects.filter(
                status__in=[Student.Status.WITHDRAWN, Student.Status.GRADUATED],
                left_on__isnull=False,
                left_on__lt=cutoff,
                anonymized_at__isnull=True,
                legal_hold=False,
            ).count(),
            "audit_24h_total": security["total"],
        }
    return out


# --------------------------------------------------------------------------- #

def build_metrics(user) -> dict:
    today = timezone.localdate()
    term = _current_term(today)
    level, students, group_ids = _scope(user)
    active_count = students.filter(status=Student.Status.ENROLLED).count()

    payload = {
        "generated_at": timezone.now(),
        "scope": {
            "level": level,
            "role": getattr(user, "role", None),
            "group_count": len(group_ids),
            "student_count": students.count(),
            "active_students": active_count,
            "term": str(term) if term else None,
        },
        "attendance": _attendance(students, today),
        "enrolment": _enrolment(level, students, group_ids, term),
        "academics": _academics(students, group_ids, term),
        "wellbeing": _wellbeing(students, active_count, today),
    }
    if level in ("office", "system"):
        payload["operations"] = _operations(students)
    if level == "system":
        payload["system"] = _system(getattr(user, "role", None) == Role.SUPERADMIN)
    return payload
