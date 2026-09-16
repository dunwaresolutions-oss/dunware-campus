"""Ping the configured gateway's auth endpoint with its stored keys -
the companion Payments tab's "Test connection" button (P2), runnable
standalone too.

    campus-app.exe manage payments_test
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.billing.gateways import OnlineGateway, get_gateway
from apps.billing.models import Gateway, GatewayConfig


class Command(BaseCommand):
    help = "Test this install's configured online payment gateway."

    def handle(self, *args, **options):
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
