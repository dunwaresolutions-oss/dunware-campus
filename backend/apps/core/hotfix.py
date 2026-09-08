"""
Field hotfix overlay — inspection side.

The *activation* of the overlay (prepending ``<install>\\app\\hotfix`` to the
import machinery so a corrected ``.py`` shadows the frozen copy) happens in
``campus_app.py`` before Django is imported. This module is the read-only view
of it, used by ``manage support_bundle``, the ``core.W001`` system check, and
the optional remote-access status panel — so a patched box is never invisible.

A hotfix is a single ``.py`` file placed at its real package path under the
hotfix dir, e.g. ``hotfix\\apps\\grades\\services.py``. Limits: it cannot add a
pip dependency and cannot change a model or migration — those still need a
patched build applied with ``repair-campus.ps1 -RefreshAppFrom``.
"""
from __future__ import annotations

import sys
from pathlib import Path


def hotfix_dir() -> Path:
    """``<install>\\app\\hotfix`` next to the frozen exe; ``backend/hotfix`` in a
    dev checkout (normally absent there)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "hotfix"
    return Path(__file__).resolve().parents[2] / "hotfix"


def active_hotfixes() -> list[str]:
    """Package-relative paths of every ``.py`` currently overlaid, sorted."""
    root = hotfix_dir()
    if not root.is_dir():
        return []
    return sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*.py") if p.is_file()
    )
