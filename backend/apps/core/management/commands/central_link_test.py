"""Test reachability of a Campus Central install -- either this install's
saved link, or (via the override flag) a URL that hasn't been saved yet. The
companion GUI's "Test connection" button always passes --central-url
explicitly, so it tests exactly what's in the form -- same convention as
`payments_test` / campus-payments-setup-ui.ps1. Writes nothing: a pure
connectivity check.

    campus-app.exe manage central_link_test
    campus-app.exe manage central_link_test --central-url https://hq.example.gov.bs
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.central_sync import trusted_ssl_context
from apps.core.models import SiteConfiguration

# Central's root urlconf (central/urls.py) registers this at the API root
# (``api_patterns``), NOT under apps.central's own ``/central/`` prefix --
# confirmed by reading apps/central/urls.py, which has no health route at
# all. An earlier version of this command pointed at the wrong path
# (/api/central/health/, which 404s on every real Central), written back
# when C4 hadn't landed yet and the real path wasn't known -- found and
# fixed 2026-10-09 during a real end-to-end link test.
HEALTH_PATH = "/api/healthz/"


class Command(BaseCommand):
    help = "Test reachability of a Campus Central install (saved link, or an override URL)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--central-url", default=None,
            help="Test this URL directly instead of the saved link -- nothing is written.",
        )

    def handle(self, *args, **o):
        import httpx

        url = o["central_url"]
        if not url:
            cfg = SiteConfiguration.load()
            if not cfg.central_url:
                raise CommandError(
                    "No Central URL is saved, and none was given with --central-url."
                )
            url = cfg.central_url

        target = url.rstrip("/") + HEALTH_PATH
        try:
            resp = httpx.get(target, timeout=10, verify=trusted_ssl_context())
        except httpx.HTTPError as e:
            raise CommandError(f"could not reach {target}: {e}") from e

        if resp.status_code == 404:
            raise CommandError(
                f"reached a server at {url}, but it doesn't answer as Campus Central "
                "(404 on the health endpoint). Central's ingest API isn't built until "
                "a later phase -- see docs/CENTRAL_SYNC_SCOPE.md."
            )
        if resp.status_code >= 400:
            raise CommandError(f"{target} returned {resp.status_code}.")
        self.stdout.write(self.style.SUCCESS(f"reached {target} (HTTP {resp.status_code})."))
