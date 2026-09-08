"""Single source of the Campus build identity.

Surfaced by ``manage support_bundle`` and the optional remote-access status
panel so a technician can tell exactly what a site is running before touching it.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

CAMPUS_VERSION = "0.9.0"


def _git_head(repo: Path) -> str | None:
    head = repo / ".git" / "HEAD"
    if not head.exists():
        return None
    ref = head.read_text(encoding="utf-8", errors="replace").strip()
    if ref.startswith("ref: "):
        target = repo / ".git" / ref[5:]
        if target.exists():
            return target.read_text(encoding="utf-8", errors="replace").strip()[:12]
        return ref[5:]
    return ref[:12]


def build_stamp() -> dict:
    """Version + how this process was built. No secrets, safe to log/ship."""
    frozen = bool(getattr(sys, "frozen", False))
    stamp: dict = {
        "version": CAMPUS_VERSION,
        "frozen": frozen,
        "python": sys.version.split()[0],
    }
    try:
        exe = Path(sys.executable)
        if frozen and exe.exists():
            stamp["exe"] = exe.name
            stamp["exe_built"] = dt.datetime.fromtimestamp(
                exe.stat().st_mtime, tz=dt.UTC
            ).isoformat()
        if not frozen:
            head = _git_head(Path(__file__).resolve().parents[2])
            if head:
                stamp["git"] = head
    except OSError:
        pass
    return stamp
