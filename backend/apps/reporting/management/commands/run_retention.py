import json

from django.core.management.base import BaseCommand

from apps.reporting.jobs import retention_sweep


class Command(BaseCommand):
    help = "Run the data-governance retention sweep (audit anonymize + past-student erasure)."

    def handle(self, *args, **options):
        result = retention_sweep()
        self.stdout.write(json.dumps(result, indent=2))
