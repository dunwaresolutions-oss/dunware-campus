"""Campus Central's own permission classes (C6). Built on the same generic
building blocks Campus's own viewsets use (``apps.core.permissions`` --
``MFAVerified``: no Campus-specific coupling, confirmed before reusing it),
with Central's own role set.

Per docs/CENTRAL_SYNC_SCOPE.md's C0 decision 7: ``MINISTRY_ANALYST`` is
aggregate/summary-only, "enforced the same way Campus enforces every other
role: an explicit permission class per endpoint, not a UI-only hide." That
is why individual-record endpoints (search, a school's detail -- once it
carries anything beyond institutional metadata) use
``IndividualRecordAccess``, which does not list ``MINISTRY_ANALYST`` at all,
rather than one shared permission class that tries to filter fields out of
the same response for that role.

**Every class here also accepts ``is_superuser``.** The bootstrap flow
reused as-is from Campus (``apps.accounts``'s ``SetupAdminView`` /
``bootstrap_superadmin()``) hardcodes the created account's role to
``SUPERADMIN`` -- not one of Central's three roles -- so without this, the
very first account on a fresh Central install would pass MFA, sign in
successfully, and then be refused by every single endpoint below: a
first-login dead end. Treating ``is_superuser`` as a break-glass superset
matches how Campus's own permission classes already treat ``SUPERADMIN`` (a
strict superset of ``ADMIN``/``FRONT_DESK`` in ``ADMIN_ROLE_NAMES``), not a
new pattern invented for Central.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.core.permissions import MFAVerified

CENTRAL_ROLE_NAMES = ("MINISTRY_ADMIN", "MINISTRY_ANALYST", "DISTRICT_OFFICER")


class _CentralRolePermission(BasePermission):
    allowed_roles: tuple[str, ...] = ()

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(user, "role", None) in self.allowed_roles


class CentralRoleRequired(_CentralRolePermission):
    """Any of the three Central roles -- the baseline for every Central
    endpoint. School registry metadata (name, district, sync status) isn't
    person PII, so all three roles pass this; narrower endpoints add a
    stricter class on top."""

    allowed_roles = CENTRAL_ROLE_NAMES


class MinistryAdminOnly(_CentralRolePermission):
    """Token issuance / rotation and registering a new school -- an
    administrative action, not a reporting one."""

    allowed_roles = ("MINISTRY_ADMIN",)


class IndividualRecordAccess(_CentralRolePermission):
    """Search and any other endpoint that can return an individual
    student/guardian/staff row. Deliberately excludes MINISTRY_ANALYST."""

    allowed_roles = ("MINISTRY_ADMIN", "DISTRICT_OFFICER")


class CentralStaffAndMFA(CentralRoleRequired):
    """The default for a Central endpoint: one of the three roles (or
    break-glass superuser) *and* a satisfied second factor (``User.save()``
    already requires MFA for these roles and for any superuser -- see
    apps/accounts/models.py -- this just also checks the current session
    actually completed it, same as Campus's own ``StaffAndMFAVerified``)."""

    def has_permission(self, request, view):
        return super().has_permission(request, view) and MFAVerified().has_permission(
            request, view
        )
