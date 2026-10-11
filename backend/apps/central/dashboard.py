"""Aggregate dashboard figures (C6): enrolment totals, attendance %,
consent-compliance %, incident counts. Deliberately never touches a name,
email, phone or DOB anywhere in this module -- every value here is a count
or a percentage, which is what makes this safe for ``MINISTRY_ANALYST`` too
(unlike apps/central/search.py).
"""
from __future__ import annotations

from django.db.models import QuerySet, Sum

from apps.central.models import (
    CentralAttendanceSummary,
    CentralConsent,
    CentralEnrolment,
    CentralIncidentSummary,
)


def build_dashboard(schools: QuerySet) -> dict:
    school_ids = list(schools.values_list("id", flat=True))

    enrolment_total = CentralEnrolment.objects.filter(
        school_id__in=school_ids, status="ACTIVE"
    ).count()

    attendance = CentralAttendanceSummary.objects.filter(school_id__in=school_ids)
    totals = attendance.aggregate(present=Sum("present"), absent=Sum("absent"), late=Sum("late"))
    present, absent, late = (totals["present"] or 0), (totals["absent"] or 0), (totals["late"] or 0)
    total_days = present + absent + late
    attendance_pct = round(100 * present / total_days, 1) if total_days else None

    consents = CentralConsent.objects.filter(school_id__in=school_ids)
    consent_total = consents.count()
    consent_granted = consents.filter(granted=True).count()
    consent_compliance_pct = (
        round(100 * consent_granted / consent_total, 1) if consent_total else None
    )

    incidents_by_category = dict(
        CentralIncidentSummary.objects.filter(school_id__in=school_ids)
        .values("category")
        .annotate(total=Sum("count"))
        .values_list("category", "total")
    )

    # A raw ILLNESS count isn't a fair comparison across districts/schools of
    # different sizes -- a district with more enrolled students will trivially
    # show a higher raw count without actually having more illness per
    # student. Normalized per 100 enrolled students instead, so "this
    # district has more illness than that one" is an actual, comparable
    # claim -- requested explicitly for health-concern monitoring (e.g. a
    # Ministry health officer spotting an outbreak pattern across islands).
    illness_count = incidents_by_category.get("ILLNESS", 0)
    illness_rate_per_100_students = (
        round(100 * illness_count / enrolment_total, 1) if enrolment_total else None
    )

    return {
        "school_count": len(school_ids),
        "enrolment_total": enrolment_total,
        "attendance_pct": attendance_pct,
        "consent_compliance_pct": consent_compliance_pct,
        "incidents_by_category": incidents_by_category,
        "illness_count": illness_count,
        "illness_rate_per_100_students": illness_rate_per_100_students,
    }


def build_dashboard_by_district(schools: QuerySet) -> list[dict]:
    """One row per district among the given (already role-scoped) schools."""
    rows = []
    districts = schools.order_by("district").values_list("district", flat=True).distinct()
    for district in districts:
        row = build_dashboard(schools.filter(district=district))
        row["district"] = district or "(none)"
        rows.append(row)
    return rows
