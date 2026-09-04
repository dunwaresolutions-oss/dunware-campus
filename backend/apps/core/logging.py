"""
PII scrubbing for log records.

No child, guardian, or staff PII should ever reach a log file. This filter
redacts anything that looks like an email, a phone number, or a value assigned
to a known-sensitive key name, before the record is emitted. Audit entries
reference object IDs, never values, so they are unaffected.
"""
from __future__ import annotations

import logging
import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\-\s().]{7,}\d)(?!\d)")
_SENSITIVE_KV = re.compile(
    r"(?i)\b(password|token|secret|authorization|allerg\w*|medication|diagnosis|"
    r"condition|custody|sin|ssn|health_?card|dob|birth_?date)\b\s*[:=]\s*\S+"
)
_REDACTED = "[redacted]"


def _scrub(text: str) -> str:
    text = _EMAIL.sub(_REDACTED, text)
    text = _PHONE.sub(_REDACTED, text)
    text = _SENSITIVE_KV.sub(lambda m: f"{m.group(1)}={_REDACTED}", text)
    return text


class PIIScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = _scrub(str(record.msg))
            if record.args:
                record.args = tuple(
                    _scrub(a) if isinstance(a, str) else a for a in record.args
                )
        except Exception:  # noqa: S110 - a logging filter must never raise
            return True
        return True
