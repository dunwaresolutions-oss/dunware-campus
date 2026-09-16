"""
Payments (see docs/DATA_MODEL.md, Phase-0 decisions, and Campus_Payments_Action_Plan.html
- P2/P3 of that accepted roadmap).

A manual "mark paid" workflow (real since Phase 7), plus, as of P2/P3, real
online-gateway checkout: `GatewayConfig` (this install's one configured
gateway - Direct-API-Key model, keys encrypted) and `PaymentAttempt` (the
audit trail of one hosted checkout, worked by the poller / resolved on
demand). No card data is ever collected or stored by Campus itself - a
gateway's hosted checkout is what actually takes the card, Campus only ever
sees a reference/amount/status. Amounts are integer cents throughout, to
avoid float rounding.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.fields import EncryptedCharField, EncryptedTextField
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


class Gateway(models.TextChoices):
    """Shared across `GatewayConfig`, `Payment.gateway` and `PaymentAttempt.gateway`
    so there's exactly one list of gateway names in the codebase. MANUAL isn't
    a real online gateway - it's the explicit "no online gateway configured"
    value `GatewayConfig` defaults to, kept in the same enum so a config row
    always has *a* value rather than a separate nullable flag."""

    MANUAL = "MANUAL", "Manual only"
    PAYSTACK = "PAYSTACK", "Paystack"
    FLUTTERWAVE = "FLUTTERWAVE", "Flutterwave"
    STRIPE = "STRIPE", "Stripe"
    KANOO = "KANOO", "Kanoo"


class GatewayConfig(BaseModel):
    """This install's one configured online gateway - Direct API Key model
    (Campus_Payments_Action_Plan.html decision 1): the school's own merchant
    keys, pasted in and stored encrypted, never a Dunware-held account.
    Singleton, same pattern as `SiteConfiguration`/`SchoolProfile` - "one
    active row per install" (decision 9) means one row, not one-of-many with
    an active flag. Written only by `manage set_gateway_config` (the eventual
    companion app's Payments tab shells out to the same command) - there is
    deliberately no browser-facing write endpoint for secret keys (decision
    9: "The browser wizard is not the place for it")."""

    gateway = models.CharField(max_length=12, choices=Gateway.choices, default=Gateway.MANUAL)

    class Mode(models.TextChoices):
        TEST = "TEST", "Test"
        LIVE = "LIVE", "Live"

    mode = models.CharField(max_length=4, choices=Mode.choices, default=Mode.TEST)
    public_key = models.CharField(max_length=255, blank=True, default="")
    secret_key = EncryptedCharField(max_length=255, blank=True, default="")
    # reserved for a possible future aggregator/subaccount model - not used by
    # the Direct API Key model P2/P3 actually implement.
    subaccount_id = models.CharField(max_length=100, blank=True, default="")
    configured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    configured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_gateway_config"
        verbose_name = "gateway configuration"

    def __str__(self) -> str:
        return f"{self.get_gateway_display()} ({self.mode})"

    @classmethod
    def load(cls) -> GatewayConfig:
        obj = cls.objects.first()
        return obj if obj is not None else cls.objects.create()

    @property
    def is_online(self) -> bool:
        return self.gateway != Gateway.MANUAL


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

    invoice_number = models.CharField(
        max_length=20, unique=True, blank=True, editable=False,
        help_text="Human-readable reference (INV-000123), assigned on creation.",
    )
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
    currency = models.CharField(max_length=3, blank=True)  # ISO-4217; site default
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

    def save(self, *args, **kwargs):
        if self._state.adding and not self.currency:
            from apps.core.models import SiteConfiguration

            self.currency = SiteConfiguration.load().currency
        if self._state.adding and self.guardian_id is None:
            # The field's own help_text has always promised this ("defaults
            # to the primary contact") but nothing implemented it - every
            # invoice was silently created with guardian=None unless a
            # caller set it explicitly. That was harmless while visibility
            # was checked through the student (any linked guardian could
            # see it); now that `is_visible_to` checks this FK specifically
            # (multi-child invoicing work, 2026-09-16), an unset guardian
            # would make the invoice invisible to everyone but staff -  so
            # the documented default has to actually exist.
            from apps.people.models import GuardianLink

            link = (
                GuardianLink.objects.filter(student_id=self.student_id, is_primary_contact=True)
                .select_related("guardian").first()
            )
            if link:
                self.guardian = link.guardian
        if self._state.adding and not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
        super().save(*args, **kwargs)

    @classmethod
    def _generate_invoice_number(cls) -> str:
        """INV-000123, sequential enough for a human to reference on the
        phone or a cheque memo. Not concurrency-hardened with a DB sequence
        (the PK is a UUID, not an integer) - fine for this product's actual
        usage pattern (front-desk staff creating invoices one at a time);
        the existence check is a cheap defensive backstop, not a real lock."""
        n = cls.objects.count() + 1
        while cls.objects.filter(invoice_number=f"INV-{n:06d}").exists():
            n += 1
        return f"INV-{n:06d}"

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
            # Deliberately NOT `self.student.is_visible_to(user)` - that
            # asks "is any guardian linked to this child," which any
            # linked guardian (a non-custodial parent, an estranged
            # co-parent with no financial role) would pass. An invoice
            # discloses financial detail about a *specific billing
            # relationship*, not just the student - only the guardian
            # actually assigned to it should ever see it. Tightened
            # 2026-09-16 (multi-child invoicing work exposed this as a
            # real gap in the existing single-invoice model too, not
            # something the new feature introduces).
            guardian = getattr(user, "guardian_profile", None)
            return guardian is not None and self.guardian_id == guardian.id
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
    """A recorded payment - manual (front office entered it after the fact)
    or, as of P3, gateway-sourced (a `PaymentAttempt` resolved to success).
    `source` distinguishes the two; `method` describes a manual payment's
    real-world form and is blank for a gateway payment (there's no
    cash/cheque/e-transfer/terminal "method" for a hosted-checkout charge -
    `gateway` + `gateway_reference` already say exactly what it was)."""

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        GATEWAY = "GATEWAY", "Online gateway"

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        CHEQUE = "CHEQUE", "Cheque"
        E_TRANSFER = "E_TRANSFER", "e-Transfer"
        CARD_TERMINAL = "CARD_TERMINAL", "Card — terminal"
        OTHER = "OTHER", "Other"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount_cents = models.PositiveIntegerField()
    source = models.CharField(max_length=7, choices=Source.choices, default=Source.MANUAL)
    method = models.CharField(max_length=13, choices=Method.choices, blank=True, default="")
    gateway = models.CharField(max_length=12, choices=Gateway.choices, blank=True, default="")
    gateway_reference = models.CharField(max_length=100, blank=True, default="")
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
        label = self.method or self.get_gateway_display()
        return f"${self.amount_cents / 100:.2f} {label} on invoice {self.invoice_id}"

    def is_visible_to(self, user) -> bool:
        return self.invoice.is_visible_to(user)


class PaymentAttempt(SensitiveModel):
    """The audit trail of one hosted-checkout attempt (Campus_Payments_Action_Plan.html
    §data — new in P2/P3). Created when a Pay action calls `gateway.initialize()`;
    resolved (on demand today - see `services.resolve_payment_attempt` - by a
    scheduled poller once P4 lands) by calling `gateway.verify()`. A verified
    SUCCESS whose amount/currency match this attempt creates a real `Payment`;
    a mismatch is never auto-applied. `raw_response` holds the last `verify`
    payload as dispute evidence - encrypted, since a gateway's response can
    include payer details (email, card brand/last4, etc)."""

    PII_FIELDS = ("raw_response",)
    PII_PURPOSE = {"raw_response": "dispute evidence for one checkout; the gateway's own payload"}

    class Status(models.TextChoices):
        INITIALIZED = "INITIALIZED", "Initialized"
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        ABANDONED = "ABANDONED", "Abandoned"
        MISMATCH = "MISMATCH", "Mismatch"

    gateway = models.CharField(max_length=12, choices=Gateway.choices)
    reference = models.CharField(max_length=64, unique=True)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=11, choices=Status.choices, default=Status.INITIALIZED)
    checkout_url = models.CharField(max_length=500, blank=True, default="")
    gateway_session_id = models.CharField(
        max_length=255, blank=True, default="",
        help_text="The gateway's OWN id for this checkout, when it has one distinct "
                   "from `reference` (e.g. Stripe's Checkout Session id - Stripe has no "
                   "verify-by-your-own-reference endpoint, only by its own id). Blank for "
                   "a gateway that verifies by `reference` directly (Paystack, Flutterwave).",
    )
    channel = models.CharField(max_length=30, blank=True, default="")
    raw_response = EncryptedTextField(blank=True, default="")
    initialized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
        help_text="Who triggered checkout - the parent from the portal, or "
                   "staff generating a payment link.",
    )
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_payment_attempt"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["gateway", "status"])]

    def __str__(self) -> str:
        return f"{self.gateway} attempt {self.reference} ({self.status})"

    def is_visible_to(self, user) -> bool:
        # No `invoice` FK here (see PaymentAttemptInvoice) - an attempt
        # always has at least one allocation, single- or multi-invoice
        # alike, and is visible only if *every* allocated invoice is
        # visible to `user` (a combined family payment must not leak one
        # child's billing detail to a guardian who only has rights to
        # another child on the same attempt).
        allocations = list(self.allocations.select_related("invoice"))
        return bool(allocations) and all(a.invoice.is_visible_to(user) for a in allocations)


class PaymentAttemptInvoice(BaseModel):
    """One invoice's slice of a `PaymentAttempt` - always present, even for
    the plain single-invoice case (one row, 100% of the amount), so
    `resolve_payment_attempt`'s success handling never needs two code
    paths for "one invoice" vs "several." Lets a family combine multiple
    children's invoices into one real gateway charge (one transaction fee,
    not one per child) while each invoice's own ledger still updates
    correctly - `allocated_cents` is this invoice's share of whatever the
    parent actually paid, which may be less than the full combined balance
    (partial payment is allowed - see `services.allocate_payment`)."""

    attempt = models.ForeignKey(
        PaymentAttempt, on_delete=models.CASCADE, related_name="allocations"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="payment_attempt_allocations"
    )
    allocated_cents = models.PositiveIntegerField()

    class Meta:
        db_table = "billing_payment_attempt_invoice"
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "invoice"], name="one_allocation_per_invoice_per_attempt"
            )
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id}: ${self.allocated_cents / 100:.2f} -> invoice {self.invoice_id}"


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
