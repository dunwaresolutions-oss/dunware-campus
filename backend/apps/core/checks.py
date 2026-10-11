"""System checks that surface an unusual runtime state in `check` output (and
therefore in `manage support_bundle`)."""
from __future__ import annotations

import os
import subprocess  # nosec B404 - a fixed, no-argument-from-user system tool call, see below
import sys

from django.core.checks import Warning as CheckWarning
from django.core.checks import register

from apps.core.hotfix import active_hotfixes

_SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
_MANAGE_BDE = os.path.join(_SYSTEM32, "manage-bde.exe")


@register()
def hotfix_overlay_active(app_configs, **kwargs):
    fixes = active_hotfixes()
    if not fixes:
        return []
    return [
        CheckWarning(
            "A field hotfix overlay is active: " + ", ".join(fixes),
            hint="These .py files shadow the frozen build. Fold them into a "
            "proper release and clear <install>\\app\\hotfix once the fix ships.",
            id="core.W001",
        )
    ]


@register()
def disk_encryption_at_rest(app_configs, **kwargs):
    """install.ps1 / install-central.ps1 warn about BitLocker exactly once,
    at setup time -- nothing ever checks again. If a technician disables it
    later (troubleshooting something unrelated) and forgets to turn it back
    on, the box silently holds student/guardian PII (Campus) or synced
    cross-school PII (Central) unencrypted at rest with no further warning,
    forever. This re-checks on every `manage check` (therefore every
    `support_bundle`, and anything else that runs system checks) instead of
    trusting a one-time install-wizard warning to still hold true.

    Frozen installs only -- a dev checkout's own drive encryption status
    says nothing about a real deployment, and this would otherwise run
    unnecessarily (and noisily) in every local dev/test run. Fails silently
    on any error (`manage-bde` missing, non-Windows, no permission, timeout)
    -- an inconclusive check must never become a crash or block the app;
    the install-time PowerShell warning already covers "could not
    determine," this only adds a positive, confirmed "it's OFF" signal.
    """
    if not getattr(sys, "frozen", False):
        return []
    drive = sys.executable[:2]  # "C:" -- same drive the frozen app itself runs from
    try:
        result = subprocess.run(  # noqa: S603 # nosec B603 - fixed argv, absolute exe
            [_MANAGE_BDE, "-status", drive],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0 or not result.stdout:
            return []
        if "protection on" in result.stdout.lower():
            return []
        if "protection off" not in result.stdout.lower():
            return []  # unrecognized output -- inconclusive, not a confirmed OFF
    except (OSError, subprocess.SubprocessError):
        return []
    return [
        CheckWarning(
            f"BitLocker is OFF on drive {drive} -- data at rest (the database, "
            "media, backups) is unencrypted on disk.",
            hint="Turn BitLocker back on for this drive. This box holds real "
            "student/guardian PII.",
            id="core.W002",
        )
    ]
