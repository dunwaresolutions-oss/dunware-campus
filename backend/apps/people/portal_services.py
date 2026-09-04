"""
Portal server logic: the consolidated "my world" dashboard for a
parent / student, and applying an approved contact-change request.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Role
from apps.audit.models import AuditAction
from apps.audit.services import record

from .models import ContactChangeRequest, GuardianLink, Student


def submit_contact_change(*, user, guardian, field, proposed_value, reason="",
                          student=None) -> ContactChangeRequest:
    if guardian.user_id != user.pk:
        raise ValidationError("You can only request changes to your own record.")

    link = None
    if field in ContactChangeRequest.LINK_FIELDS:
        if student is None:
            raise ValidationError("A student is required for a per-child setting.")
        link = GuardianLink.objects.filter(guardian=guardian, student=student).first()
        if link is None:
            raise ValidationError("You are not linked to that student.")
        current = str(getattr(link, field))
    elif field in ContactChangeRequest.GUARDIAN_FIELDS:
        current = str(getattr(guardian, field) or "")
    else:
        raise ValidationError(f"'{field}' is not a field you can request to change.")

    req = ContactChangeRequest.objects.create(
        requested_by=user, guardian=guardian, guardian_link=link, field=field,
        current_value=current, proposed_value=str(proposed_value), reason=reason[:255],
    )
    record(AuditAction.CREATE, req, summary=f"contact-change requested: {field}", actor=user)
    return req


def _coerce(field: str, raw: str):
    if field in ContactChangeRequest.LINK_FIELDS:
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return raw


def review_contact_change(
    *, req: ContactChangeRequest, approve: bool, by, note=""
) -> ContactChangeRequest:
    if req.status != ContactChangeRequest.Status.PENDING:
        raise ValidationError(f"This request is already {req.status}.")

    req.status = (
        ContactChangeRequest.Status.APPROVED if approve
        else ContactChangeRequest.Status.REJECTED
    )
    req.reviewed_by = by
    req.reviewed_at = timezone.now()
    req.review_note = note[:255]
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])

    if approve:
        value = _coerce(req.field, req.proposed_value)
        if req.target_is_link and req.guardian_link_id:
            setattr(req.guardian_link, req.field, value)
            req.guardian_link.save(update_fields=[req.field, "updated_at"])
            target = req.guardian_link
        else:
            setattr(req.guardian, req.field, value)
            req.guardian.save(update_fields=[req.field, "updated_at"])
            target = req.guardian
        record(AuditAction.UPDATE, target,
               summary=f"contact-change applied: {req.field}", actor=by,
               changed_fields=[req.field])
    record(AuditAction.UPDATE, req,
           summary=f"contact-change {req.status.lower()}", actor=by)
    return req


def _child_block(student: Student):
    from apps.attendance.models import AttendanceRecord
    from apps.booking.models import Booking
    from apps.communication.models import IncidentReport
    from apps.grades.models import ReportCard
    from apps.registration.models import Consent
    from apps.scheduling.models import SessionOccurrence

    now = timezone.now()
    today = timezone.localdate()
    group_ids = list(
        student.enrolments.filter(status="ACTIVE").values_list("group_id", flat=True)
    )
    upcoming_sessions = list(
        SessionOccurrence.objects.filter(
            group_id__in=group_ids, date__gte=today, status="SCHEDULED"
        ).order_by("date", "start_time")[:5].values("id", "group_id", "date",
                                                    "start_time", "end_time", "title")
    )
    attendance = list(
        AttendanceRecord.objects.filter(student=student).order_by("-date")[:5]
        .values("id", "date", "status", "checked_in_at", "checked_out_at")
    )
    report_cards = list(
        ReportCard.objects.alive().filter(student=student, status="RELEASED")
        .order_by("-released_at").values("id", "term_id", "released_at")
    )
    bookings = list(
        Booking.objects.filter(
            student=student, status__in=["CONFIRMED", "WAITLISTED"],
            slot__starts_at__gte=now,
        ).select_related("slot", "slot__offering").order_by("slot__starts_at")[:10]
    )
    open_incidents = list(
        IncidentReport.objects.alive().filter(student=student, status="SENT")
        .values("id", "occurred_at", "category")
    )
    given = set(
        Consent.objects.filter(student=student).values_list("kind", flat=True)
    )
    pending_consents = [k for k in Consent.Kind.values if k not in given]

    return {
        "id": str(student.pk),
        "display_name": student.display_name,
        "student_number": student.student_number,
        "primary_group_id": str(student.primary_group_id) if student.primary_group_id else None,
        "upcoming_sessions": [
            {**s, "id": str(s["id"]), "group_id": str(s["group_id"])} for s in upcoming_sessions
        ],
        "recent_attendance": [{**a, "id": str(a["id"])} for a in attendance],
        "released_report_cards": [
            {"id": str(r["id"]), "term_id": str(r["term_id"]), "released_at": r["released_at"]}
            for r in report_cards
        ],
        "upcoming_bookings": [
            {
                "id": str(b.pk), "offering": b.slot.offering.title,
                "starts_at": b.slot.starts_at, "status": b.status,
            }
            for b in bookings
        ],
        "open_incidents": [{**i, "id": str(i["id"])} for i in open_incidents],
        "pending_consents": pending_consents,
    }


def build_dashboard(user) -> dict:
    from apps.communication.models import Announcement, MessageThread

    role = getattr(user, "role", None)
    if role == Role.STUDENT:
        children = list(Student.objects.filter(user=user))
    else:
        children = list(Student.visible_queryset(user))

    announcements = list(
        Announcement.objects.alive().filter(published_at__isnull=False)
        .order_by("-pinned", "-published_at")[:10]
    )
    announcements = [a for a in announcements if a.is_visible_to(user)]

    threads = list(
        MessageThread.objects.filter(participants=user)
        .order_by("-last_message_at", "-created_at")[:20]
    )

    return {
        "children": [_child_block(s) for s in children],
        "announcements": [
            {
                "id": str(a.pk), "title": a.title, "body": a.body,
                "published_at": a.published_at, "pinned": a.pinned,
            }
            for a in announcements
        ],
        "message_threads": [
            {
                "id": str(t.pk), "subject": t.subject, "closed": t.closed,
                "last_message_at": t.last_message_at,
                "message_count": t.messages.count(),
            }
            for t in threads
        ],
        "contact_change_requests": [
            {
                "id": str(r.pk), "field": r.field, "status": r.status,
                "created_at": r.created_at,
            }
            for r in ContactChangeRequest.objects.filter(requested_by=user)[:20]
        ],
        "invoices": [],  # Phase 7 (billing) fills this in — read-only in the portal
    }
