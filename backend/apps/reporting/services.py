"""
Data-subject rights over the people / health / registration data
(see docs/PII_SECURITY.md §3).

- ``data_subject_export(student)`` — everything Campus holds about one child,
  decrypted, as a plain dict. For a lawful access request; the caller is
  responsible for delivery. Writes an EXPORT audit entry.
- ``erase_person(student)`` — anonymize in place (names → "ERASED", encrypted
  fields blanked, health rows deleted), keeping row IDs so history / audit
  references stay intact. Blocked by ``student.legal_hold``. Writes ERASE.

Neither hard-deletes the ``Student`` row: the audit log and any financial
history must still resolve. A true purge is a separate, deliberate DBA action.
"""
from __future__ import annotations

import contextlib

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record


class LegalHoldError(Exception):
    """Raised when erasure is attempted on a student under legal hold."""


def _dt(value):
    return value.isoformat() if value else None


def data_subject_export(student, *, actor=None) -> dict:
    from apps.registration.models import Consent, Enrolment

    guardians = []
    for link in student.guardian_links.select_related("guardian"):
        g = link.guardian
        guardians.append({
            "relationship": link.relationship,
            "is_primary_contact": link.is_primary_contact,
            "has_custody": link.has_custody,
            "name": f"{g.first_name} {g.last_name}".strip(),
            "email": g.email,
            "phone": g.phone,
            "address": g.address,
        })

    health = {
        "profile": None,
        "allergies": [], "conditions": [], "medications": [], "action_plans": [],
    }
    profile = getattr(student, "health_profile", None)
    if profile is not None:
        health["profile"] = {"blood_type": profile.blood_type, "notes": profile.notes}
    for a in student.allergies.all():
        health["allergies"].append(
            {"allergen": a.allergen, "reaction": a.reaction, "severity": a.severity,
             "epipen_required": a.epipen_required}
        )
    for c in student.conditions.all():
        health["conditions"].append(
            {"name": c.name, "details": c.details, "diagnosed_on": _dt(c.diagnosed_on)}
        )
    for m in student.medications.all():
        health["medications"].append(
            {"name": m.name, "dose": m.dose, "schedule": m.schedule, "route": m.route,
             "prn": m.prn, "prescriber": m.prescriber}
        )
    for p in student.actionplans.all():
        health["action_plans"].append(
            {"kind": p.kind, "plan": p.plan, "effective_from": _dt(p.effective_from)}
        )

    payload = {
        "student": {
            "id": str(student.pk),
            "first_name": student.first_name,
            "last_name": student.last_name,
            "preferred_name": student.preferred_name,
            "date_of_birth": _dt(student.date_of_birth),
            "student_number": student.student_number,
            "government_id": student.government_id,
            "custody_notes": student.custody_notes,
            "status": student.status,
        },
        "guardians": guardians,
        "emergency_contacts": [
            {"name": e.name, "relationship": e.relationship, "phone": e.phone,
             "alt_phone": e.alt_phone, "priority": e.priority}
            for e in student.emergency_contacts.all()
        ],
        "authorized_pickups": [
            {"name": ap.name, "relationship": ap.relationship, "phone": ap.phone,
             "active": ap.active}
            for ap in student.authorized_pickups.all()
        ],
        "observations": [
            {"category": o.category, "occurred_at": _dt(o.occurred_at), "body": o.body,
             "visible_to_guardians": o.visible_to_guardians}
            for o in student.observations.all()
        ],
        "documents": [
            {"kind": d.kind, "title": d.title, "uploaded_at": _dt(d.created_at)}
            for d in student.documents.all()
        ],
        "health": health,
        "enrolments": [
            {"group": e.group.name, "start_date": _dt(e.start_date),
             "end_date": _dt(e.end_date), "status": e.status}
            for e in Enrolment.objects.filter(student=student).select_related("group")
        ],
        "consents": [
            {"kind": c.kind, "version": c.version, "granted": c.granted,
             "recorded_at": _dt(c.recorded_at), "granted_by": c.granted_by_name}
            for c in Consent.objects.filter(student=student)
        ],
        "generated_at": timezone.now().isoformat(),
    }
    record(AuditAction.EXPORT, student,
           summary="data-subject access export generated", actor=actor)
    return payload


@transaction.atomic
def erase_person(student, *, actor=None, reason: str = "") -> dict:
    if student.legal_hold:
        raise LegalHoldError(f"Student {student.pk} is under legal hold; erasure blocked.")

    removed = {}

    # Health data: delete outright (it has no independent history value).
    for rel in ("allergies", "conditions", "medications", "actionplans"):
        qs = getattr(student, rel).all()
        removed[rel] = qs.count()
        qs.delete()
    if getattr(student, "health_profile", None) is not None:
        student.health_profile.delete()
        removed["health_profile"] = 1

    # Free-text PII on related rows -> blank.
    student.observations.update(body="")
    student.guardian_links.update(custody_notes="")
    for e in student.emergency_contacts.all():
        e.name, e.phone, e.alt_phone = "ERASED", "", ""
        e.save(update_fields=["name", "phone", "alt_phone", "updated_at"])
    for ap in student.authorized_pickups.all():
        ap.name, ap.phone, ap.active = "ERASED", "", False
        ap.save(update_fields=["name", "phone", "active", "updated_at"])
    for d in student.documents.all():
        with contextlib.suppress(Exception):  # a missing file must not block erasure
            d.file.delete(save=False)
        d.title = "ERASED"
        d.save(update_fields=["title", "updated_at"])

    # The student row itself.
    student.first_name = "ERASED"
    student.last_name = "ERASED"
    student.preferred_name = ""
    student.pronouns = ""
    student.government_id = ""
    student.custody_notes = ""
    student.user = None
    student.anonymized_at = timezone.now()
    if not student.deleted_at:
        student.deleted_at = timezone.now()
    student.save()

    record(AuditAction.ERASE, student,
           summary=f"person erased ({reason or 'no reason given'})", actor=actor,
           extra={"removed": removed})
    return {"student": str(student.pk), "removed": removed}
