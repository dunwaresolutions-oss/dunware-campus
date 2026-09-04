from __future__ import annotations

from rest_framework import serializers

from .models import Credit, FeeSchedule, Invoice, InvoiceLine, Payment


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

    class Meta:
        model = Payment
        fields = ["id", "invoice", "amount_cents", "method", "reference",
                  "received_at", "received_by", "note", "created_at"]
        read_only_fields = ["received_at", "received_by"]


class CreditSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Credit
        fields = ["id", "student", "amount_cents", "reason", "applied_to_invoice",
                  "created_by", "created_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    total_cents = serializers.IntegerField(read_only=True)
    paid_cents = serializers.IntegerField(read_only=True)
    balance_cents = serializers.IntegerField(read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "student", "guardian", "term", "status", "issued_at", "due_date",
            "notes", "created_by", "lines", "payments", "total_cents", "paid_cents",
            "balance_cents", "created_at",
        ]
        read_only_fields = ["status", "issued_at"]
