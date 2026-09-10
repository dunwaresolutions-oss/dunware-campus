"""Build a render context from real models (or sample data) and apply a template.

``build_context`` is the only place that touches the ORM — it flattens each
entity into a plain namespace of display-ready strings, which the token
resolvers in ``tokens.py`` then read.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from django.utils import timezone

from .models import MessageTemplate
from .tokens import render


def _fmt_date(d) -> str:
    if not d:
        return ""
    return f"{d:%B} {d.day}, {d.year}"


def _fmt_time(d) -> str:
    if not isinstance(d, datetime):
        return ""
    h = d.hour % 12 or 12
    return f"{h}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def _fmt_dt(d) -> str:
    if not isinstance(d, datetime):
        return _fmt_date(d)
    return f"{_fmt_date(d)} at {_fmt_time(d)}"


def _student_ns(s) -> SimpleNamespace:
    grp = getattr(s, "primary_group", None)
    return SimpleNamespace(
        full_name=getattr(s, "display_name", ""),
        first_name=getattr(s, "preferred_name", "") or getattr(s, "first_name", ""),
        legal_first_name=getattr(s, "first_name", ""),
        last_name=getattr(s, "last_name", ""),
        number=getattr(s, "student_number", ""),
        class_name=getattr(grp, "name", "") if grp else "",
        pronouns=getattr(s, "pronouns", ""),
        dob=_fmt_date(getattr(s, "date_of_birth", None)),
    )


def _guardian_ns(g) -> SimpleNamespace:
    return SimpleNamespace(
        full_name=f"{getattr(g, 'first_name', '')} {getattr(g, 'last_name', '')}".strip(),
        first_name=getattr(g, "first_name", ""),
        last_name=getattr(g, "last_name", ""),
        email=getattr(g, "email", ""),
        phone=str(getattr(g, "phone", "") or ""),
    )


def _school_ns(p) -> SimpleNamespace:
    addr = " ".join((getattr(p, "address_block", "") or "").split("\n")[:2]).strip()
    return SimpleNamespace(
        name=getattr(p, "name", ""),
        phone=getattr(p, "phone", ""),
        email=getattr(p, "email", ""),
        website=getattr(p, "website", ""),
        address=addr or getattr(p, "address_line1", ""),
        principal=getattr(p, "principal_name", ""),
    )


def _group_ns(grp) -> SimpleNamespace:
    teacher = ""
    lead = getattr(grp, "_lead_name", None)
    if lead is None:
        try:
            from apps.people.models import GroupStaff

            gs = (
                GroupStaff.objects.select_related("user")
                .filter(group=grp, active=True, role=GroupStaff.Role.LEAD)
                .first()
            )
            if gs and gs.user:
                teacher = gs.user.get_full_name() or gs.user.username
        except Exception:  # noqa: BLE001
            teacher = ""
    else:
        teacher = lead
    return SimpleNamespace(name=getattr(grp, "name", ""), teacher=teacher)


def _term_ns(t) -> SimpleNamespace:
    yr = getattr(t, "academic_year", None)
    return SimpleNamespace(name=getattr(t, "name", ""), year=getattr(yr, "name", "") if yr else "")


def build_context(
    *,
    student=None,
    guardian=None,
    school=None,
    group=None,
    term=None,
    event=None,
    incident=None,
    announcement=None,
) -> dict:
    if school is None:
        from apps.core.models import SchoolProfile

        school = SchoolProfile.load()

    ctx: dict = {"today": _fmt_date(timezone.localdate())}
    ctx["school"] = _school_ns(school)
    if student is not None:
        ctx["student"] = _student_ns(student)
        if group is None:
            group = getattr(student, "primary_group", None)
    if guardian is not None:
        ctx["guardian"] = _guardian_ns(guardian)
    if group is not None:
        ctx["group"] = _group_ns(group)
    if term is not None:
        ctx["term"] = _term_ns(term)
    if event is not None:
        ctx["event"] = SimpleNamespace(
            date=_fmt_date(event), time=_fmt_time(event), datetime=_fmt_dt(event)
        )
    if incident is not None:
        ctx["incident"] = SimpleNamespace(
            category=incident.get_category_display()
            if hasattr(incident, "get_category_display")
            else getattr(incident, "category", ""),
            date=_fmt_date(getattr(incident, "occurred_at", None)),
            location=getattr(incident, "location", ""),
        )
    if announcement is not None:
        ctx["announcement"] = SimpleNamespace(
            title=getattr(announcement, "title", ""),
            body=getattr(announcement, "body", ""),
        )
    return ctx


def render_template(template: MessageTemplate, context: dict) -> tuple[str, str]:
    return render(template.subject, context), render(template.body, context)


def get_active(kind: str) -> MessageTemplate | None:
    return (
        MessageTemplate.objects.filter(kind=kind, active=True)
        .order_by("-is_system", "-updated_at")
        .first()
    )


# --------------------------------------------------------------- preview ----

_SAMPLE_STUDENT = SimpleNamespace(
    display_name="Bobby Adams",
    first_name="Robert",
    preferred_name="Bobby",
    last_name="Adams",
    student_number="S-1042",
    pronouns="he/him",
    date_of_birth=date(2016, 8, 9),
    primary_group=SimpleNamespace(name="Grade 3 – Room 7"),
)
_SAMPLE_GUARDIAN = SimpleNamespace(
    first_name="Alex", last_name="Adams",
    email="alex.adams@example.com", phone="(555) 010-4477",
)


def preview_context(kind: str, student_id=None) -> dict:
    """A context for the editor's live preview: a real student when one is
    given or available, otherwise canned sample data."""
    from apps.people.models import Student

    student = guardian = group = term = None
    if student_id:
        student = Student.objects.filter(pk=student_id).first()
    if student is None:
        student = Student.objects.order_by("last_name").first()

    if student is not None:
        link = student.guardian_links.select_related("guardian").first()
        guardian = link.guardian if link else None
        group = student.primary_group
    else:
        student, guardian = _SAMPLE_STUDENT, _SAMPLE_GUARDIAN
        group = _SAMPLE_STUDENT.primary_group

    if guardian is None:
        guardian = _SAMPLE_GUARDIAN

    try:
        from apps.scheduling.models import Term

        term = (
            Term.objects.filter(academic_year__is_current=True).order_by("start_date").first()
            or Term.objects.order_by("-start_date").first()
        )
    except Exception:  # noqa: BLE001
        term = None

    event = timezone.now()
    incident = SimpleNamespace(
        get_category_display=lambda: "Minor injury",
        occurred_at=event,
        location="the playground",
    )
    announcement = SimpleNamespace(
        title="Early dismissal this Friday",
        body="School will close at 12:30 PM on Friday for staff development.",
    )
    return build_context(
        student=student, guardian=guardian, group=group, term=term,
        event=event, incident=incident, announcement=announcement,
    )
