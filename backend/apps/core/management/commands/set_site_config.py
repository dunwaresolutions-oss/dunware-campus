"""Set the per-install region / fiscal settings (companion tool + install.ps1).

    campus-app.exe manage set_site_config --country BS --currency BSD
    campus-app.exe manage set_site_config --collects-fees no
    campus-app.exe manage set_site_config --currency USD --force   # after invoices exist
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import SiteConfiguration


class Command(BaseCommand):
    help = "Set country / currency / fee-collection for this install."

    def add_arguments(self, parser):
        parser.add_argument("--country", default=None, help="ISO-3166 alpha-2, e.g. CA")
        parser.add_argument("--currency", default=None, help="ISO-4217, e.g. CAD")
        parser.add_argument("--locale", default=None, help='e.g. "en-CA"')
        parser.add_argument("--collects-fees", default=None, choices=["yes", "no"])
        parser.add_argument(
            "--deployment-mode", default=None,
            choices=["SINGLE", "SCHOOL", "HEADQUARTERS"],
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Allow a currency change even though invoices already exist.",
        )

    def handle(self, *args, **o):
        from apps.billing.models import Invoice

        cfg = SiteConfiguration.load()

        if o["currency"] and o["currency"].upper() != cfg.currency:
            if Invoice.objects.exists() and not o["force"]:
                raise CommandError(
                    f"{Invoice.objects.count()} invoice(s) already use {cfg.currency}. "
                    "Re-run with --force to change the currency anyway."
                )
            cfg.currency = o["currency"].upper()[:3]

        if o["country"] is not None:
            cfg.country = o["country"].upper()[:2]
        if o["locale"] is not None:
            cfg.locale = o["locale"]
        if o["collects_fees"] is not None:
            cfg.collects_fees = o["collects_fees"] == "yes"
        if o["deployment_mode"] is not None:
            cfg.deployment_mode = o["deployment_mode"]

        cfg.save()
        self.stdout.write(
            f"site config: country={cfg.country or '--'} currency={cfg.currency} "
            f"collects_fees={cfg.collects_fees} mode={cfg.deployment_mode}"
        )
