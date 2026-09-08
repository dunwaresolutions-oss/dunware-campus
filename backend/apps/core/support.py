"""Shared helpers for the ``manage support_*`` field-troubleshooting commands."""
from __future__ import annotations

import sys
from pathlib import Path

from django.conf import settings

# alias -> the NSSM log file install.ps1 writes for each Windows service
LOG_ALIASES = {
    "app": "Campus-App.log",
    "proxy": "Campus-Proxy.log",
    "db": "Campus-PostgreSQL.log",
    "remote": "Campus-Remote.log",
}


def install_root() -> Path:
    """The directory that holds app/, logs/, media/ — the exe's parent when
    frozen, the ``backend/`` tree in a dev checkout."""
    base = Path(settings.BASE_DIR)
    return base.parent if getattr(sys, "frozen", False) else base


def logs_dir() -> Path | None:
    for d in (install_root() / "logs", Path(settings.BASE_DIR) / "logs"):
        if d.is_dir():
            return d
    return None
