"""
Email dispatch (email only — no SMS anywhere).

Dev uses the console backend; a real install points EMAIL_* at the operator's
on-site SMTP. Every send is logged to `OutboundEmail` — subject, recipients,
and what it was about, never the rendered body — so an operator can prove a
guardian was notified.
"""
from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record

from .models import Announcement, IncidentReport, OutboundEmail


def _guardian_emails_for_student(student, *, only_comms=True):
    links = student.guardian_links.select_related("guardian")
    if only_comms:
        links = links.filter(receives_communications=True)
    return sorted({link.guardian.email for link in links if link.guardian.email})


def _send(kind, subject, body, recipients, *, obj=None, actor=None) -> OutboundEmail:
    log = OutboundEmail(
        kind=kind, subject=subject[:255], to=list(recipients),
        object_type=f"{obj._meta.app_label}.{obj._meta.object_name}" if obj else "",
        object_id=str(getattr(obj, "pk", "")) if obj else "",
    )
    if not recipients:
        log.error = "no recipients"
        log.save()
        return log
    try:
        send_mail(
            subject, body, settings.DEFAULT_FROM_EMAIL, list(recipients),
            fail_silently=False,
        )
        log.sent_at = timezone.now()
    except Exception as exc:  # noqa: BLE001 - surfaced on the log, not raised at the caller
        log.error = str(exc)[:255]
    log.save()
    record(AuditAction.EXPORT, obj, summary=f"email sent: {kind} ({len(recipients)})", actor=actor)
    return log


def send_announcement(announcement: Announcement, *, actor=None) -> OutboundEmail:
    from apps.people.models import Guardian

    if announcement.audience == Announcement.Audience.ALL_STAFF:
        from apps.accounts.models import STAFF_ROLES, User

        recipients = list(
            User.objects.filter(role__in=[r.value for r in STAFF_ROLES], is_active=True)
            .exclude(email="").values_list("email", flat=True)
        )
    elif announcement.audience == Announcement.Audience.GROUP and announcement.group_id:
        recipients = list(
            Guardian.objects.filter(
                links__student__enrolments__group_id=announcement.group_id,
                links__student__enrolments__status="ACTIVE",
                links__receives_communications=True,
            ).exclude(email="").values_list("email", flat=True).distinct()
        )
    else:  # ALL_PARENTS / WHOLE_SITE
        recipients = list(
            Guardian.objects.filter(links__receives_communications=True)
            .exclude(email="").values_list("email", flat=True).distinct()
        )

    log = _send(
        OutboundEmail.Kind.ANNOUNCEMENT,
        f"[Campus] {announcement.title}",
        announcement.body,
        recipients,
        obj=announcement,
        actor=actor,
    )
    announcement.email_sent_at = log.sent_at
    announcement.save(update_fields=["email_sent_at"])
    return log


def notify_incident(incident: IncidentReport, *, actor=None) -> OutboundEmail:
    recipients = _guardian_emails_for_student(incident.student, only_comms=False)
    body = (
        f"An incident report has been filed for your child on "
        f"{incident.occurred_at:%Y-%m-%d %H:%M}. Please sign in to Campus to read it "
        f"and acknowledge that you have seen it."
    )
    log = _send(
        OutboundEmail.Kind.INCIDENT,
        "[Campus] An incident report needs your acknowledgement",
        body,
        recipients,
        obj=incident,
        actor=actor,
    )
    incident.status = IncidentReport.Status.SENT
    incident.guardians_notified_at = timezone.now()
    incident.save(update_fields=["status", "guardians_notified_at"])
    return log
