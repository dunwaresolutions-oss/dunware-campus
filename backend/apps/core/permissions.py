"""
Base permission building blocks (see docs/PII_SECURITY.md).

DRF default is IsAuthenticated (settings). Every viewset then narrows with one
of these. Phase 1 fills in the concrete role/object matrix; this file sets the
shape so no viewset ships without an explicit decision.
"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

STAFF_ROLE_NAMES = ("SUPERADMIN", "ADMIN", "FRONT_DESK", "TEACHER", "TUTOR")


class MFAVerified(BasePermission):
    """
    Blocks a request whose user is required to use MFA but whose session is not
    OTP-verified. Parents/students (``must_use_mfa`` False) pass straight
    through; staff must have confirmed a TOTP device and cleared the second
    factor this session.
    """

    message = "Multi-factor authentication is required. Finish MFA setup / verification."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        if not getattr(user, "must_use_mfa", False):
            return True
        is_verified = getattr(user, "is_verified", None)
        return bool(callable(is_verified) and is_verified())


class RoleRequired(BasePermission):
    """
    Subclass and set ``allowed_roles``. Deny-by-default: an unlisted role
    (including a viewset that forgot to subclass) gets nothing.
    """

    allowed_roles: tuple[str, ...] = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and getattr(user, "role", None) in self.allowed_roles
        )


class StaffOnly(RoleRequired):
    allowed_roles = STAFF_ROLE_NAMES


class AdminOnly(RoleRequired):
    allowed_roles = ("SUPERADMIN", "ADMIN")


class PortalUser(RoleRequired):
    allowed_roles = ("PARENT", "STUDENT")


class StaffAndMFAVerified(BasePermission):
    """The default for staff-facing viewsets that touch person data: a staff
    role *and* a satisfied second factor. Compose object-level scoping on top."""

    def has_permission(self, request, view):
        return StaffOnly().has_permission(request, view) and MFAVerified().has_permission(
            request, view
        )


class IsObjectOwnerOrStaff(BasePermission):
    """
    Object-level scoping. Staff pass; a portal user passes only for objects
    that belong to them. The model must implement ``is_visible_to(user)``.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if getattr(user, "role", None) in ("SUPERADMIN", "ADMIN", "FRONT_DESK", "TEACHER", "TUTOR"):
            return True
        checker = getattr(obj, "is_visible_to", None)
        return bool(checker and checker(user))


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
