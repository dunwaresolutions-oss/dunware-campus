"""The merge-field token registry for message templates.

Templates carry ``[[TOKEN_NAME]]`` placeholders. Every token belongs to one
*entity group* (Student, Guardian, School, …) and knows the single context key
it needs. ``templating.build_context`` normalises real model instances (or
sample data) into plain namespaces so the resolvers here never touch the ORM —
that keeps them trivial and makes the preview path identical to the real one.

"Intelligent" = the palette a template editor shows is filtered to the tokens
that template's *kind* can actually resolve (``KIND_CONTEXT``); an incident
notification offers guardian/incident tokens, a broadcast announcement does not.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    name: str
    group: str
    label: str
    example: str
    needs: str  # context key required, "" = always available
    resolve: Callable[[dict], str]


def _g(key: str, attr: str) -> Callable[[dict], str]:
    return lambda c: str(getattr(c.get(key), attr, "") or "")


# name, group, label, example, needs (context key), attr on the namespace
_SPEC: list[tuple[str, str, str, str, str, str]] = [
    ("STUDENT_FULL_NAME", "Student", "Full name", "Bobby Adams", "student", "full_name"),
    ("STUDENT_FIRST_NAME", "Student", "First name (preferred)", "Bobby", "student", "first_name"),
    ("STUDENT_LEGAL_FIRST_NAME", "Student", "Legal first", "Rob", "student", "legal_first_name"),
    ("STUDENT_LAST_NAME", "Student", "Last name", "Adams", "student", "last_name"),
    ("STUDENT_NUMBER", "Student", "Student number", "S-1042", "student", "number"),
    ("STUDENT_CLASS", "Student", "Class / group", "Grade 3 – Room 7", "student", "class_name"),
    ("STUDENT_PRONOUNS", "Student", "Pronouns", "he/him", "student", "pronouns"),
    ("STUDENT_DOB", "Student", "Date of birth", "August 9, 2016", "student", "dob"),
    ("GUARDIAN_FULL_NAME", "Guardian", "Full name", "Alex Adams", "guardian", "full_name"),
    ("GUARDIAN_FIRST_NAME", "Guardian", "First name", "Alex", "guardian", "first_name"),
    ("GUARDIAN_LAST_NAME", "Guardian", "Last name", "Adams", "guardian", "last_name"),
    ("GUARDIAN_EMAIL", "Guardian", "Email", "alex.adams@example.com", "guardian", "email"),
    ("GUARDIAN_PHONE", "Guardian", "Phone", "(555) 010-4477", "guardian", "phone"),
    ("SCHOOL_NAME", "School", "School name", "Maple Grove Primary School", "school", "name"),
    ("SCHOOL_PHONE", "School", "Main phone", "(519) 555-0142", "school", "phone"),
    ("SCHOOL_ADMIN_NUMBER", "School", "Office number", "(519) 555-0142", "school", "phone"),
    ("SCHOOL_EMAIL", "School", "Office email", "office@maplegrove.example", "school", "email"),
    ("SCHOOL_WEBSITE", "School", "Website", "maplegrove.example", "school", "website"),
    ("SCHOOL_ADDRESS", "School", "Address", "184 Orchard Lane, Riverbend", "school", "address"),
    ("PRINCIPAL_NAME", "School", "Principal", "Dana Whitfield", "school", "principal"),
    ("CLASS_NAME", "Class", "Class / group name", "Grade 3 – Room 7", "group", "name"),
    ("CLASS_TEACHER", "Class", "Class teacher", "Basil Richards", "group", "teacher"),
    ("TERM_NAME", "Term", "Term name", "Term 1 (Sep–Dec)", "term", "name"),
    ("SCHOOL_YEAR", "Term", "Academic year", "2026–2027", "term", "year"),
    ("EVENT_DATE", "Event", "Event date", "September 10, 2026", "event", "date"),
    ("EVENT_TIME", "Event", "Event time", "2:15 PM", "event", "time"),
    ("EVENT_DATETIME", "Event", "Date & time", "Sep 10 at 2:15 PM", "event", "datetime"),
    ("INCIDENT_CATEGORY", "Incident", "Category", "Injury", "incident", "category"),
    ("INCIDENT_DATE", "Incident", "When it happened", "September 10, 2026", "incident", "date"),
    ("INCIDENT_LOCATION", "Incident", "Location", "the playground", "incident", "location"),
    ("ANNOUNCEMENT_TITLE", "Announcement", "Title", "Early dismissal", "announcement", "title"),
    ("ANNOUNCEMENT_BODY", "Announcement", "Body", "School closes at 12:30", "announcement", "body"),
    ("TODAY", "General", "Today's date", "September 10, 2026", "", "@today"),
]

TOKENS: list[Token] = [
    Token(
        name, group, label, example, needs,
        (lambda c: str(c.get("today", ""))) if attr == "@today" else _g(needs, attr),
    )
    for (name, group, label, example, needs, attr) in _SPEC
]

BY_NAME: dict[str, Token] = {t.name: t for t in TOKENS}

# which context keys each template kind can supply (plus "" = always)
KIND_CONTEXT: dict[str, set[str]] = {
    "INCIDENT": {"student", "guardian", "school", "group", "term", "event", "incident"},
    "REPORT_CARD": {"student", "guardian", "school", "group", "term"},
    "ABSENCE": {"student", "guardian", "school", "group", "term", "event"},
    "ANNOUNCEMENT": {"school", "announcement", "group", "event"},
    "GENERAL": {"student", "guardian", "school", "group", "term", "event"},
}

_TOKEN_RE = re.compile(r"\[\[([A-Z0-9_]+)\]\]")


def render(text: str, context: dict) -> str:
    """Substitute every known ``[[TOKEN]]``. Unknown tokens are left visible
    (so a typo is obvious); a known token with no context resolves to ""."""

    def _sub(m: re.Match) -> str:
        tok = BY_NAME.get(m.group(1))
        if tok is None:
            return m.group(0)
        if tok.needs and tok.needs not in context:
            return ""
        try:
            return tok.resolve(context)
        except Exception:  # noqa: BLE001 - a bad resolver must not break a send
            return ""

    return _TOKEN_RE.sub(_sub, text or "")


def available_tokens(kind: str) -> list[dict]:
    """Grouped palette for the editor, filtered to what *kind* can resolve."""
    allowed = KIND_CONTEXT.get(kind, KIND_CONTEXT["GENERAL"]) | {""}
    groups: dict[str, list[dict]] = {}
    for t in TOKENS:
        if t.needs not in allowed:
            continue
        groups.setdefault(t.group, []).append(
            {"name": t.name, "label": t.label, "example": t.example}
        )
    return [{"group": g, "tokens": toks} for g, toks in groups.items()]


def token_names(kind: str) -> list[str]:
    allowed = KIND_CONTEXT.get(kind, KIND_CONTEXT["GENERAL"]) | {""}
    return [t.name for t in TOKENS if t.needs in allowed]
