"""One small, real, payable invoice per Paystack-supported currency - lets
Damien exercise the online-checkout flow (console "generate a payment link",
or the parent portal's Pay button) against every currency Paystack's own
account can be configured for, ahead of confirming Paystack end-to-end the
way Stripe already is (see gateways.py, PaystackGateway).

Paystack's supported currencies (paystack.com/docs, verified 2026-09-18):
NGN, GHS, ZAR, KES, USD - a single Paystack merchant account is normally
configured for ONE of these (matching the country it was registered in;
NG/KE accounts can also enable USD alongside their base currency), so this
does not imply a real install would ever bill a family in five currencies
at once - it exists purely to let one `GatewayConfig` be test-driven against
whichever of the five currencies its keys are actually live for, without
regenerating the whole seed_demo dataset (--currency) each time.

    campus-app.exe manage seed_paystack_currencies
    campus-app.exe manage seed_paystack_currencies --flush   # replace them
"""
from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.billing.models import Invoice, InvoiceLine
from apps.billing.services import issue_invoice
from apps.people.models import Guardian, GuardianLink, Student

# Paystack's documented supported-currency list - re-check paystack.com/docs
# before trusting this long-term, it is a live third party's own decision,
# not something Campus controls.
PAYSTACK_CURRENCIES = ["NGN", "GHS", "ZAR", "KES", "USD"]

# A flat, memorable test amount (minor units - matches Campus's *_cents
# convention) - realism doesn't matter here, only that checkout completes.
TEST_AMOUNT_CENTS = 5_000  # e.g. NGN 50.00, USD 50.00, etc.

_MARKER_PREFIX = "PSTK-"  # student_number prefix - how --flush finds these rows again


class Command(BaseCommand):
    help = (
        "Seed one test student/guardian/invoice per Paystack-supported currency, "
        "for exercising the online-checkout flow across all of them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete previously-seeded Paystack test invoices/students first "
                 "(matched by student_number prefix 'PSTK-'), then recreate them.",
        )
        parser.add_argument("--force", action="store_true",
                            help="Allow running even when DEBUG is False")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to seed with DEBUG=False. Pass --force if you mean it.")

        with transaction.atomic():
            if options["flush"]:
                deleted, _ = Student.objects.filter(
                    student_number__startswith=_MARKER_PREFIX
                ).delete()
                self.stdout.write(f"flushed {deleted} previously-seeded row(s)")

            created = []
            skipped = []
            for code in PAYSTACK_CURRENCIES:
                student_number = f"{_MARKER_PREFIX}{code}"
                if Student.objects.filter(student_number=student_number).exists():
                    skipped.append(code)
                    continue
                inv = self._seed_one(code, student_number)
                created.append((code, inv))

        for code, inv in created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{code}: invoice {inv.invoice_number} "
                    f"({inv.total_cents / 100:.2f} {code}) - {inv.pk}"
                )
            )
        for code in skipped:
            self.stdout.write(
                f"{code}: test invoice already exists (student {_MARKER_PREFIX}{code}) "
                "- pass --flush to replace it"
            )
        self.stdout.write(self.style.SUCCESS(
            f"done: {len(created)} created, {len(skipped)} already present"
        ))

    @staticmethod
    def _seed_one(code: str, student_number: str) -> Invoice:
        student = Student.objects.create(
            first_name="Paystack", last_name=f"Test {code}",
            date_of_birth=dt.date(2012, 1, 1),
            student_number=student_number, status=Student.Status.ENROLLED,
        )
        guardian = Guardian.objects.create(
            first_name="Paystack", last_name=f"Guardian {code}",
            # example.com, not example.test - Paystack's own email validator
            # rejects the `.test` TLD ('"email" must be a valid email'), and
            # example.com is equally guaranteed non-deliverable (also an
            # IANA-reserved documentation domain), just one whose TLD a
            # picky third-party validator actually recognizes.
            email=f"paystack.test.{code.lower()}@example.com",
        )
        GuardianLink.objects.create(
            student=student, guardian=guardian, relationship=GuardianLink.Relationship.MOTHER,
            is_primary_contact=True, has_custody=True, can_pickup=True,
            receives_communications=True, lives_with=True,
        )
        # Explicit `currency=code`, not the site default - Invoice.save() only
        # fills it in when unset (apps/billing/models.py), so this overrides
        # SiteConfiguration for this one test invoice regardless of what the
        # install is otherwise configured for.
        inv = Invoice.objects.create(
            student=student, currency=code,
            due_date=dt.date.today() + dt.timedelta(days=30),
            notes=f"Paystack gateway test invoice ({code}) - synthetic, not a real fee.",
        )
        InvoiceLine.objects.create(
            invoice=inv, description=f"Paystack gateway test charge ({code})",
            unit_amount_cents=TEST_AMOUNT_CENTS,
        )
        issue_invoice(inv)
        return inv
