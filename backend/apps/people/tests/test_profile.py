"""Student profile-page support: photo upload/stream/clear, adjacent nav,
and the ?student= filters the profile tabs rely on."""
from __future__ import annotations

import io

import pytest

from .factories import enrol, link_guardian, make_group, make_student

pytestmark = pytest.mark.django_db


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (6, 6), (200, 120, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_photo_upload_stream_and_clear(auth_client, front_desk):
    from django.core.files.uploadedfile import SimpleUploadedFile

    kid = make_student()
    c = auth_client(front_desk)

    up = SimpleUploadedFile("face.png", _png(), content_type="image/png")
    r = c.patch(f"/api/students/{kid.id}/", {"photo": up}, format="multipart")
    assert r.status_code == 200
    assert r.data["photo_url"] and r.data["photo_url"].endswith(f"/students/{kid.id}/photo/")

    stream = c.get(f"/api/students/{kid.id}/photo/")
    assert stream.status_code == 200
    assert b"".join(stream.streaming_content).startswith(b"\x89PNG")  # decrypted

    assert c.delete(f"/api/students/{kid.id}/photo/").status_code == 204
    assert c.get(f"/api/students/{kid.id}/photo/").status_code == 404


def test_adjacent_walks_the_visible_list_in_order(auth_client, front_desk):
    a = make_student(last_name="Adams", first_name="Al")
    b = make_student(last_name="Baker", first_name="Bo")
    d = make_student(last_name="Diaz", first_name="Di")
    c = auth_client(front_desk)

    assert c.get(f"/api/students/{b.id}/adjacent/").data == {
        "prev": str(a.id), "next": str(d.id),
    }
    assert c.get(f"/api/students/{a.id}/adjacent/").data["prev"] is None
    assert c.get(f"/api/students/{d.id}/adjacent/").data["next"] is None


def test_student_filters_scope_the_profile_tabs(auth_client, front_desk):
    g = make_group()
    mine, other = make_student(), make_student()
    enrol(mine, g)
    enrol(other, g)
    link_guardian(mine)
    c = auth_client(front_desk)

    e = c.get("/api/enrolments/", {"student": str(mine.id)}).data["results"]
    assert {str(row["student"]) for row in e} == {str(mine.id)}

    gl = c.get("/api/guardian-links/", {"student": str(mine.id)}).data["results"]
    assert gl and all(str(row["student"]) == str(mine.id) for row in gl)
