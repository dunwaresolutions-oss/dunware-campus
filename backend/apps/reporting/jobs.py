"""
Scheduled data-governance jobs (django-q2). Phase 1 provides the entry points
and wiring contract; the record-type rules land with the models in Phase 2.

    retention_sweep()   -> anonymize/purge data past its configured window
    erase_person(id)    -> the admin "erase this person" action, legal-hold aware

Both are append-only from the audit log's point of view: every anonymization,
purge, and erasure writes an ERASE / EXPORT entry recording what was done and
by whom.
"""
from __future__ import annotations

from apps.audit.jobs import audit_retention_sweep


def retention_sweep() -> dict:
    """Top of the nightly governance sweep. Phase 2 adds per-model retention
    (past students, applications, communications); today it runs the audit-log
    anonymization pass so the schedule and monitoring are exercised end to end."""
    result = {"audit": audit_retention_sweep()}
    # Phase 2: result["students"] = anonymize_expired_students()
    # Phase 2: result["applications"] = purge_stale_applications()
    return result


def erase_person(person_id: str, *, requested_by=None, reason: str = "") -> dict:
    """Placeholder for the DSAR erasure action (Phase 2, once People exists)."""
    raise NotImplementedError("erase_person lands in Phase 2 with the People model")
