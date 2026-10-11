"""Mint a fresh sync token for an already-registered school, invalidating
its old one immediately (School.issue_token() overwrites the stored hash).
Shown once, same as register_school.

    manage_central.py rotate_school_token --school-id <uuid>
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.central.models import School


class Command(BaseCommand):
    help = "Rotate a school's sync token (invalidates the old one immediately)."

    def add_arguments(self, parser):
        parser.add_argument("--school-id", required=True)

    def handle(self, *args, **o):
        try:
            school = School.objects.get(pk=o["school_id"])
        except (School.DoesNotExist, ValueError) as e:
            raise CommandError(f"no school with id {o['school_id']!r}: {e}") from e

        token = school.issue_token()
        self.stdout.write(self.style.SUCCESS(f"rotated token for {school.name} ({school.pk})"))
        self.stdout.write(f"new sync token (shown once): {token}")
