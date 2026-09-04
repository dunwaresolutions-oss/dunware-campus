from __future__ import annotations

from apps.core.permissions import MFAVerified, StaffOnly

from .models import HealthAccessGrant


class HealthDataPermission(StaffOnly):
    """Staff role + MFA + an explicit, active health-access grant (or admin
    tier). The named-subset requirement from docs/PII_SECURITY.md §2."""

    message = "Viewing health records requires an active health-data access grant."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if not MFAVerified().has_permission(request, view):
            return False
        return HealthAccessGrant.user_may_view_health(request.user)
