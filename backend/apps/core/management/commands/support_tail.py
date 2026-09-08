"""
Show the tail of a Campus service log without needing to know where it lives.

    campus-app.exe manage support_tail app            # last 200 lines of Campus App
    campus-app.exe manage support_tail proxy -n 500
    campus-app.exe manage support_tail db

Aliases: app | proxy | db | remote. For a live follow, use PowerShell:
    Get-Content C:\\ProgramData\\Campus\\logs\\Campus-App.log -Wait -Tail 40
"""
from __future__ import annotations

import io

from django.core.management.base import BaseCommand, CommandError

from apps.core.support import LOG_ALIASES, logs_dir


class Command(BaseCommand):
    help = "Print the tail of a Campus service log (aliases: app, proxy, db, remote)."

    def add_arguments(self, parser):
        parser.add_argument("which", choices=sorted(LOG_ALIASES), help="Which log.")
        parser.add_argument("-n", "--lines", type=int, default=200, help="Lines to show.")

    def handle(self, *args, **opts):
        d = logs_dir()
        if d is None:
            raise CommandError("no logs directory found (is this a packaged install?)")
        path = d / LOG_ALIASES[opts["which"]]
        if not path.exists():
            raise CommandError(f"{path} does not exist — service may never have started")

        with path.open("rb") as fh:
            try:
                fh.seek(-256 * 1024, io.SEEK_END)
            except OSError:
                fh.seek(0)
            tail = fh.read().decode("utf-8", errors="replace").splitlines()

        self.stdout.write(f"== {path} (last {opts['lines']} of {len(tail)}+ lines) ==")
        for line in tail[-opts["lines"] :]:
            self.stdout.write(line)
