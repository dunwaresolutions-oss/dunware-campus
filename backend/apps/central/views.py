"""C4 -- the ingest endpoint (server-to-server). C6 -- the console's own
backend: school registry, cross-school search, aggregate dashboards, CSV
export. Every C6 view is a browser session (SessionAuthentication, the DRF
default) with one of apps/central/permissions.py's classes; the ingest view
below is the one deliberate exception.
"""
from __future__ import annotations

import csv
import io

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.central.dashboard import build_dashboard, build_dashboard_by_district
from apps.central.detail import build_guardian_detail, build_student_detail
from apps.central.ingest import IngestError, ingest_bundle
from apps.central.models import DistrictAssignment, School
from apps.central.permissions import (
    CentralStaffAndMFA,
    IndividualRecordAccess,
    MinistryAdminOnly,
)
from apps.central.scoping import schools_visible_to
from apps.central.search import search as search_schools

User = get_user_model()


def _bearer_token(request) -> str:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    prefix = "Bearer "
    return header[len(prefix):] if header.startswith(prefix) else ""


class IngestView(APIView):
    """``POST /api/central/ingest/<school_id>/`` -- body is the raw bytes of
    a `manage central_export` bundle (gzipped tar). Same not-found treatment
    for an unknown AND an inactive school -- neither should be distinguishable
    from the other to whoever is calling with a bad school_id."""

    authentication_classes = []
    permission_classes = []

    def post(self, request, school_id):
        try:
            school = School.objects.get(pk=school_id, active=True)
        except (School.DoesNotExist, ValueError):
            return Response({"detail": "no such school"}, status=404)

        token = _bearer_token(request)
        if not school.verify_token(token):
            return Response({"detail": "invalid or missing sync token"}, status=401)

        try:
            batch = ingest_bundle(school, request.body)
        except IngestError as e:
            return Response({"detail": str(e)}, status=400)

        return Response(
            {
                "batch_id": str(batch.pk),
                "kind": batch.kind,
                "applied": batch.applied,
                "tables": batch.manifest.get("tables", {}),
            },
            status=201,
        )


def _school_payload(school: School) -> dict:
    # Never sync_token_hash -- same "never echoed back" treatment as any
    # other credential in this codebase.
    return {
        "id": str(school.pk),
        "name": school.name,
        "district": school.district,
        "sync_status": school.sync_status,
        "last_synced_at": school.last_synced_at.isoformat() if school.last_synced_at else None,
        "snapshot_schema_version": school.snapshot_schema_version,
        "contact_email": school.contact_email,
        "active": school.active,
    }


class SchoolListCreateView(APIView):
    """``GET`` -- every school visible to this user (scoped by district for
    a DISTRICT_OFFICER). ``POST`` -- register a new school and mint its
    first sync token (MINISTRY_ADMIN only; the plan's "central-register-school"
    action, now reachable from the console too, not just `manage register_school`)."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [MinistryAdminOnly()]
        return [CentralStaffAndMFA()]

    def get(self, request):
        schools = schools_visible_to(request.user).order_by("name")
        record(AuditAction.READ, actor=request.user, summary="listed schools")
        return Response([_school_payload(s) for s in schools])

    def post(self, request):
        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response({"name": "This field is required."}, status=400)
        school = School.objects.create(
            name=name,
            district=str(request.data.get("district", "")).strip(),
            contact_email=str(request.data.get("contact_email", "")).strip(),
        )
        token = school.issue_token()
        record(
            AuditAction.CREATE, school, actor=request.user,
            summary=f"registered school {school.name}",
        )
        return Response({**_school_payload(school), "sync_token": token}, status=201)


class SchoolDetailView(APIView):
    """``GET /api/central/schools/<id>/`` -- same not-found treatment for a
    school outside this user's scope as for one that doesn't exist at all."""

    permission_classes = [CentralStaffAndMFA]

    def get(self, request, school_id):
        school = schools_visible_to(request.user).filter(pk=school_id).first()
        if school is None:
            return Response({"detail": "no such school"}, status=404)
        record(AuditAction.READ, school, actor=request.user, summary="viewed school detail")
        return Response(_school_payload(school))


class RotateSchoolTokenView(APIView):
    """``POST /api/central/schools/<id>/rotate-token/`` -- MINISTRY_ADMIN
    only, same as registering a school in the first place."""

    permission_classes = [MinistryAdminOnly]

    def post(self, request, school_id):
        try:
            school = School.objects.get(pk=school_id)
        except (School.DoesNotExist, ValueError):
            return Response({"detail": "no such school"}, status=404)
        token = school.issue_token()
        record(AuditAction.UPDATE, school, actor=request.user, summary="rotated sync token")
        return Response({**_school_payload(school), "sync_token": token})


class DistrictAssignmentsView(APIView):
    """``GET/POST /api/central/district-assignments/`` -- which district(s)
    a DISTRICT_OFFICER may see (apps.central.scoping.schools_visible_to's
    own source of truth). MINISTRY_ADMIN only, same as registering a school
    or inviting an account -- this directly controls another account's data
    reach. ``GET`` takes a required ``?user_id=`` (there is no "list every
    assignment for every user" surface -- that's the directory + per-user
    lookup, not a flat dump)."""

    permission_classes = [MinistryAdminOnly]

    def get(self, request):
        user_id = request.query_params.get("user_id")
        if not user_id:
            return Response({"user_id": "This field is required."}, status=400)
        rows = DistrictAssignment.objects.filter(user_id=user_id).order_by("district")
        return Response([{"id": str(r.pk), "district": r.district} for r in rows])

    def post(self, request):
        user_id = request.data.get("user_id")
        district = str(request.data.get("district", "")).strip()
        if not user_id or not district:
            return Response({"detail": "user_id and district are both required."}, status=400)
        target = get_object_or_404(User, pk=user_id, role="DISTRICT_OFFICER")
        assignment, created = DistrictAssignment.objects.get_or_create(
            user=target, district=district
        )
        if created:
            record(
                AuditAction.CREATE, assignment, actor=request.user,
                summary=f"assigned {target.username} to district {district!r}",
            )
        return Response(
            {"id": str(assignment.pk), "district": assignment.district},
            status=201 if created else 200,
        )


class DistrictAssignmentDetailView(APIView):
    """``DELETE /api/central/district-assignments/<id>/`` -- remove one
    assignment. MINISTRY_ADMIN only."""

    permission_classes = [MinistryAdminOnly]

    def delete(self, request, assignment_id):
        assignment = get_object_or_404(DistrictAssignment, pk=assignment_id)
        summary = f"removed {assignment.user.username} from district {assignment.district!r}"
        assignment.delete()
        record(AuditAction.DELETE, actor=request.user, summary=summary)
        return Response(status=204)


class SearchView(APIView):
    """``GET /api/central/search/?q=...`` -- individual student/guardian/staff
    records. Never available to MINISTRY_ANALYST (IndividualRecordAccess)."""

    permission_classes = [IndividualRecordAccess]

    def get(self, request):
        query = request.query_params.get("q", "")
        schools = schools_visible_to(request.user)
        results = search_schools(schools, query)
        record(
            AuditAction.READ, actor=request.user,
            summary=f"cross-school search: {query[:100]!r}",
        )
        return Response(results)


class StudentDetailView(APIView):
    """``GET /api/central/students/<id>/`` -- the on-demand "case file" view:
    school, class, attendance, guardians (with contact + relationship),
    consents, report-card status. Never MINISTRY_ANALYST. Assembled entirely
    from data already synced -- nothing is fetched live from a school."""

    permission_classes = [IndividualRecordAccess]

    def get(self, request, student_id):
        schools = schools_visible_to(request.user)
        detail = build_student_detail(schools, student_id)
        if detail is None:
            return Response({"detail": "no such student"}, status=404)
        record(
            AuditAction.READ, actor=request.user,
            summary=f"viewed student case file {student_id}",
        )
        return Response(detail)


class GuardianDetailView(APIView):
    """``GET /api/central/guardians/<id>/`` -- a guardian's contact info and
    every child of theirs Central has synced, across however many schools
    this user can see. Never MINISTRY_ANALYST."""

    permission_classes = [IndividualRecordAccess]

    def get(self, request, guardian_id):
        schools = schools_visible_to(request.user)
        detail = build_guardian_detail(schools, guardian_id)
        if detail is None:
            return Response({"detail": "no such guardian"}, status=404)
        record(
            AuditAction.READ, actor=request.user,
            summary=f"viewed guardian case file {guardian_id}",
        )
        return Response(detail)


class DashboardView(APIView):
    """``GET /api/central/dashboard/`` -- aggregate figures only (enrolment,
    attendance %, consent compliance %, incidents by category), safe for
    MINISTRY_ANALYST too. ``?school_id=`` narrows to one school;
    ``?group_by=district`` returns one row per district instead of one total."""

    permission_classes = [CentralStaffAndMFA]

    def get(self, request):
        schools = schools_visible_to(request.user)
        school_id = request.query_params.get("school_id")
        if school_id:
            schools = schools.filter(pk=school_id)

        if request.query_params.get("group_by") == "district":
            data = {"by_district": build_dashboard_by_district(schools)}
        else:
            data = build_dashboard(schools)

        record(AuditAction.READ, actor=request.user, summary="viewed dashboard")
        return Response(data)


class DashboardExportView(APIView):
    """``GET /api/central/dashboard/export.csv`` -- the same figures as
    DashboardView, as CSV. PDF export is not built this pass (see
    docs/CENTRAL_SYNC_SCOPE.md's C6 note) -- it belongs with the console
    frontend, not this backend-only slice."""

    permission_classes = [CentralStaffAndMFA]

    def get(self, request):
        schools = schools_visible_to(request.user)
        school_id = request.query_params.get("school_id")
        if school_id:
            schools = schools.filter(pk=school_id)

        if request.query_params.get("group_by") == "district":
            rows = build_dashboard_by_district(schools)
            fieldnames = [
                "district", "school_count", "enrolment_total", "attendance_pct",
                "consent_compliance_pct", "incidents_by_category",
                "illness_count", "illness_rate_per_100_students",
            ]
        else:
            rows = [build_dashboard(schools)]
            fieldnames = [
                "school_count", "enrolment_total", "attendance_pct",
                "consent_compliance_pct", "incidents_by_category",
                "illness_count", "illness_rate_per_100_students",
            ]

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

        record(AuditAction.EXPORT, actor=request.user, summary="exported dashboard as CSV")
        # Plain HttpResponse, not DRF's Response: a Response still runs the
        # configured renderer pipeline (JSONRenderer by default), which would
        # re-encode this CSV text as a JSON string instead of returning it as is.
        response = HttpResponse(buf.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="central-dashboard.csv"'
        return response
