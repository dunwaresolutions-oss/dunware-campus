"""
Check-in / check-out. The check-out authorization rule is the point of this
module: a child is only released to someone on their `AuthorizedPickup` list
or a guardian whose `GuardianLink.can_pickup` is set. Anything else raises
`NotAuthorizedToCollect` and is refused.
"""
from __future__ import annotations

from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.people.models import AuthorizedPickup, GuardianLink

from .models import AttendanceRecord


class NotAuthorizedToCollect(Exception):
    """Raised when a check-out names someone not authorized for this student."""


def check_in(*, student, group, date=None, by=None, dropped_off_by_name="", late=False):
    date = date or timezone.localdate()
    record_obj, _ = AttendanceRecord.objects.get_or_create(
        student=student, group=group, date=date
    )
    record_obj.status = (
        AttendanceRecord.Status.LATE if late else AttendanceRecord.Status.PRESENT
    )
    record_obj.checked_in_at = timezone.now()
    record_obj.checked_in_by = by if getattr(by, "pk", None) else None
    record_obj.dropped_off_by_name = dropped_off_by_name[:150]
    record_obj.save()
    record(AuditAction.UPDATE, record_obj, summary="checked in", actor=by,
           changed_fields=["status", "checked_in_at"])
    return record_obj


def check_out(*, record_obj, by=None, pickup_id=None, guardian_link_id=None):
    student = record_obj.student
    pickup = guardian_link = None
    name = ""

    if pickup_id:
        pickup = AuthorizedPickup.objects.filter(
            pk=pickup_id, student=student, active=True
        ).first()
        if pickup is None:
            raise NotAuthorizedToCollect(
                "That person is not on this student's authorized-pickup list."
            )
        name = pickup.name
    elif guardian_link_id:
        guardian_link = GuardianLink.objects.filter(
            pk=guardian_link_id, student=student, can_pickup=True
        ).select_related("guardian").first()
        if guardian_link is None:
            raise NotAuthorizedToCollect(
                "That guardian is not authorized to collect this student."
            )
        name = str(guardian_link.guardian)
    else:
        raise NotAuthorizedToCollect("A pickup person or guardian must be named for check-out.")

    record_obj.checked_out_at = timezone.now()
    record_obj.checked_out_by = by if getattr(by, "pk", None) else None
    record_obj.collected_by_pickup = pickup
    record_obj.collected_by_guardian = guardian_link
    record_obj.collected_by_name = name
    if record_obj.status == AttendanceRecord.Status.PRESENT:
        record_obj.status = AttendanceRecord.Status.PRESENT
    record_obj.save()
    record(AuditAction.UPDATE, record_obj,
           summary=f"checked out to {name}", actor=by,
           changed_fields=["checked_out_at", "collected_by_name"])
    return record_obj


def mark_absent(*, student, group, date=None, by=None, excused=False, note=""):
    date = date or timezone.localdate()
    record_obj, _ = AttendanceRecord.objects.get_or_create(
        student=student, group=group, date=date
    )
    record_obj.status = (
        AttendanceRecord.Status.EXCUSED if excused else AttendanceRecord.Status.ABSENT
    )
    record_obj.note = note[:255]
    record_obj.save()
    record(AuditAction.UPDATE, record_obj, summary=f"marked {record_obj.status}", actor=by)
    return record_obj
