from django.core.management.base import BaseCommand, CommandError

from apps.people.models import Student
from apps.reporting.services import LegalHoldError, erase_person


class Command(BaseCommand):
    help = "Erase (anonymize in place) a student. Blocked if the student is under legal hold."

    def add_arguments(self, parser):
        parser.add_argument("--student", required=True, help="Student UUID")
        parser.add_argument("--reason", default="", help="Recorded in the audit log")
        parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")

    def handle(self, *args, **options):
        try:
            student = Student.objects.get(pk=options["student"])
        except Student.DoesNotExist as exc:
            raise CommandError(f"no student {options['student']!r}") from exc

        if not options["yes"]:
            confirm = input(f"Irreversibly erase {student}? type 'erase' to confirm: ")
            if confirm.strip().lower() != "erase":
                self.stdout.write("aborted")
                return

        try:
            result = erase_person(student, reason=options["reason"])
        except LegalHoldError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"erased {result['student']}: {result['removed']}"))
