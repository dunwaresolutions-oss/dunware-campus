from __future__ import annotations

from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import (
    BillingEnabled,
    FrontOffice,
    IsObjectOwnerOrStaff,
    MFAVerified,
)
from apps.people.models import Student

from .gateways import GatewayError, GatewayNotConfigured
from .models import Credit, FeeSchedule, Invoice, InvoiceLine, Payment, PaymentAttempt
from .serializers import (
    CreditSerializer,
    FeeScheduleSerializer,
    InvoiceLineSerializer,
    InvoiceSerializer,
    PaymentAttemptSerializer,
    PaymentSerializer,
)
from .services import (
    initiate_online_payment,
    issue_invoice,
    mark_paid,
    resolve_payment_attempt,
    void_invoice,
)

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}


class BillingAccess(BasePermission):
    """Only the front office and billing's own object-level owners (a
    guardian, via the queryset scoping) may touch invoices/payments — nobody
    else, including teachers, has a billing reason to be here."""

    def has_permission(self, request, view):
        if not MFAVerified().has_permission(request, view):
            return False
        role = getattr(request.user, "role", None)
        if request.method in SAFE_METHODS:
            return role in _ADMIN_ROLES or role == Role.PARENT
        return role in _ADMIN_ROLES


class CanPayInvoice(BasePermission):
    """`pay` is the one billing write a parent may trigger directly — every
    other write (issue/void/mark-paid/create) is staff-only via
    `BillingAccess`. `IsObjectOwnerOrStaff` still does the object-level check
    (a parent may only pay their own child's invoice)."""

    def has_permission(self, request, view):
        if not MFAVerified().has_permission(request, view):
            return False
        role = getattr(request.user, "role", None)
        return role in _ADMIN_ROLES or role == Role.PARENT


class FeeScheduleViewSet(CampusViewSet):
    serializer_class = FeeScheduleSerializer
    permission_classes = [BillingEnabled, FrontOffice, MFAVerified]
    audit_reads = False

    def get_queryset(self):
        qs = FeeSchedule.objects.select_related("group")
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return qs


# statuses that mean "this family still owes money on it" - matches the
# open/unpaid check already used when the collects-fees toggle is turned off
# (apps/core/views.py) and the dashboard's own outstanding-fees figure.
_OUTSTANDING_STATUSES = [
    Invoice.Status.ISSUED, Invoice.Status.PARTIALLY_PAID, Invoice.Status.OVERDUE,
]


class InvoiceViewSet(CampusViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [BillingEnabled, BillingAccess, IsObjectOwnerOrStaff]
    audit_reads = True

    def get_permissions(self):
        if self.action == "pay":
            return [p() for p in (BillingEnabled, CanPayInvoice, IsObjectOwnerOrStaff)]
        return super().get_permissions()

    def get_queryset(self):
        # No prefetch_related on lines/payments here: total_cents/paid_cents
        # use .aggregate(), which always re-queries, but keeping the instance
        # itself uncached avoids any confusion after issue/mark-paid actions.
        qs = Invoice.objects.select_related("student", "guardian", "term")
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            pass
        elif role == Role.PARENT:
            qs = qs.exclude(status=Invoice.Status.DRAFT).filter(
                student__in=Student.visible_queryset(self.request.user)
            )
        else:
            return qs.none()
        params = self.request.query_params
        if params.get("outstanding"):
            qs = qs.filter(status__in=_OUTSTANDING_STATUSES)
        elif params.get("status"):
            qs = qs.filter(status=params["status"])
        q = (params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(invoice_number__icontains=q)
                | Q(student__first_name__icontains=q)
                | Q(student__last_name__icontains=q)
                | Q(student__preferred_name__icontains=q)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        invoice = issue_invoice(self.get_object(), actor=request.user)
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        invoice = void_invoice(
            self.get_object(), reason=request.data.get("reason", ""), actor=request.user
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid_action(self, request, pk=None):
        invoice = self.get_object()
        payment = mark_paid(
            invoice, amount_cents=int(request.data["amount_cents"]),
            method=request.data["method"], reference=request.data.get("reference", ""),
            by=request.user, note=request.data.get("note", ""),
        )
        invoice.refresh_from_db()
        return Response(
            {"invoice": self.get_serializer(invoice).data,
             "payment": PaymentSerializer(payment).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """Start a hosted checkout (P3 §flow). Parents call this from the
        portal's Pay button; front office can also call it to "generate a
        payment link" for a family that doesn't use the portal — same
        endpoint either way, `initialized_by` just records who."""
        invoice = self.get_object()
        return_url = (request.data.get("return_url") or "")[:500]
        try:
            attempt = initiate_online_payment(
                invoice, initialized_by=request.user, return_url=return_url
            )
        except GatewayNotConfigured as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except GatewayError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentAttemptSerializer(attempt).data, status=status.HTTP_201_CREATED)


class InvoiceLineViewSet(CampusViewSet):
    serializer_class = InvoiceLineSerializer
    permission_classes = [BillingEnabled, FrontOffice, MFAVerified]
    audit_reads = False

    def get_queryset(self):
        return InvoiceLine.objects.select_related("invoice", "fee_schedule")


class PaymentViewSet(CampusViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [BillingEnabled, BillingAccess, IsObjectOwnerOrStaff]
    audit_reads = True
    http_method_names = ["get", "head", "options"]  # created only via /mark-paid

    def get_queryset(self):
        qs = Payment.objects.select_related("invoice", "invoice__student")
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            pass
        elif role == Role.PARENT:
            qs = qs.filter(invoice__student__in=Student.visible_queryset(self.request.user))
        else:
            return qs.none()
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(invoice__invoice_number__icontains=q)
                | Q(invoice__student__first_name__icontains=q)
                | Q(invoice__student__last_name__icontains=q)
                | Q(reference__icontains=q)
            )
        return qs


class PaymentAttemptViewSet(CampusViewSet):
    """Read-only — an attempt is only ever created via `InvoiceViewSet.pay`.
    Looked up by `reference` (not the UUID pk): the portal's return-poll page
    (P3 §flow, step 4) is handed the reference in the checkout redirect, and
    `retrieve` resolves it live against the gateway (see
    `services.resolve_payment_attempt`) rather than just reading a cached
    row — the return-poll page needs this endpoint to actually be the
    confirmation path today, ahead of P4's scheduled poller."""

    serializer_class = PaymentAttemptSerializer
    permission_classes = [BillingEnabled, BillingAccess, IsObjectOwnerOrStaff]
    http_method_names = ["get", "head", "options"]
    lookup_field = "reference"
    lookup_value_regex = "[^/]+"
    audit_reads = False  # a polled confirmation status, not a sensitive record browse

    def get_queryset(self):
        qs = PaymentAttempt.objects.select_related("invoice", "invoice__student")
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            return qs
        if role == Role.PARENT:
            return qs.filter(invoice__student__in=Student.visible_queryset(self.request.user))
        return qs.none()

    def retrieve(self, request, *args, **kwargs):
        attempt = resolve_payment_attempt(self.get_object())
        return Response(self.get_serializer(attempt).data)


class CreditViewSet(CampusViewSet):
    serializer_class = CreditSerializer
    permission_classes = [BillingEnabled, FrontOffice, MFAVerified]
    audit_reads = False

    def get_queryset(self):
        qs = Credit.objects.select_related("student", "applied_to_invoice")
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(student__first_name__icontains=q)
                | Q(student__last_name__icontains=q)
                | Q(reason__icontains=q)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
