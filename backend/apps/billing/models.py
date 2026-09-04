"""
Payments — PLACEHOLDER only in v1 (see docs/DATA_MODEL.md, Phase-0 decisions).

Real models, a real manual "mark paid" workflow, and a `PaymentGateway`
interface with a working `ManualGateway` and a **stubbed** `StripeGateway`
(raises `NotImplementedError`). No card data is ever collected or stored —
there is nothing here for PCI scope to attach to. Amounts are integer cents to
avoid float rounding.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.models import BaseModel, SensitiveModel
from apps.people.models import Group, Guardian, Student

_ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK})


class FeeSchedule(BaseModel):
    class Frequency(models.TextChoices):
        ONE_TIME = "ONE_TIME", "One-time"
        MONTHLY = "MONTHLY", "Monthly"
        TERM = "TERM", "Per term"
        ANNUAL = "ANNUAL", "Annual"

    name = models.CharField(max_length=150)
    description = models.CharField(max_length=255, blank=True)
    amount_cents = models.PositiveIntegerField()
    frequency = models.CharField(max_length=10, choices=Frequency.choices,
                                 default=Frequency.ONE_TIME)
    group = models.ForeignKey(
        Group, null=True, blank=True, on_delete=models.SET_NULL, related_name="fee_schedules"
    )
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "billing_fee_schedule"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} (${self.amount_cents / 100:.2f})"


class Invoice(SensitiveModel):
    """A family's bill. Sensitive because it discloses financial detail about
    a specific child/family — reads are audited like any other."""

    PII_FIELDS = ("notes",)

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
        PAID = "PAID", "Paid"
        OVERDUE = "OVERDUE", "Overdue"
        VOID = "VOID", "Void"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="invoices")
    guardian = models.ForeignKey(
        Guardian, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices",
        help_text="Who the bill goes to; defaults to the primary contact.",
    )
    term = models.ForeignKey(
        "scheduling.Term", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="invoices",
    )
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.DRAFT)
    issued_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "billing_invoice"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["student", "status"])]

    def __str__(self) -> str:
        return f"invoice {self.pk} for {self.student_id} ({self.status})"

    @property
    def total_cents(self) -> int:
        # .aggregate() always issues a fresh query — unlike .all(), it is not
        # fooled by a stale prefetch_related cache from before a line/payment
        # was added in the same request.
        agg = self.lines.aggregate(total=models.Sum(models.F("quantity") * models.F(
            "unit_amount_cents"
        )))
        return agg["total"] or 0

    @property
    def paid_cents(self) -> int:
        agg = self.payments.aggregate(total=models.Sum("amount_cents"))
        return agg["total"] or 0

    @property
    def balance_cents(self) -> int:
        return max(self.total_cents - self.paid_cents, 0)

    def refresh_status(self):
        if self.status in (self.Status.VOID,):
            return
        total, paid = self.total_cents, self.paid_cents
        if total == 0:
            new = self.status
        elif paid >= total:
            new = self.Status.PAID
        elif paid > 0:
            new = self.Status.PARTIALLY_PAID
        elif self.status == self.Status.DRAFT:
            new = self.Status.DRAFT
        else:
            new = self.Status.ISSUED
        if new != self.status:
            self.status = new
            self.save(update_fields=["status", "updated_at"])

    def is_visible_to(self, user) -> bool:
        role = getattr(user, "role", None)
        if role in _ADMIN_ROLES:
            return True
        if role == Role.PARENT:
            return self.student.is_visible_to(user)
        return False


class InvoiceLine(BaseModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    fee_schedule = models.ForeignKey(
        FeeSchedule, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_amount_cents = models.PositiveIntegerField()

    class Meta:
        db_table = "billing_invoice_line"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.description} x{self.quantity}"

    @property
    def amount_cents(self) -> int:
        return self.quantity * self.unit_amount_cents

    def is_visible_to(self, user) -> bool:
        return self.invoice.is_visible_to(user)


class Payment(BaseModel):
    """A manually recorded payment. There is no card path — `method` is one of
    the manual options only; `StripeGateway` never reaches this model."""

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        CHEQUE = "CHEQUE", "Cheque"
        E_TRANSFER = "E_TRANSFER", "e-Transfer"
        OTHER = "OTHER", "Other"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount_cents = models.PositiveIntegerField()
    method = models.CharField(max_length=10, choices=Method.choices)
    reference = models.CharField(max_length=100, blank=True)
    received_at = models.DateTimeField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "billing_payment"
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"${self.amount_cents / 100:.2f} {self.method} on invoice {self.invoice_id}"

    def is_visible_to(self, user) -> bool:
        return self.invoice.is_visible_to(user)


class Credit(BaseModel):
    """A manual adjustment in the family's favour (refund, goodwill, error
    correction) — never an automated card refund; see `PaymentGateway.refund`."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="credits")
    amount_cents = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    applied_to_invoice = models.ForeignKey(
        Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="credits"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "billing_credit"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"credit ${self.amount_cents / 100:.2f} for {self.student_id}"

    def is_visible_to(self, user) -> bool:
        return self.student.is_visible_to(user)
