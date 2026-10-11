"""On-demand trigger for the C5 sync agent -- the same command the
companion's "Sync now" button (campus-central-setup-ui.ps1) shells out to.
No automatic schedule calls this yet -- see apps/core/central_sync.py's own
docstring for why.

    campus-app.exe manage central_sync
    campus-app.exe manage central_sync --full
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.central_sync import run_sync


class Command(BaseCommand):
    help = "Run one Campus Central sync attempt now (build the bundle, send it)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--full", action="store_true", help="Force a full export instead of incremental."
        )

    def handle(self, *args, **o):
        outcome = run_sync(force_full=o["full"])
        if not outcome.ok:
            raise CommandError(outcome.message)
        self.stdout.write(self.style.SUCCESS(outcome.message))
