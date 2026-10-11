"""Link this SCHOOL-mode install to a Campus Central head office.

    campus-app.exe manage link_central --central-url https://hq.example.gov.bs \
        --school-id 3fae1b2c-... --token sch_abc123xyz

Requires deployment_mode to already be SCHOOL (set it first with
`set_site_config --deployment-mode SCHOOL`) -- linking doesn't implicitly
change the mode, so a SINGLE install can't be silently turned into a spoke by
this command alone.
"""
from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import SiteConfiguration


class Command(BaseCommand):
    help = "Link this install to a Campus Central head office (SCHOOL mode only)."

    def add_arguments(self, parser):
        parser.add_argument("--central-url", required=True)
        parser.add_argument(
            "--school-id", required=True,
            help="UUID issued by Central when this school was registered there.",
        )
        parser.add_argument("--token", required=True, help="Bearer sync token, minted by Central.")
        parser.add_argument("--sync-interval-minutes", type=int, default=None)

    def handle(self, *args, **o):
        cfg = SiteConfiguration.load()
        if cfg.deployment_mode != SiteConfiguration.DeploymentMode.SCHOOL:
            raise CommandError(
                "This install isn't in SCHOOL mode yet. Run "
                "`manage set_site_config --deployment-mode SCHOOL` first."
            )
        try:
            school_id = uuid.UUID(o["school_id"])
        except ValueError as e:
            raise CommandError(f"--school-id must be a UUID: {e}") from e

        cfg.school_id = school_id
        cfg.central_url = o["central_url"]
        cfg.central_token = o["token"]
        cfg.sync_enabled = True
        cfg.last_sync_error = ""
        if o["sync_interval_minutes"] is not None:
            cfg.sync_interval_minutes = o["sync_interval_minutes"]
        cfg.save()
        self.stdout.write(self.style.SUCCESS(
            f"linked: school_id={cfg.school_id} central_url={cfg.central_url} "
            f"sync_enabled={cfg.sync_enabled} interval={cfg.sync_interval_minutes}min"
        ))
