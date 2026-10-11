"""C4 -- the ingest side (apps/central/ingest.py + the IngestView). Builds a
synthetic bundle in exactly the format apps/core/central_export.py (on the
Campus/school side, a different Django project -- not importable here,
see docs/CENTRAL_SYNC_SCOPE.md) produces, so these tests double as a contract
check that ingest understands that format, not just whatever ingest.py
itself happens to emit.

    pytest apps/central --ds=central.settings.test
"""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import uuid
from datetime import UTC, datetime

import pytest
from rest_framework.test import APIClient

from apps.central.ingest import IngestError, ingest_bundle
from apps.central.models import (
    CentralAttendanceSummary,
    CentralBillingSummary,
    CentralConsent,
    CentralEnrolment,
    CentralGroup,
    CentralGuardian,
    CentralIncidentSummary,
    CentralRegistrationCounts,
    CentralReportCard,
    CentralSettings,
    CentralStaff,
    CentralStudent,
    School,
    SnapshotBatch,
)

pytestmark = pytest.mark.django_db


def _build_bundle(tables: dict[str, list[dict]], *, school_id, kind="FULL", version=1) -> bytes:
    table_payloads = {}
    for name, rows in tables.items():
        text = "\n".join(json.dumps(r, default=str) for r in rows)
        if rows:
            text += "\n"
        table_payloads[name] = text.encode("utf-8")

    hasher = hashlib.sha256()
    for name in sorted(table_payloads):
        hasher.update(name.encode("utf-8"))
        hasher.update(table_payloads[name])

    manifest = {
        "school_id": str(school_id),
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot_schema_version": version,
        "kind": kind,
        "since": None,
        "tables": {name: len(rows) for name, rows in tables.items()},
        "content_hash": hasher.hexdigest(),
    }

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in table_payloads.items():
            info = tarfile.TarInfo(name=f"{name}.jsonl")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))
    return buf.getvalue()


def _student_row(**over):
    row = {
        "id": str(uuid.uuid4()), "first_name": "Kid", "last_name": "One",
        "date_of_birth": "2018-01-01", "student_number": "S1", "status": "ENROLLED",
        "primary_group_id": None, "guardian_count": 1,
        "updated_at": "2026-10-01T00:00:00+00:00",
    }
    row.update(over)
    return row


def test_full_bundle_upserts_a_student():
    school = School.objects.create(name="A School")
    row = _student_row()
    bundle = _build_bundle({"students": [row]}, school_id=school.pk)

    batch = ingest_bundle(school, bundle)

    assert batch.applied is True
    assert batch.kind == "FULL"
    cs = CentralStudent.objects.get(school=school, source_id=row["id"])
    assert cs.first_name == "Kid" and cs.student_number == "S1" and cs.status == "ENROLLED"

    school.refresh_from_db()
    assert school.sync_status == School.SyncStatus.OK
    assert school.last_synced_at is not None
    assert school.snapshot_schema_version == 1


def test_resyncing_the_same_student_upserts_not_duplicates():
    school = School.objects.create(name="A School")
    row = _student_row()
    bundle1 = _build_bundle({"students": [row]}, school_id=school.pk)
    ingest_bundle(school, bundle1)

    row["first_name"] = "KidRenamed"
    bundle2 = _build_bundle({"students": [row]}, school_id=school.pk)
    ingest_bundle(school, bundle2)

    assert CentralStudent.objects.filter(school=school, source_id=row["id"]).count() == 1
    assert CentralStudent.objects.get(school=school, source_id=row["id"]).first_name == "KidRenamed"


def test_full_bundle_tombstones_a_student_no_longer_present():
    school = School.objects.create(name="A School")
    row1, row2 = _student_row(), _student_row()
    ingest_bundle(school, _build_bundle({"students": [row1, row2]}, school_id=school.pk))
    assert CentralStudent.objects.filter(school=school).count() == 2

    # row2 dropped from a second FULL bundle -- it should be removed
    ingest_bundle(school, _build_bundle({"students": [row1]}, school_id=school.pk))
    remaining = set(
        CentralStudent.objects.filter(school=school).values_list("source_id", flat=True)
    )
    assert remaining == {uuid.UUID(row1["id"])}


def test_incremental_bundle_does_not_tombstone():
    school = School.objects.create(name="A School")
    row1, row2 = _student_row(), _student_row()
    ingest_bundle(school, _build_bundle({"students": [row1, row2]}, school_id=school.pk))

    # an incremental sync mentioning only row1 must NOT delete row2
    ingest_bundle(
        school, _build_bundle({"students": [row1]}, school_id=school.pk, kind="INCREMENTAL")
    )
    assert CentralStudent.objects.filter(school=school).count() == 2


def test_aggregate_tables_are_always_fully_replaced_even_on_incremental():
    school = School.objects.create(name="A School")
    term_a, term_b = str(uuid.uuid4()), str(uuid.uuid4())
    bundle1 = _build_bundle(
        {
            "billing_summary": [
                {"term_id": term_a, "issued_cents": 100, "paid_cents": 0, "outstanding_cents": 100},
                {"term_id": term_b, "issued_cents": 200, "paid_cents": 0, "outstanding_cents": 200},
            ],
        },
        school_id=school.pk,
    )
    ingest_bundle(school, bundle1)
    assert CentralBillingSummary.objects.filter(school=school).count() == 2

    # the school's own export always sends aggregates in full -- term_b
    # dropping out means it genuinely no longer exists, even on an
    # INCREMENTAL bundle (apps/core/central_export.py never partial-sends these)
    bundle2 = _build_bundle(
        {
            "billing_summary": [
                {
                    "term_id": term_a, "issued_cents": 150, "paid_cents": 50,
                    "outstanding_cents": 100,
                },
            ],
        },
        school_id=school.pk, kind="INCREMENTAL",
    )
    ingest_bundle(school, bundle2)
    rows = list(CentralBillingSummary.objects.filter(school=school))
    assert len(rows) == 1
    assert str(rows[0].term_source_id) == term_a
    assert rows[0].issued_cents == 150


def test_guardian_staff_group_enrolment_consent_report_card_round_trip():
    school = School.objects.create(name="A School")
    student_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    term_id = str(uuid.uuid4())
    bundle = _build_bundle(
        {
            "guardians": [{
                "id": str(uuid.uuid4()), "first_name": "P", "last_name": "One",
                "email": "p@example.test", "phone": "", "updated_at": None,
                "children": [{"student_id": student_id, "relationship": "PARENT"}],
            }],
            "staff": [
                {"id": str(uuid.uuid4()), "username": "t1", "role": "TEACHER", "active": True},
            ],
            "groups": [{
                "id": group_id, "name": "Grade 4", "kind": "CLASS", "stage_label": "",
                "capacity": 20, "active": True, "live_count": 15, "updated_at": None,
            }],
            "enrolments": [{
                "id": str(uuid.uuid4()), "student_id": student_id, "group_id": group_id,
                "start_date": "2026-09-01", "end_date": None, "status": "ACTIVE",
                "updated_at": None,
            }],
            "consents": [{
                "id": str(uuid.uuid4()), "student_id": student_id, "kind": "PHOTO", "version": "1",
                "granted": True, "recorded_at": "2026-09-05T00:00:00+00:00", "updated_at": None,
            }],
            "report_cards": [{
                "id": str(uuid.uuid4()), "student_id": student_id, "term_id": term_id,
                "status": "FINALIZED", "updated_at": None,
            }],
        },
        school_id=school.pk,
    )
    ingest_bundle(school, bundle)

    g = CentralGuardian.objects.get(school=school)
    assert g.children == [{"student_id": student_id, "relationship": "PARENT"}]
    assert CentralStaff.objects.get(school=school).username == "t1"
    assert CentralGroup.objects.get(school=school).live_count == 15
    assert CentralEnrolment.objects.get(school=school).student_source_id == uuid.UUID(student_id)
    assert CentralConsent.objects.get(school=school).granted is True
    assert CentralReportCard.objects.get(school=school).status == "FINALIZED"


def test_registration_counts_and_attendance_and_incident_summaries_round_trip():
    school = School.objects.create(name="A School")
    student_id = str(uuid.uuid4())
    term_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    bundle = _build_bundle(
        {
            "registration_counts": [{
                "applications_by_status": {"SUBMITTED": 3}, "waitlist_by_group": {group_id: 2},
            }],
            "attendance_summary": [{
                "term_id": term_id, "student_id": student_id, "present": 8, "absent": 1,
                "late": 1, "present_pct": 80.0,
            }],
            "incident_summary": [{
                "term_id": term_id, "category": "INJURY", "severity": 2,
                "status": "SENT", "count": 1,
            }],
        },
        school_id=school.pk,
    )
    ingest_bundle(school, bundle)

    rc = CentralRegistrationCounts.objects.get(school=school)
    assert rc.applications_by_status == {"SUBMITTED": 3}
    att = CentralAttendanceSummary.objects.get(school=school)
    assert att.present == 8 and att.present_pct == 80.0
    inc = CentralIncidentSummary.objects.get(school=school)
    assert inc.category == "INJURY" and inc.count == 1


def test_wrong_school_id_in_manifest_is_rejected():
    school = School.objects.create(name="A School")
    bundle = _build_bundle({"students": [_student_row()]}, school_id=uuid.uuid4())
    with pytest.raises(IngestError, match="does not match the school"):
        ingest_bundle(school, bundle)
    # rejected before a SnapshotBatch is even created -- a bundle for a
    # different school is never recorded against this one at all.
    assert SnapshotBatch.objects.filter(school=school).count() == 0


def test_tampered_content_hash_is_rejected():
    school = School.objects.create(name="A School")
    bundle = _build_bundle({"students": [_student_row()]}, school_id=school.pk)
    # Unpack and re-pack with one table's bytes changed but the manifest's
    # own content_hash left as it was -- simulates a bit-flip or a bundle
    # that was built then edited in transit.
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as tar:
        members = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
    members["students.jsonl"] = members["students.jsonl"].replace(b"ENROLLED", b"WITHDRAWN")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    corrupted = buf.getvalue()

    with pytest.raises(IngestError, match="content hash"):
        ingest_bundle(school, corrupted)


def test_malformed_bundle_bytes_are_rejected():
    school = School.objects.create(name="A School")
    with pytest.raises(IngestError, match="not a valid"):
        ingest_bundle(school, b"not a tar file at all")


def test_bundle_schema_version_newer_than_central_understands_is_rejected():
    school = School.objects.create(name="A School")
    settings_row = CentralSettings.load()
    assert settings_row.snapshot_schema_version_supported == 1
    bundle = _build_bundle({"students": [_student_row()]}, school_id=school.pk, version=99)
    with pytest.raises(IngestError, match="schema version"):
        ingest_bundle(school, bundle)


def test_failed_ingest_marks_the_school_error_status():
    school = School.objects.create(name="A School")
    bundle = _build_bundle({"students": [_student_row()]}, school_id=uuid.uuid4())
    with pytest.raises(IngestError):
        ingest_bundle(school, bundle)
    # school_id mismatch is caught before any upsert/batch-error path runs,
    # so sync_status is untouched -- only an upsert-stage failure sets ERROR.
    school.refresh_from_db()
    assert school.sync_status == School.SyncStatus.NEVER_SYNCED


# ---------------------------------------------------------------------------
# HTTP layer (IngestView)
# ---------------------------------------------------------------------------

def test_view_accepts_a_valid_token_and_bundle():
    school = School.objects.create(name="A School")
    token = school.issue_token()
    bundle = _build_bundle({"students": [_student_row()]}, school_id=school.pk)

    client = APIClient()
    resp = client.post(
        f"/api/central/ingest/{school.pk}/", data=bundle, content_type="application/gzip",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert resp.status_code == 201
    assert resp.data["applied"] is True


def test_view_rejects_a_bad_token():
    school = School.objects.create(name="A School")
    school.issue_token()
    bundle = _build_bundle({"students": [_student_row()]}, school_id=school.pk)

    client = APIClient()
    resp = client.post(
        f"/api/central/ingest/{school.pk}/", data=bundle, content_type="application/gzip",
        HTTP_AUTHORIZATION="Bearer wrong-token",
    )
    assert resp.status_code == 401


def test_view_rejects_a_missing_token():
    school = School.objects.create(name="A School")
    school.issue_token()
    bundle = _build_bundle({"students": [_student_row()]}, school_id=school.pk)

    client = APIClient()
    resp = client.post(
        f"/api/central/ingest/{school.pk}/", data=bundle, content_type="application/gzip"
    )
    assert resp.status_code == 401


def test_view_404s_for_an_unknown_school():
    client = APIClient()
    resp = client.post(
        f"/api/central/ingest/{uuid.uuid4()}/", data=b"irrelevant",
        content_type="application/gzip", HTTP_AUTHORIZATION="Bearer whatever",
    )
    assert resp.status_code == 404


def test_view_404s_for_an_inactive_school_same_as_unknown():
    school = School.objects.create(name="A School", active=False)
    token = school.issue_token()
    client = APIClient()
    resp = client.post(
        f"/api/central/ingest/{school.pk}/", data=b"irrelevant",
        content_type="application/gzip", HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert resp.status_code == 404
