#!/usr/bin/env python
"""Campus Central's own manage.py-equivalent -- a separate entry point from
manage.py (Campus's own) so there is never any ambiguity about which
project's database a command is about to touch."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "central.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Is it installed and available on your "
            "PYTHONPATH? Did you forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
