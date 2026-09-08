"""System checks that surface an unusual runtime state in `check` output (and
therefore in `manage support_bundle`)."""
from __future__ import annotations

from django.core.checks import Warning as CheckWarning
from django.core.checks import register

from apps.core.hotfix import active_hotfixes


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
