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


def _obj_ref(obj):
    if not obj:
        return "", ""
    return (
        f"{obj._meta.app_label}.{obj._meta.object_name}",
        str(getattr(obj, "pk", "")),
    )


def _send(kind, subject, body, recipients, *, obj=None, actor=None) -> OutboundEmail:
    otype, oid = _obj_ref(obj)
    log = OutboundEmail(
        kind=kind, subject=subject[:255], to=list(recipients),
        object_type=otype, object_id=oid,
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


def _send_personalized(kind, items, *, obj=None, actor=None) -> OutboundEmail:
    """``items``: list of ``(email, subject, body)`` — one email per recipient
    (so ``Dear [[GUARDIAN_FULL_NAME]]`` works). One OutboundEmail row records
    the batch; per-recipient failures land in its ``error``."""
    otype, oid = _obj_ref(obj)
    emails = [e for e, _, _ in items]
    log = OutboundEmail(
        kind=kind, subject=(items[0][1][:255] if items else ""), to=emails,
        object_type=otype, object_id=oid,
    )
    if not items:
        log.error = "no recipients"
        log.save()
        return log
    errors = []
    for email, subject, body in items:
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{email}: {exc}")
    if errors:
        log.error = "; ".join(errors)[:255]
    else:
        log.sent_at = timezone.now()
    log.save()
    record(AuditAction.EXPORT, obj, summary=f"email sent: {kind} ({len(items)})", actor=actor)
    return log


def send_announcement(announcement: Announcement, *, actor=None, event=None) -> OutboundEmail:
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

    from .models import MessageTemplate
    from .templating import build_context, get_active, render_template

    tmpl = get_active(MessageTemplate.Kind.ANNOUNCEMENT)
    if tmpl:
        subject, body = render_template(
            tmpl,
            build_context(announcement=announcement, group=announcement.group, event=event),
        )
    else:
        subject, body = f"[Campus] {announcement.title}", announcement.body

    log = _send(
        OutboundEmail.Kind.ANNOUNCEMENT, subject, body, recipients,
        obj=announcement, actor=actor,
    )
    announcement.email_sent_at = log.sent_at
    announcement.save(update_fields=["email_sent_at"])
    return log


def notify_incident(incident: IncidentReport, *, actor=None) -> OutboundEmail:
    from .models import MessageTemplate
    from .templating import build_context, get_active, render_template

    links = incident.student.guardian_links.select_related("guardian")
    guardians = [link.guardian for link in links if link.guardian and link.guardian.email]
    tmpl = get_active(MessageTemplate.Kind.INCIDENT)

    if tmpl and guardians:
        items = []
        for g in guardians:
            subj, body = render_template(
                tmpl,
                build_context(
                    student=incident.student, guardian=g,
                    group=incident.student.primary_group,
                    event=incident.occurred_at, incident=incident,
                ),
            )
            items.append((g.email, subj, body))
        log = _send_personalized(
            OutboundEmail.Kind.INCIDENT, items, obj=incident, actor=actor
        )
    else:
        body = (
            f"An incident report has been filed for your child on "
            f"{incident.occurred_at:%Y-%m-%d %H:%M}. Please sign in to Campus to read it "
            f"and acknowledge that you have seen it."
        )
        log = _send(
            OutboundEmail.Kind.INCIDENT,
            "[Campus] An incident report needs your acknowledgement",
            body,
            sorted({g.email for g in guardians}),
            obj=incident,
            actor=actor,
        )
    incident.status = IncidentReport.Status.SENT
    incident.guardians_notified_at = timezone.now()
    incident.save(update_fields=["status", "guardians_notified_at"])
    return log


def notify_absence(*, student, event, actor=None, group=None) -> OutboundEmail:
    """Email a student's communications-guardians that they were absent on
    ``event`` (a date/datetime). Renders the active ABSENCE template; no-ops
    to a plain sentence if none is configured. Not auto-wired yet — call it
    from a 'notify guardians' action or a daily job."""
    from .models import MessageTemplate
    from .templating import build_context, get_active, render_template

    links = student.guardian_links.select_related("guardian").filter(
        receives_communications=True
    )
    guardians = [link.guardian for link in links if link.guardian and link.guardian.email]
    tmpl = get_active(MessageTemplate.Kind.ABSENCE)
    group = group or getattr(student, "primary_group", None)

    if tmpl and guardians:
        items = [
            (
                g.email,
                *render_template(
                    tmpl,
                    build_context(student=student, guardian=g, group=group, event=event),
                ),
            )
            for g in guardians
        ]
        return _send_personalized(
            OutboundEmail.Kind.ABSENCE, items, obj=student, actor=actor
        )
    body = f"{student.display_name} was recorded absent on {event:%Y-%m-%d}."
    return _send(
        OutboundEmail.Kind.ABSENCE,
        "[Campus] Absence notification",
        body,
        sorted({g.email for g in guardians}),
        obj=student,
        actor=actor,
    )


def notify_early_dismissal(dismissal, *, actor=None) -> OutboundEmail:
    """Send guardians an announcement for a scheduling.EarlyDismissal. Reuses
    the Announcement pipeline (audience resolution, the ANNOUNCEMENT
    template, the OutboundEmail log) rather than a parallel one -- an early
    dismissal notice is exactly the "school closes early" case that template
    kind's sample content already describes. ``dismissal.date`` is site-wide
    when no group is set, group-only otherwise, matching Closure's model."""
    import datetime as _dt

    when = _dt.datetime.combine(dismissal.date, dismissal.dismissal_time)
    day = f"{dismissal.date:%B} {dismissal.date.day}, {dismissal.date.year}"
    dismiss_at = dismissal.dismissal_time.strftime("%I:%M %p").lstrip("0")
    title = f"Early dismissal — {day}"
    body = f"School will dismiss at {dismiss_at} on {day}. Reason: {dismissal.reason}"

    audience = (
        Announcement.Audience.GROUP if dismissal.group_id else Announcement.Audience.WHOLE_SITE
    )
    announcement = Announcement.objects.create(
        title=title, body=body, audience=audience, group=dismissal.group,
        author=actor, published_at=timezone.now(),
    )
    log = send_announcement(announcement, actor=actor, event=when)
    dismissal.notified_at = timezone.now()
    dismissal.save(update_fields=["notified_at"])
    return log
