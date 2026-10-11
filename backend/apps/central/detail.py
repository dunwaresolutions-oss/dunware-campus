"""Per-student / per-guardian detail ("case file") views (C8). Reuses ONLY
data already synced into Central's own database -- nothing here reaches out
to a school live. Gated by the same ``IndividualRecordAccess`` permission as
search (never ``MINISTRY_ANALYST``), and every call is audited by its view,
same as every other individual-record read in this app.

Deliberately on-demand, not broadcast: this assembles a rich view ONLY when
a specific id is requested by an authorized user, not as part of the regular
aggregate sync/dashboard surface -- matches the explicit design principle
that Central should not constantly hold/show full student detail by default,
but must be able to produce it immediately when genuinely needed (e.g.
assisting a police inquiry without the Ministry needing to call the school).
"""
from __future__ import annotations

from apps.central.models import (
    CentralAttendanceSummary,
    CentralConsent,
    CentralEnrolment,
    CentralGroup,
    CentralGuardian,
    CentralReportCard,
    CentralStudent,
    School,
)


def _guardians_for_student(school_id, source_id) -> list[dict]:
    """``CentralGuardian.children`` is a small JSON list per guardian row
    (never the other way around -- there is no per-student guardian table),
    so resolving "who are this student's guardians" means scanning the
    school's own guardians in Python rather than a DB-side JSON-containment
    query -- simpler and backend-portable (SQLite in dev/tests, Postgres in
    prod), and a school's guardian count is small enough that this is cheap.
    """
    sid = str(source_id)
    out = []
    for g in CentralGuardian.objects.filter(school_id=school_id):
        for child in g.children or []:
            if child.get("student_id") == sid:
                out.append({
                    "id": str(g.pk), "name": f"{g.first_name} {g.last_name}".strip(),
                    "email": g.email, "phone": g.phone,
                    "relationship": child.get("relationship", ""),
                })
                break
    return out


def build_student_detail(schools, student_id) -> dict | None:
    visible_ids = schools.values_list("id", flat=True)
    student = CentralStudent.objects.filter(school_id__in=visible_ids, pk=student_id).first()
    if student is None:
        return None
    school = School.objects.filter(pk=student.school_id).first()

    group = None
    if student.primary_group_source_id:
        group = CentralGroup.objects.filter(
            school_id=student.school_id, source_id=student.primary_group_source_id
        ).first()

    enrolments = [
        {
            "group_name": (
                CentralGroup.objects.filter(
                    school_id=student.school_id, source_id=e.group_source_id
                ).values_list("name", flat=True).first()
            ) or "(unknown group)",
            "start_date": e.start_date, "end_date": e.end_date, "status": e.status,
        }
        for e in CentralEnrolment.objects.filter(
            school_id=student.school_id, student_source_id=student.source_id
        ).order_by("-start_date")
    ]

    attendance = [
        {
            "term_source_id": str(a.term_source_id), "present": a.present,
            "absent": a.absent, "late": a.late, "present_pct": a.present_pct,
        }
        for a in CentralAttendanceSummary.objects.filter(
            school_id=student.school_id, student_source_id=student.source_id
        )
    ]

    consents = [
        {
            "kind": c.kind, "version": c.version, "granted": c.granted,
            "recorded_at": c.recorded_at,
        }
        for c in CentralConsent.objects.filter(
            school_id=student.school_id, student_source_id=student.source_id
        ).order_by("kind")
    ]

    report_cards = [
        {"term_source_id": str(r.term_source_id), "status": r.status}
        for r in CentralReportCard.objects.filter(
            school_id=student.school_id, student_source_id=student.source_id
        )
    ]

    return {
        "id": str(student.pk),
        "school_id": str(student.school_id),
        "school_name": school.name if school else "",
        "school_district": school.district if school else "",
        "first_name": student.first_name, "last_name": student.last_name,
        "date_of_birth": student.date_of_birth,
        "student_number": student.student_number, "status": student.status,
        "primary_group_name": group.name if group else None,
        "enrolments": enrolments,
        "attendance": attendance,
        "guardians": _guardians_for_student(student.school_id, student.source_id),
        "consents": consents,
        "report_cards": report_cards,
    }


def build_guardian_detail(schools, guardian_id) -> dict | None:
    guardian = CentralGuardian.objects.filter(
        school_id__in=schools.values_list("id", flat=True)
    ).filter(pk=guardian_id).first()
    if guardian is None:
        return None
    school = School.objects.filter(pk=guardian.school_id).first()

    children = []
    for child in guardian.children or []:
        sid = child.get("student_id")
        if not sid:
            continue
        s = CentralStudent.objects.filter(school_id=guardian.school_id, source_id=sid).first()
        children.append({
            "student_id": str(s.pk) if s else None,
            "name": f"{s.first_name} {s.last_name}".strip() if s else "(not synced)",
            "student_number": s.student_number if s else "",
            "status": s.status if s else "",
            "relationship": child.get("relationship", ""),
        })

    return {
        "id": str(guardian.pk),
        "school_id": str(guardian.school_id),
        "school_name": school.name if school else "",
        "school_district": school.district if school else "",
        "first_name": guardian.first_name, "last_name": guardian.last_name,
        "email": guardian.email, "phone": guardian.phone,
        "children": children,
    }
