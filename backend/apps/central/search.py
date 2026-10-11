"""Cross-school search (C6) over the three individual-record ``Central*``
tables. Never called for ``MINISTRY_ANALYST`` -- the view's own permission
class (``IndividualRecordAccess``) refuses that role before this runs at
all, per docs/CENTRAL_SYNC_SCOPE.md's C0 decision 7.
"""
from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.central.models import CentralGuardian, CentralStaff, CentralStudent, School

MAX_RESULTS_PER_KIND = 50


def _name_query(field_prefix: str, q: str) -> Q:
    """Matches "Jane", "Smith" OR "Jane Smith"/"Smith Jane" -- a query split
    on whitespace into tokens, each of which must hit EITHER the first or
    last name field (AND across tokens, OR within a token). A single
    ``icontains`` against the whole query string (the original
    implementation) can never match a two-word "first last" search, since
    neither field ever contains both words together -- found 2026-10-09
    testing a real cross-school lookup for a named student, the exact
    "name a person, find their record" use case this search exists for."""
    tokens = q.split()
    if not tokens:
        return Q(pk__in=[])
    first, last = f"{field_prefix}first_name", f"{field_prefix}last_name"
    combined = Q()
    for token in tokens:
        combined &= Q(**{f"{first}__icontains": token}) | Q(**{f"{last}__icontains": token})
    return combined


def search(schools: QuerySet, query: str) -> dict:
    q = query.strip()
    if not q:
        return {"students": [], "guardians": [], "staff": []}
    school_ids = list(schools.values_list("id", flat=True))

    students = CentralStudent.objects.filter(school_id__in=school_ids).filter(
        _name_query("", q) | Q(student_number__icontains=q)
    )[:MAX_RESULTS_PER_KIND]
    guardians = CentralGuardian.objects.filter(school_id__in=school_ids).filter(
        _name_query("", q) | Q(email__icontains=q)
    )[:MAX_RESULTS_PER_KIND]
    staff = CentralStaff.objects.filter(
        school_id__in=school_ids, username__icontains=q
    )[:MAX_RESULTS_PER_KIND]

    # Resolve school_id -> name/district once, not per-row: a result with no
    # indication of WHICH school it belongs to is not actionable (confirmed
    # feedback, 2026-10-09 -- the whole point of this search is a Ministry
    # user being able to say which school to go to from a bare name).
    school_names = dict(School.objects.filter(pk__in=school_ids).values_list("id", "name"))

    return {
        "students": [
            {
                "id": str(s.pk), "school_id": str(s.school_id),
                "school_name": school_names.get(s.school_id, ""),
                "name": f"{s.first_name} {s.last_name}".strip(),
                "student_number": s.student_number, "status": s.status,
            }
            for s in students
        ],
        "guardians": [
            {
                "id": str(g.pk), "school_id": str(g.school_id),
                "school_name": school_names.get(g.school_id, ""),
                "name": f"{g.first_name} {g.last_name}".strip(), "email": g.email,
            }
            for g in guardians
        ],
        "staff": [
            {
                "id": str(s.pk), "school_id": str(s.school_id),
                "school_name": school_names.get(s.school_id, ""),
                "username": s.username, "role": s.role,
            }
            for s in staff
        ],
    }
