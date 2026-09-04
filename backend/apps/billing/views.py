from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import FrontOffice, IsObjectOwnerOrStaff, MFAVerified
from apps.people.models import Student

from .models import Credit, FeeSchedule, Invoice, InvoiceLine, Payment
from .serializers import (
    CreditSerializer,
    FeeScheduleSerializer,
    InvoiceLineSerializer,
    InvoiceSerializer,
    PaymentSerializer,
)
from .services import issue_invoice, mark_paid, void_invoice

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


class FeeScheduleViewSet(CampusViewSet):
    queryset = FeeSchedule.objects.select_related("group")
    serializer_class = FeeScheduleSerializer
    permission_classes = [FrontOffice, MFAVerified]
    audit_reads = False


class InvoiceViewSet(CampusViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [BillingAccess, IsObjectOwnerOrStaff]
    audit_reads = True

    def get_queryset(self):
        # No prefetch_related on lines/payments here: total_cents/paid_cents
        # use .aggregate(), which always re-queries, but keeping the instance
        # itself uncached avoids any confusion after issue/mark-paid actions.
        qs = Invoice.objects.select_related("student", "guardian", "term")
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            return qs
        if role == Role.PARENT:
            return qs.exclude(status=Invoice.Status.DRAFT).filter(
                student__in=Student.visible_queryset(self.request.user)
            )
        return qs.none()

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


class InvoiceLineViewSet(CampusViewSet):
    serializer_class = InvoiceLineSerializer
    permission_classes = [FrontOffice, MFAVerified]
    audit_reads = False

    def get_queryset(self):
        return InvoiceLine.objects.select_related("invoice", "fee_schedule")


class PaymentViewSet(CampusViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [BillingAccess, IsObjectOwnerOrStaff]
    audit_reads = True
    http_method_names = ["get", "head", "options"]  # created only via /mark-paid

    def get_queryset(self):
        qs = Payment.objects.select_related("invoice", "invoice__student")
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            return qs
        if role == Role.PARENT:
            return qs.filter(invoice__student__in=Student.visible_queryset(self.request.user))
        return qs.none()


class CreditViewSet(CampusViewSet):
    serializer_class = CreditSerializer
    permission_classes = [FrontOffice, MFAVerified]
    audit_reads = False

    def get_queryset(self):
        return Credit.objects.select_related("student", "applied_to_invoice")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
