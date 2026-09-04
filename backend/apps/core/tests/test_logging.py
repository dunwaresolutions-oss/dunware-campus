"""The log filter must strip PII before anything is emitted."""
from __future__ import annotations

import logging

from apps.core.logging import PIIScrubFilter, _scrub


def test_scrub_removes_email_phone_and_sensitive_kv():
    assert "@" not in _scrub("reach a.parent@example.com about pickup")
    assert "416-555-0199" not in _scrub("call 416-555-0199 now")
    out = _scrub("allergy=peanut password=hunter2 medication=insulin")
    assert "peanut" not in out
    assert "hunter2" not in out
    assert "insulin" not in out


def test_filter_never_raises_and_returns_true():
    f = PIIScrubFilter()
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "email me@example.com", None, None)
    assert f.filter(rec) is True
    assert "me@example.com" not in rec.getMessage()
