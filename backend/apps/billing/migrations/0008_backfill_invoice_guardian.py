from django.db import migrations


def fill(apps, schema_editor):
    """`Invoice.save()` only started defaulting `guardian` to the
    student's primary contact at creation time on 2026-09-16 (alongside
    multi-invoice combine) - every invoice created before that, real or
    seeded, was left with `guardian_id` NULL. That silently broke online
    payment for every one of them (initiate_online_payment's guardian-
    consistency check, and the parent-ownership check in views.py, both
    require it) - found the same day a guardian tried to pay a real
    invoice. Runtime code also falls back via `Invoice.effective_guardian`
    for a row this can't resolve (no primary contact on file at all), but
    backfilling the column is the real, permanent fix."""
    Invoice = apps.get_model("billing", "Invoice")
    GuardianLink = apps.get_model("people", "GuardianLink")

    primary_links = {
        link["student_id"]: link["guardian_id"]
        for link in GuardianLink.objects.filter(is_primary_contact=True)
        .values("student_id", "guardian_id")
    }
    updates = []
    for invoice in Invoice.objects.filter(guardian__isnull=True).only("id", "student_id"):
        guardian_id = primary_links.get(invoice.student_id)
        if guardian_id:
            invoice.guardian_id = guardian_id
            updates.append(invoice)
    if updates:
        Invoice.objects.bulk_update(updates, ["guardian_id"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0007_multi_invoice_payment_attempts"),
        ("people", "0001_initial"),
    ]

    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
