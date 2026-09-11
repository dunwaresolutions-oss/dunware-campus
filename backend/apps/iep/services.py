"""Render an IEP to self-contained HTML (school letterhead + goals + plan)."""
from __future__ import annotations

import html as _html

from django.utils import timezone

from apps.core.branding import LETTERHEAD_CSS, letterhead_html, signature_block_html

from .models import IEP, IEPGoal


def _esc(v) -> str:
    return _html.escape(str(v or ""))


def _p(label: str, value) -> str:
    return f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"


def render_iep_html(iep: IEP) -> str:
    s = iep.student
    goals = list(iep.iepgoals.all())
    accs = list(iep.iepaccommodations.filter(active=True))
    svcs = list(iep.iepservices.all())
    reviews = list(iep.iepreviews.all())
    prog = dict(IEPGoal.Progress.choices)
    area = dict(IEPGoal.Area.choices)

    goal_rows = "".join(
        f"<tr><td>{_esc(area.get(g.area, g.area))}</td>"
        f"<td>{_esc(g.description)}</td>"
        f"<td>{_esc(g.baseline)}</td><td>{_esc(g.target)}</td>"
        f"<td>{_esc(prog.get(g.progress, g.progress))}</td></tr>"
        for g in goals
    ) or '<tr><td colspan="5">No goals recorded.</td></tr>'

    acc_rows = "".join(
        f"<li><b>{_esc(dict(a.Category.choices).get(a.category, a.category))}</b> — "
        f"{_esc(a.description)} <i>({_esc(a.applies_to)})</i></li>"
        for a in accs
    ) or "<li>None recorded.</li>"

    svc_rows = "".join(
        f"<tr><td>{_esc(x.service)}</td><td>{_esc(x.provider)}</td>"
        f"<td>{_esc(x.frequency)}</td><td>{_esc(x.location)}</td></tr>"
        for x in svcs
    ) or '<tr><td colspan="4">None recorded.</td></tr>'

    review_rows = "".join(
        f"<tr><td>{_esc(r.review_date)}</td>"
        f"<td>{_esc(dict(r.Outcome.choices).get(r.outcome, r.outcome))}</td>"
        f"<td>{_esc(r.notes)}</td></tr>"
        for r in reviews
    ) or '<tr><td colspan="3">No reviews recorded.</td></tr>'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Individual Education Plan</title>
<style>
 body{{font-family:Georgia,serif;margin:40px;color:#1c2126}}
 h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:14px;margin:20px 0 6px}}
 .muted{{color:#5b6572;font-size:13px}}
 table{{border-collapse:collapse;width:100%;margin-top:8px;font-size:12px}}
 th,td{{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top}}
 .box{{white-space:pre-wrap;border:1px solid #ccc;padding:10px;margin-top:6px;font-size:12px}}
 ul{{font-size:12px}}
 {LETTERHEAD_CSS}
</style></head><body>
{letterhead_html()}
<h1>Individual Education Plan</h1>
<div class="muted">Generated {timezone.now():%Y-%m-%d}</div>
<table>
 {_p("Student", s.display_name)}
 {_p("Student number", s.student_number)}
 {_p("School year", iep.school_year)}
 {_p("Status", iep.get_status_display())}
 {_p("Primary concern", iep.primary_concern)}
 {_p("Start date", iep.start_date or "—")}
 {_p("Next review", iep.review_date or "—")}
 {_p("Case manager", getattr(iep.case_manager, "get_full_name", lambda: "")() or "—")}
</table>

<h2>Strengths</h2><div class="box">{_esc(iep.strengths)}</div>
<h2>Needs</h2><div class="box">{_esc(iep.needs)}</div>
<h2>Summary</h2><div class="box">{_esc(iep.summary)}</div>

<h2>Goals</h2>
<table><tr><th>Area</th><th>Goal</th><th>Baseline</th><th>Target</th><th>Progress</th></tr>
{goal_rows}</table>

<h2>Accommodations</h2><ul>{acc_rows}</ul>

<h2>Services</h2>
<table><tr><th>Service</th><th>Provider</th><th>Frequency</th><th>Location</th></tr>
{svc_rows}</table>

<h2>Review history</h2>
<table><tr><th>Date</th><th>Outcome</th><th>Notes</th></tr>
{review_rows}</table>

{signature_block_html()}
</body></html>"""
