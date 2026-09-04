import json

from django.core.management.base import BaseCommand, CommandError

from apps.people.models import Student
from apps.reporting.services import data_subject_export


class Command(BaseCommand):
    help = "Print everything Campus holds about one student (data-subject access request)."

    def add_arguments(self, parser):
        parser.add_argument("--student", required=True, help="Student UUID")
        parser.add_argument("--out", help="Write JSON to this file instead of stdout")

    def handle(self, *args, **options):
        try:
            student = Student.objects.get(pk=options["student"])
        except Student.DoesNotExist as exc:
            raise CommandError(f"no student {options['student']!r}") from exc
        payload = json.dumps(data_subject_export(student), indent=2)
        if options.get("out"):
            with open(options["out"], "w", encoding="utf-8") as fh:
                fh.write(payload)
            self.stdout.write(f"wrote {options['out']}")
        else:
            self.stdout.write(payload)
