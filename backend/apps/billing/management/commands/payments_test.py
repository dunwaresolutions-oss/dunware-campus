"""Ping a gateway's auth endpoint - either this install's saved
GatewayConfig, or (via the override flags) values that haven't been saved
yet at all. The companion GUI's "Test connection" button always passes the
override flags, so it tests exactly what's currently in the form - not
whatever was last Applied - see campus-payments-setup-ui.ps1.

    campus-app.exe manage payments_test
    campus-app.exe manage payments_test --gateway paystack --mode test \
        --public-key pk_test_xxx --secret-key sk_test_xxx
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.billing.gateways import OnlineGateway, get_gateway, online_gateway_class
from apps.billing.models import Gateway, GatewayConfig


class Command(BaseCommand):
    help = "Test an online payment gateway - saved config, or override values not yet saved."

    def add_arguments(self, parser):
        parser.add_argument(
            "--gateway", default=None, choices=[c.lower() for c in Gateway.values],
            help="Test these values directly instead of the saved GatewayConfig - "
                 "nothing is written to the database.",
        )
        parser.add_argument("--mode", default="test", choices=["test", "live"])
        parser.add_argument("--public-key", default=None)
        parser.add_argument("--secret-key", default=None)

    def handle(self, *args, **o):
        if o["gateway"]:
            gateway_code = o["gateway"].upper()
            if gateway_code == Gateway.MANUAL:
                raise CommandError("Manual has no online connection to test.")
            impl = online_gateway_class(gateway_code)
            if impl is None:
                raise CommandError(
                    f"{gateway_code} has no real implementation yet — nothing to test."
                )
            if not o["public_key"] or not o["secret_key"]:
                raise CommandError("--public-key and --secret-key are required to test a gateway.")
            cfg = GatewayConfig(
                gateway=gateway_code, mode=o["mode"].upper(),
                public_key=o["public_key"], secret_key=o["secret_key"],
            )  # deliberately not .save()d - a pure connectivity test
            gateway = impl(cfg)
        else:
            cfg = GatewayConfig.load()
            if cfg.gateway == Gateway.MANUAL:
                raise CommandError("No online gateway is configured (currently: manual only).")
            gateway = get_gateway()
            if not isinstance(gateway, OnlineGateway):
                raise CommandError(
                    f"{cfg.get_gateway_display()} is configured but has no real "
                    "implementation yet — nothing to test."
                )

        try:
            ok, message = gateway.test_connection()
        except NotImplementedError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(message)
        if not ok:
            raise CommandError("Connection test failed.")
        self.stdout.write(self.style.SUCCESS("OK"))
