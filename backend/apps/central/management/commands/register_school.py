"""Register a new school with this Head Office -- creates the School row and
mints its first sync token. The token is shown ONCE, here, and never again:
only its hash is stored (School.issue_token()). Give the printed school_id
and token to whoever runs that school's own Campus install, for
`manage link_central` there.

    manage_central.py register_school --name "Maple Grove Primary" --district Nassau
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.central.models import School


class Command(BaseCommand):
    help = "Register a new school and mint its first sync token."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--district", default="")
        parser.add_argument("--contact-email", default="")

    def handle(self, *args, **o):
        school = School.objects.create(
            name=o["name"], district=o["district"], contact_email=o["contact_email"],
        )
        token = school.issue_token()
        self.stdout.write(self.style.SUCCESS(f"registered: {school.name} (school_id={school.pk})"))
        self.stdout.write(
            f"sync token (shown once -- give this and the school_id above to the school): {token}"
        )
