"""Invoice lifecycle: draft -> issued -> (partially) paid / void."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record

from .gateways import get_gateway
from .models import Invoice, Payment


def issue_invoice(invoice: Invoice, *, actor=None) -> Invoice:
    if invoice.status != Invoice.Status.DRAFT:
        return invoice
    invoice.status = Invoice.Status.ISSUED
    invoice.issued_at = timezone.now()
    invoice.save(update_fields=["status", "issued_at", "updated_at"])
    record(AuditAction.UPDATE, invoice, summary="invoice issued", actor=actor)
    return invoice


@transaction.atomic
def mark_paid(invoice: Invoice, *, amount_cents: int, method: str, reference: str = "",
             by=None, note: str = "") -> Payment:
    if invoice.status == Invoice.Status.VOID:
        raise ValueError("Cannot record a payment against a void invoice.")
    gateway = get_gateway()
    return gateway.charge(
        invoice, amount_cents, method=method, reference=reference, received_by=by, note=note
    )


def void_invoice(invoice: Invoice, *, reason: str = "", actor=None) -> Invoice:
    invoice.status = Invoice.Status.VOID
    invoice.notes = (invoice.notes + f" [voided: {reason}]").strip()[:255]
    invoice.save(update_fields=["status", "notes", "updated_at"])
    record(AuditAction.UPDATE, invoice, summary=f"invoice voided ({reason or 'no reason given'})",
           actor=actor)
    return invoice


def portal_summary(student) -> list[dict]:
    """Read-only shape for the parent portal dashboard — no card data, ever."""
    rows = []
    for inv in Invoice.objects.filter(student=student).exclude(status=Invoice.Status.DRAFT):
        rows.append({
            "id": str(inv.pk),
            "status": inv.status,
            "total_cents": inv.total_cents,
            "balance_cents": inv.balance_cents,
            "due_date": inv.due_date,
        })
    return rows
