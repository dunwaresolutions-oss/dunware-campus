from django.urls import path

from .views import (
    DashboardExportView,
    DashboardView,
    DistrictAssignmentDetailView,
    DistrictAssignmentsView,
    GuardianDetailView,
    IngestView,
    RotateSchoolTokenView,
    SchoolDetailView,
    SchoolListCreateView,
    SearchView,
    StudentDetailView,
)

app_name = "central"

urlpatterns = [
    path("ingest/<uuid:school_id>/", IngestView.as_view(), name="ingest"),
    path("schools/", SchoolListCreateView.as_view(), name="schools"),
    path("schools/<uuid:school_id>/", SchoolDetailView.as_view(), name="school-detail"),
    path(
        "schools/<uuid:school_id>/rotate-token/", RotateSchoolTokenView.as_view(),
        name="school-rotate-token",
    ),
    path("search/", SearchView.as_view(), name="search"),
    path("students/<uuid:student_id>/", StudentDetailView.as_view(), name="student-detail"),
    path("guardians/<uuid:guardian_id>/", GuardianDetailView.as_view(), name="guardian-detail"),
    path(
        "district-assignments/", DistrictAssignmentsView.as_view(),
        name="district-assignments",
    ),
    path(
        "district-assignments/<uuid:assignment_id>/", DistrictAssignmentDetailView.as_view(),
        name="district-assignment-detail",
    ),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/export.csv", DashboardExportView.as_view(), name="dashboard-export-csv"),
]
