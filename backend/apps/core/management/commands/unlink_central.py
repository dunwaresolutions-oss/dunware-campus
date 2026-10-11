"""Unlink this install from Campus Central -- clears the link fields and
turns sync off. Does NOT change deployment_mode back to SINGLE (a school that
temporarily unlinks is still, organisationally, a school -- re-link later
with `link_central`, or run `set_site_config --deployment-mode SINGLE`
separately if it's truly leaving the programme).

    campus-app.exe manage unlink_central
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.core.models import SiteConfiguration


class Command(BaseCommand):
    help = "Clear this install's Campus Central link and turn sync off."

    def handle(self, *args, **o):
        cfg = SiteConfiguration.load()
        cfg.school_id = None
        cfg.central_url = ""
        cfg.central_token = ""  # noqa: S105 # nosec B105 - clearing the field, not a real password
        cfg.sync_enabled = False
        cfg.last_sync_error = ""
        cfg.save()
        self.stdout.write(self.style.SUCCESS("unlinked from Campus Central."))
