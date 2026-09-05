import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.accounts.services import bootstrap_superadmin


class Command(BaseCommand):
    help = (
        "Create the first Campus SUPERADMIN. First-run only - refuses if a "
        "superadmin already exists. Reads --password, then "
        "CAMPUS_ADMIN_PASSWORD, then prompts (hidden)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username", help="defaults to $CAMPUS_ADMIN_USER or a prompt"
        )
        parser.add_argument(
            "--email", help="defaults to $CAMPUS_ADMIN_EMAIL or a prompt"
        )
        parser.add_argument(
            "--password",
            help="avoid on shared machines - falls back to "
            "$CAMPUS_ADMIN_PASSWORD or a hidden prompt",
        )

    def handle(self, *args, **options):
        username = (
            options.get("username")
            or os.environ.get("CAMPUS_ADMIN_USER")
            or input("Admin username: ").strip()
        )
        email = (
            options.get("email")
            or os.environ.get("CAMPUS_ADMIN_EMAIL")
            or input("Admin email: ").strip()
        )
        password = options.get("password") or os.environ.get("CAMPUS_ADMIN_PASSWORD")
        if not password:
            password = getpass.getpass(
                "Admin password (min 12 chars, not all digits): "
            )
            if password != getpass.getpass("Confirm password: "):
                raise CommandError("passwords did not match")

        if not username or not email:
            raise CommandError("username and email are both required")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        try:
            user = bootstrap_superadmin(
                username=username, email=email, password=password
            )
        except (ValidationError, DRFValidationError) as exc:
            detail = getattr(exc, "messages", None) or getattr(exc, "detail", exc)
            if isinstance(detail, (list, tuple)):
                detail = "; ".join(str(d) for d in detail)
            raise CommandError(str(detail)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"created superadmin: {user.username} <{user.email}>"
            )
        )
        self.stdout.write(
            "Sign in at your Campus URL and enrol an authenticator app (TOTP) "
            "immediately - staff accounts cannot reach the sensitive screens "
            "until MFA is confirmed."
        )
