"""
One search box for the whole staff console.

`GET /api/search/?q=<term>` — staff only, MFA-verified, results scoped to
what the caller may see. Returns grouped hits, each with a `route` the SPA
can navigate to:

    {"query": "...", "groups": [
        {"title": "Students", "items": [
            {"id": "...", "label": "...", "sublabel": "...",
             "route": "/people/?tab=students&focus=..."}
        ]}
    ]}
"""
from __future__ import annotations

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import STAFF_ROLES, Role, User
from apps.core.permissions import MFAVerified
from apps.grades.models import ReportCard
from apps.people.models import Group, GroupStaff, Guardian, Student
from apps.registration.models import Application

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}
_PER_TYPE = 6
_MIN = 2


def _grp(title, items):
    return {"title": title, "items": list(items)}


def _join(*parts):
    return " · ".join(p for p in parts if p)


class SearchView(APIView):
    permission_classes = [IsAuthenticated, MFAVerified]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        role = getattr(request.user, "role", None)
        if role not in STAFF_ROLES or len(q) < _MIN:
            return Response({"query": q, "groups": []})

        is_admin = role in _ADMIN_ROLES
        students = Student.visible_queryset(request.user)
        groups = []

        # ── students ──────────────────────────────────────────────
        s_hits = (
            students.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(preferred_name__icontains=q)
                | Q(student_number__icontains=q)
            )
            .select_related("primary_group")[:_PER_TYPE]
        )
        groups.append(_grp("Students", (
            {
                "id": str(s.pk),
                "label": s.display_name,
                "sublabel": _join(
                    s.student_number,
                    s.primary_group.name if s.primary_group_id else "",
                    s.get_status_display(),
                ),
                "route": f"/people/?tab=students&focus={s.pk}",
            }
            for s in s_hits
        )))

        # ── guardians ─────────────────────────────────────────────
        g_qs = Guardian.objects.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
        if not is_admin:
            g_qs = g_qs.filter(links__student__in=students).distinct()
        g_hits = g_qs.prefetch_related("links__student")[:_PER_TYPE]
        groups.append(_grp("Guardians", (
            {
                "id": str(g.pk),
                "label": f"{g.first_name} {g.last_name}".strip(),
                "sublabel": _join(
                    g.email,
                    ", ".join(link.student.display_name for link in list(g.links.all())[:3]),
                ),
                "route": f"/people/?tab=guardians&focus={g.pk}",
            }
            for g in g_hits
        )))

        # ── staff (admin tier only) ───────────────────────────────
        if is_admin:
            u_hits = User.objects.filter(
                role__in=[r.value for r in STAFF_ROLES]
            ).filter(
                Q(username__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
            )[:_PER_TYPE]
            groups.append(_grp("Staff", (
                {
                    "id": str(u.pk),
                    "label": u.get_full_name() or u.username,
                    "sublabel": _join(u.get_role_display(), u.username),
                    "route": "/staff/?tab=directory",
                }
                for u in u_hits
            )))

        # ── groups (rooms / classes / sections) ───────────────────
        grp_qs = Group.objects.filter(Q(name__icontains=q) | Q(stage_label__icontains=q))
        if not is_admin:
            grp_qs = grp_qs.filter(
                id__in=GroupStaff.objects.filter(
                    user=request.user, active=True
                ).values("group_id")
            )
        groups.append(_grp("Groups", (
            {
                "id": str(gr.pk),
                "label": gr.name,
                "sublabel": _join(gr.stage_label, gr.get_kind_display()),
                "route": "/people/?tab=groups",
            }
            for gr in grp_qs[:_PER_TYPE]
        )))

        # ── report cards (matched via the student) ────────────────
        rc_hits = (
            ReportCard.objects.alive()
            .select_related("student", "term")
            .filter(student__in=students)
            .filter(
                Q(student__first_name__icontains=q)
                | Q(student__last_name__icontains=q)
                | Q(student__student_number__icontains=q)
            )
            .order_by("-created_at")[:_PER_TYPE]
        )
        groups.append(_grp("Report cards", (
            {
                "id": str(r.pk),
                "label": f"{r.student.display_name} — {r.term}",
                "sublabel": r.get_status_display(),
                "route": f"/grades/?tab=reportcards&focus={r.pk}",
            }
            for r in rc_hits
        )))

        # ── applications (admin tier only) ────────────────────────
        if is_admin:
            a_hits = Application.objects.alive().filter(
                Q(child_first_name__icontains=q)
                | Q(child_last_name__icontains=q)
                | Q(applicant_name__icontains=q)
                | Q(applicant_email__icontains=q)
            )[:_PER_TYPE]
            groups.append(_grp("Applications", (
                {
                    "id": str(a.pk),
                    "label": f"{a.child_first_name} {a.child_last_name}".strip(),
                    "sublabel": _join(a.applicant_name, a.get_status_display()),
                    "route": "/registration/?tab=applications",
                }
                for a in a_hits
            )))

        return Response({"query": q, "groups": [g for g in groups if g["items"]]})
