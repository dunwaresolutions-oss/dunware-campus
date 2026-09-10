"""
Report-card generation.

The card is always rendered to self-contained HTML. Converting that to PDF
needs WeasyPrint, which pulls native libraries (Cairo / Pango) that only ship
inside the installer (`requirements/prod.txt`, bundled in Phase 9). So:

* `render_report_card_html(card)`  -> str, always available
* `html_to_pdf(html)`              -> bytes, or raises `PdfEngineUnavailable`
* `generate_report_card(card)`     -> stores a `.pdf` when the engine is present,
  otherwise a `.html` fallback; either way sets `generated_at`.

Both are written through `EncryptedFileSystemStorage`, so the artifact is
encrypted at rest like every other document.
"""
from __future__ import annotations

import html as _html
from io import BytesIO

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.branding import (
    LETTERHEAD_CSS,
    letterhead_html,
    signature_block_html,
)


class PdfEngineUnavailable(RuntimeError):
    """WeasyPrint is not installed in this environment (dev / CI)."""


def _row(label, value):
    return f"<tr><th>{_html.escape(str(label))}</th><td>{_html.escape(str(value or ''))}</td></tr>"


def render_report_card_html(card) -> str:
    s = card.student
    entries = card.entries.all()
    body_rows = "".join(
        f"<tr><td>{_html.escape(e.subject)}</td>"
        f"<td>{'' if e.mark is None else e.mark}</td>"
        f"<td>{'' if e.level is None else e.level}</td>"
        f"<td>{_html.escape(e.comment or '')}</td></tr>"
        for e in entries
    )
    from apps.core.models import SchoolProfile

    profile = SchoolProfile.load()
    footer = _html.escape(profile.report_card_footer or "").replace("\n", "<br>")
    footer_html = f'<div class="footer">{footer}</div>' if footer else ""

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Report card</title>
<style>
 body{{font-family:Georgia,serif;margin:40px;color:#1c2126}}
 h1{{font-size:20px;margin:0 0 4px}} .muted{{color:#5b6572;font-size:13px}}
 table{{border-collapse:collapse;width:100%;margin-top:16px;font-size:13px}}
 th,td{{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top}}
 .summary{{margin-top:18px;white-space:pre-wrap;border:1px solid #ccc;padding:10px}}
 .footer{{margin-top:24px;font-size:11px;color:#5b6572;white-space:pre-line;
   border-top:1px solid #ccc;padding-top:8px}}
 {LETTERHEAD_CSS}
</style></head><body>
{letterhead_html(profile)}
<h1>Report card</h1>
<div class="muted">Generated {timezone.now():%Y-%m-%d}</div>
<table>
 {_row("Student", s.display_name)}
 {_row("Student number", s.student_number)}
 {_row("Term", card.term)}
 {_row("Status", card.get_status_display())}
</table>
<table>
 <tr><th>Subject / learning area</th><th>Mark</th><th>Level</th><th>Comment</th></tr>
 {body_rows or '<tr><td colspan="4">No entries.</td></tr>'}
</table>
<div class="summary"><b>Summary</b>\n{_html.escape(card.summary_narrative or '')}</div>
{signature_block_html(profile)}
{footer_html}
</body></html>"""


def html_to_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML  # noqa: PLC0415 - optional, prod-only dependency
    except Exception as exc:  # noqa: BLE001
        raise PdfEngineUnavailable(
            "WeasyPrint is not available; PDF rendering ships with the installer."
        ) from exc
    buf = BytesIO()
    HTML(string=html).write_pdf(buf)
    return buf.getvalue()


def generate_report_card(card, *, actor=None) -> dict:
    html = render_report_card_html(card)
    try:
        pdf = html_to_pdf(html)
        card.document.save(f"report-card-{card.pk}.pdf", ContentFile(pdf), save=False)
        fmt = "pdf"
    except PdfEngineUnavailable:
        card.document.save(f"report-card-{card.pk}.html", ContentFile(html.encode()), save=False)
        fmt = "html"
    card.generated_at = timezone.now()
    if card.status == card.Status.DRAFT:
        card.status = card.Status.FINALIZED
    card.save()
    record(AuditAction.CREATE, card, summary=f"report card generated ({fmt})", actor=actor)
    return {"format": fmt, "document": card.document.name}


def release_report_card(card, *, actor=None) -> None:
    from apps.communication.models import MessageTemplate, OutboundEmail
    from apps.communication.services import (
        _guardian_emails_for_student,
        _send,
        _send_personalized,
    )
    from apps.communication.templating import build_context, get_active, render_template

    card.status = card.Status.RELEASED
    card.released_at = timezone.now()
    card.save(update_fields=["status", "released_at"])
    record(AuditAction.UPDATE, card, summary="report card released to guardians", actor=actor)

    links = card.student.guardian_links.select_related("guardian").filter(
        receives_communications=True
    )
    guardians = [link.guardian for link in links if link.guardian and link.guardian.email]
    tmpl = get_active(MessageTemplate.Kind.REPORT_CARD)

    if tmpl and guardians:
        items = [
            (
                g.email,
                *render_template(
                    tmpl,
                    build_context(
                        student=card.student, guardian=g,
                        group=card.student.primary_group, term=card.term,
                    ),
                ),
            )
            for g in guardians
        ]
        _send_personalized(OutboundEmail.Kind.REPORT_CARD, items, obj=card, actor=actor)
    else:
        _send(
            OutboundEmail.Kind.REPORT_CARD,
            "[Campus] A report card is now available",
            "A report card has been released. Sign in to Campus to read it.",
            _guardian_emails_for_student(card.student, only_comms=True),
            obj=card,
            actor=actor,
        )
