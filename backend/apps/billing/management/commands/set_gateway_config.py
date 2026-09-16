"""Set this install's one online payment gateway (companion tool -
Campus_Payments_Action_Plan.html decision 9: the browser wizard is not the
place for this, only the elevated companion / this command).

    campus-app.exe manage set_gateway_config --gateway paystack --mode test \
        --public-key pk_test_xxx --secret-key sk_test_xxx
    campus-app.exe manage set_gateway_config --gateway manual   # turn online payments back off
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.billing.models import Gateway, GatewayConfig


class Command(BaseCommand):
    help = "Configure this install's online payment gateway."

    def add_arguments(self, parser):
        parser.add_argument(
            "--gateway", required=True,
            choices=[c.lower() for c in Gateway.values],
        )
        parser.add_argument("--mode", default=None, choices=["test", "live"])
        parser.add_argument("--public-key", default=None)
        parser.add_argument("--secret-key", default=None)
        parser.add_argument("--subaccount-id", default=None)

    def handle(self, *args, **o):
        gateway = o["gateway"].upper()
        if gateway != Gateway.MANUAL and not (o["public_key"] and o["secret_key"]):
            raise CommandError(
                f"--public-key and --secret-key are required to configure {gateway} "
                "(omit both, with --gateway manual, to turn online payments off instead)."
            )

        cfg = GatewayConfig.load()
        cfg.gateway = gateway
        if o["mode"]:
            cfg.mode = o["mode"].upper()
        if o["public_key"] is not None:
            cfg.public_key = o["public_key"]
        if o["secret_key"] is not None:
            cfg.secret_key = o["secret_key"]
        if o["subaccount_id"] is not None:
            cfg.subaccount_id = o["subaccount_id"]
        cfg.configured_at = timezone.now()
        cfg.save()

        masked = f"{cfg.secret_key[:7]}…" if cfg.secret_key else "(none)"
        self.stdout.write(
            f"gateway config: {cfg.get_gateway_display()} ({cfg.mode}) "
            f"public_key={cfg.public_key or '(none)'} secret_key={masked}"
        )
