"""Which schools a Central user may see (C6). The one place this is decided
-- every view scopes through this, never re-derives it, so a
DISTRICT_OFFICER's reach can't drift between endpoints."""
from __future__ import annotations

from django.db.models import QuerySet

from apps.central.models import DistrictAssignment, School


def schools_visible_to(user) -> QuerySet[School]:
    role = getattr(user, "role", None)
    # A break-glass superuser (the bootstrap account's role is SUPERADMIN,
    # not a Central role -- see permissions.py's own docstring) sees
    # everything, same breadth as MINISTRY_ADMIN.
    if getattr(user, "is_superuser", False) or role in ("MINISTRY_ADMIN", "MINISTRY_ANALYST"):
        return School.objects.filter(active=True)
    if role == "DISTRICT_OFFICER":
        districts = DistrictAssignment.objects.filter(user=user).values_list(
            "district", flat=True
        )
        return School.objects.filter(active=True, district__in=list(districts))
    return School.objects.none()
