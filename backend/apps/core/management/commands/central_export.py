"""Build the curated Campus Central sync bundle -- a gzipped tar archive
holding one JSONL file per table plus a manifest. Writes a file; no network,
no connection to Central (that's the sync agent, apps/core/central_sync.py, C5).
See docs/CENTRAL_SYNC_SCOPE.md for the field list and apps/core/central_export.py
for the actual table-building and bundle-assembly logic (unit-tested separately).

    campus-app.exe manage central_export --out snapshot.tar.gz
    campus-app.exe manage central_export --since 2026-10-01T00:00:00 --out snapshot.tar.gz
"""
from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.central_export import build_bundle_bytes
from apps.core.models import SiteConfiguration


class Command(BaseCommand):
    help = "Build the curated Campus Central sync bundle (gzipped tar of JSONL tables + manifest)."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="Path to write the bundle to.")
        parser.add_argument(
            "--since", default=None,
            help="ISO datetime -- only rows changed since then (incremental). Omit for a full "
                 "export.",
        )

    def handle(self, *args, **o):
        cfg = SiteConfiguration.load()
        if not cfg.school_id:
            raise CommandError(
                "This install has no school_id yet -- link it to a Head Office with "
                "`manage link_central` first."
            )

        since = None
        if o["since"]:
            try:
                since = datetime.fromisoformat(o["since"])
            except ValueError as e:
                raise CommandError(f"--since must be an ISO datetime: {e}") from e
            if timezone.is_naive(since):
                since = timezone.make_aware(since)

        data, manifest = build_bundle_bytes(cfg.school_id, since)
        with open(o["out"], "wb") as fh:
            fh.write(data)

        total_rows = sum(manifest["tables"].values())
        self.stdout.write(self.style.SUCCESS(
            f"wrote {o['out']} ({manifest['kind']}, {total_rows} rows across "
            f"{len(manifest['tables'])} tables, hash {manifest['content_hash'][:12]}...)"
        ))
