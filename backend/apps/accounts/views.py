"""
Session auth + MFA endpoints (see docs/ARCHITECTURE.md, docs/PII_SECURITY.md).

    POST /api/auth/csrf/            prime the CSRF cookie
    POST /api/auth/login/          username + password (+ otp when enrolled)
    POST /api/auth/logout/
    GET  /api/auth/whoami/
    POST /api/auth/mfa/setup/      create an unconfirmed TOTP device -> QR + secret
    POST /api/auth/mfa/confirm/    verify a code, confirm the device, verify session
    GET  /api/auth/mfa/status/
    POST /api/auth/invite/         (admin) issue a staff invitation
    POST /api/auth/invite/accept/  redeem an invitation, set your own password

Staff (``must_use_mfa``) cannot reach a sensitive endpoint until a device is
confirmed and the session is OTP-verified — enforced by
``apps.core.permissions.MFAVerified``, not here.
"""
from __future__ import annotations

from axes.handlers.proxy import AxesProxyHandler
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django_otp import login as otp_login
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.permissions import AdminOnly

from .lockout import lockout_response
from .mfa import (
    base32_secret,
    confirm_device,
    get_or_create_unconfirmed_device,
    has_confirmed_totp,
    provisioning_uri,
    qr_data_uri,
    verify_login_token,
)
from .models import User
from .serializers import (
    InviteAcceptSerializer,
    LoginSerializer,
    SetupAdminSerializer,
    StaffInviteCreateSerializer,
    TOTPTokenSerializer,
    WhoAmISerializer,
)
from .services import accept_staff_invite, bootstrap_superadmin, create_staff_invite


def _whoami(user, *, mfa_verified: bool) -> dict:
    data = dict(WhoAmISerializer(user).data)
    data["mfa_enrolled"] = has_confirmed_totp(user)
    data["mfa_verified"] = mfa_verified
    data["mfa_enrollment_required"] = bool(user.must_use_mfa) and not data["mfa_enrolled"]
    return data


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CSRFView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        username = s.validated_data["username"]
        password = s.validated_data["password"]
        otp = (s.validated_data.get("otp") or "").strip()

        credentials = {"username": username}
        if AxesProxyHandler.is_locked(request, credentials):
            return lockout_response(request, credentials)

        try:
            user = authenticate(request, username=username, password=password)
        except DjangoPermissionDenied:
            return lockout_response(request, credentials)

        if user is None or not user.is_active:
            return Response(
                {"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
            )

        enrolled = has_confirmed_totp(user)

        if enrolled:
            device = verify_login_token(user, otp)
            if device is None:
                return Response(
                    {"detail": "A valid authentication code is required.", "mfa_required": True},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            django_login(request, user)
            otp_login(request, device)
            record(AuditAction.MFA_VERIFIED, user, summary="second factor accepted", actor=user)
            return Response(_whoami(user, mfa_verified=True))

        # No device yet. Staff still get a session so they can reach MFA setup,
        # but MFAVerified will block everything sensitive until they enrol.
        django_login(request, user)
        body = _whoami(user, mfa_verified=False)
        return Response(body, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        django_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WhoAmIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        verified = bool(getattr(request.user, "is_verified", lambda: False)())
        return Response(_whoami(request.user, mfa_verified=verified))


class MFASetupView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        device = get_or_create_unconfirmed_device(request.user)
        uri = provisioning_uri(device)
        return Response(
            {"otpauth_uri": uri, "secret": base32_secret(device), "qr": qr_data_uri(uri)}
        )


class MFAConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        s = TOTPTokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        device = confirm_device(request.user, s.validated_data["token"])
        if device is None:
            return Response(
                {"detail": "That code did not verify. Try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        otp_login(request, device)
        record(
            AuditAction.MFA_ENROLLED, request.user, summary="TOTP device confirmed",
            actor=request.user,
        )
        return Response({"detail": "MFA enabled.", "mfa_enrolled": True, "mfa_verified": True})


class MFAStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "must_use_mfa": request.user.must_use_mfa,
                "mfa_enrolled": has_confirmed_totp(request.user),
                "mfa_verified": bool(getattr(request.user, "is_verified", lambda: False)()),
            }
        )


class UsersView(APIView):
    """Admin-only staff directory — just enough to populate a group-staff
    assignment picker. No PII beyond name + role + active flag."""

    permission_classes = [IsAuthenticated, AdminOnly]

    def get(self, request):
        out = [
            {
                "id": str(u.pk),
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "display_name": getattr(u, "display_name", "") or u.username,
            }
            for u in User.objects.order_by("username")
        ]
        return Response(out)


class StaffInviteView(APIView):
    permission_classes = [IsAuthenticated, AdminOnly]

    def post(self, request):
        s = StaffInviteCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        invite = create_staff_invite(
            email=s.validated_data["email"],
            role=s.validated_data["role"],
            invited_by=request.user,
        )
        return Response(
            {
                "token": invite.token,
                "email": invite.email,
                "role": invite.role,
                "expires_at": invite.expires_at,
            },
            status=status.HTTP_201_CREATED,
        )


class InviteAcceptView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        s = InviteAcceptSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = accept_staff_invite(
            token=s.validated_data["token"],
            username=s.validated_data["username"],
            password=s.validated_data["password"],
        )
        return Response(
            {"detail": "Account created. Sign in, then set up MFA.", "username": user.username},
            status=status.HTTP_201_CREATED,
        )


class SetupStatusView(APIView):
    """Unauthenticated: does this install still need its first administrator?
    Drives the browser's first-run screen. Flips to ``needs_setup: false`` the
    instant a superadmin exists, and stays there."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {"needs_setup": not User.objects.filter(is_superuser=True).exists()}
        )


class SetupAdminView(APIView):
    """First-run only: create the initial SUPERADMIN from the browser and sign
    that session straight in, so the operator lands on MFA enrolment. Returns
    409 the moment any superadmin exists (self-disabling). Rate-limited on the
    ``auth`` scope; ``bootstrap_superadmin`` writes the audit entry."""

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        if User.objects.filter(is_superuser=True).exists():
            return Response(
                {"detail": "Campus already has an administrator. Sign in instead."},
                status=status.HTTP_409_CONFLICT,
            )
        s = SetupAdminSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            validate_password(s.validated_data["password"])
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = bootstrap_superadmin(
                username=s.validated_data["username"],
                email=s.validated_data["email"],
                password=s.validated_data["password"],
            )
        except (DjangoValidationError, DRFValidationError) as exc:
            detail = getattr(exc, "messages", None) or getattr(exc, "detail", str(exc))
            if isinstance(detail, (list, tuple)):
                detail = "; ".join(str(d) for d in detail)
            return Response({"detail": str(detail)}, status=status.HTTP_400_BAD_REQUEST)
        # the user was created directly (not via authenticate()), so name the
        # real backend explicitly — axes' standalone backend is lockout-only.
        django_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(_whoami(user, mfa_verified=False), status=status.HTTP_201_CREATED)
