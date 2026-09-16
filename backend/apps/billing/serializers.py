from __future__ import annotations

from rest_framework import serializers

from .models import (
    Credit,
    FeeSchedule,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentAttempt,
    PaymentAttemptInvoice,
)


class FeeScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeSchedule
        fields = ["id", "name", "description", "amount_cents", "frequency", "group", "active"]


class InvoiceLineSerializer(serializers.ModelSerializer):
    amount_cents = serializers.IntegerField(read_only=True)

    class Meta:
        model = InvoiceLine
        fields = ["id", "invoice", "fee_schedule", "description", "quantity",
                  "unit_amount_cents", "amount_cents"]


class PaymentSerializer(serializers.ModelSerializer):
    received_by = serializers.PrimaryKeyRelatedField(read_only=True)
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    student_name = serializers.CharField(source="invoice.student.display_name", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "invoice", "invoice_number", "student_name", "amount_cents",
                  "source", "method", "gateway", "gateway_reference", "reference",
                  "received_at", "received_by", "note", "created_at"]
        read_only_fields = ["received_at", "received_by"]


class PaymentAttemptInvoiceSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    student_name = serializers.CharField(source="invoice.student.display_name", read_only=True)

    class Meta:
        model = PaymentAttemptInvoice
        fields = ["invoice", "invoice_number", "student_name", "allocated_cents"]
        read_only_fields = fields


class PaymentAttemptSerializer(serializers.ModelSerializer):
    """No `raw_response` here — it's the gateway's own payload (dispute
    evidence, not something a client needs), and it's the one encrypted PII
    field on this model; nothing forces it to round-trip through the API.

    `allocations` replaces the old singular `invoice`/`invoice_number`
    fields - every attempt (single- or multi-invoice alike) has at least
    one, so a client never has to special-case "was this a combined
    payment"."""

    allocations = PaymentAttemptInvoiceSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentAttempt
        fields = ["id", "allocations", "gateway", "reference", "amount_cents",
                  "currency", "status", "checkout_url", "channel", "created_at", "updated_at"]
        read_only_fields = fields


class CreditSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    student_name = serializers.CharField(source="student.display_name", read_only=True)

    class Meta:
        model = Credit
        fields = ["id", "student", "student_name", "amount_cents", "reason",
                  "applied_to_invoice", "created_by", "created_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    total_cents = serializers.IntegerField(read_only=True)
    paid_cents = serializers.IntegerField(read_only=True)
    balance_cents = serializers.IntegerField(read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    guardian_name = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id", "invoice_number", "student", "student_name", "guardian", "guardian_name",
            "term", "status", "currency", "issued_at", "due_date", "notes", "created_by",
            "lines", "payments", "total_cents", "paid_cents", "balance_cents",
            "created_at",
        ]
        read_only_fields = ["status", "issued_at", "currency", "invoice_number"]

    def get_guardian_name(self, obj) -> str:
        g = obj.guardian
        return f"{g.first_name} {g.last_name}".strip() if g else ""
