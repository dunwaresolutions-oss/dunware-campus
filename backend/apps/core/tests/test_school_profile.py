"""SchoolProfile — the singleton, its API, and its use on report cards."""
from __future__ import annotations

import io

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import SchoolProfile

pytestmark = pytest.mark.django_db

URL = "/api/school-profile/"


def _png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_load_creates_one_and_only_one():
    a = SchoolProfile.load()
    b = SchoolProfile.load()
    assert a.pk == b.pk
    assert SchoolProfile.objects.count() == 1
    with pytest.raises(ValidationError):
        SchoolProfile(name="second").save()


def test_get_is_open_to_staff_not_parents(auth_client, staff, parent, api):
    assert auth_client(staff).get(URL).status_code == 200
    assert auth_client(parent).get(URL).status_code == 403
    assert api.get(URL).status_code in (401, 403)


def test_patch_is_admin_only(auth_client, admin_user, staff):
    assert auth_client(staff).patch(URL, {"name": "Nope"}, format="json").status_code == 403
    resp = auth_client(admin_user).patch(URL, {"name": "Oakwood School"}, format="json")
    assert resp.status_code == 200
    assert resp.data["name"] == "Oakwood School"
    assert SchoolProfile.load().name == "Oakwood School"


def test_logo_upload_and_clear(auth_client, admin_user):
    from django.core.files.uploadedfile import SimpleUploadedFile

    up = SimpleUploadedFile("logo.png", _png_bytes(), content_type="image/png")
    resp = auth_client(admin_user).patch(URL, {"logo": up}, format="multipart")
    assert resp.status_code == 200
    assert resp.data["logo_url"]
    assert SchoolProfile.load().logo

    resp = auth_client(admin_user).delete(URL)
    assert resp.status_code == 200
    assert resp.data["logo_url"] is None
    assert not SchoolProfile.load().logo


def test_address_block_joins_present_parts():
    p = SchoolProfile.load()
    p.address_line1 = "1 Elm St"
    p.city, p.region, p.postal_code = "Springfield", "IL", "62704"
    p.country = "USA"
    p.save()
    assert p.address_block == "1 Elm St\nSpringfield IL 62704\nUSA"


def test_report_card_html_uses_the_school_identity(django_user_model):
    from apps.core.branding import letterhead_html

    p = SchoolProfile.load()
    p.name = "Birchwood Academy"
    p.principal_name = "R. Osei"
    p.save()

    html = letterhead_html()
    assert "Birchwood Academy" in html


SIG_URL = "/api/school-profile/signature/"


def test_designating_the_principal_is_superadmin_only(
    auth_client, admin_user, superadmin, make_user
):
    candidate = make_user(username="dana", role="TEACHER")
    resp = auth_client(admin_user).patch(
        URL, {"principal_user": str(candidate.pk)}, format="json"
    )
    assert resp.status_code == 403

    resp = auth_client(superadmin).patch(
        URL, {"principal_user": str(candidate.pk)}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["principal_user_name"]
    assert SchoolProfile.load().principal_user_id == candidate.pk


def test_only_the_designated_principal_may_upload_a_signature(
    auth_client, admin_user, superadmin, make_user
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    principal = make_user(username="principal1", role="TEACHER")
    other = make_user(username="notprincipal", role="TEACHER")
    cfg = SchoolProfile.load()
    cfg.principal_user = principal
    cfg.save()

    up = lambda: SimpleUploadedFile("sig.png", _png_bytes(), content_type="image/png")  # noqa: E731

    # a random admin can't place the signature, even though they can edit
    # everything else on the profile
    assert auth_client(admin_user).patch(
        URL, {"signature": up()}, format="multipart"
    ).status_code == 403
    # another teacher (not the designated principal) can't either
    assert auth_client(other).patch(
        URL, {"signature": up()}, format="multipart"
    ).status_code == 403

    resp = auth_client(principal).patch(URL, {"signature": up()}, format="multipart")
    assert resp.status_code == 200
    assert resp.data["has_signature"] is True
    # a superadmin can act as a fallback (e.g. onboarding, principal turnover)
    assert auth_client(superadmin).patch(
        URL, {"signature": up()}, format="multipart"
    ).status_code == 200


def test_signature_streams_and_only_the_principal_or_superadmin_clears_it(
    auth_client, staff, superadmin, make_user
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    principal = make_user(username="principal2", role="TEACHER")
    cfg = SchoolProfile.load()
    cfg.principal_user = principal
    cfg.save()
    auth_client(principal).patch(
        URL,
        {"signature": SimpleUploadedFile("sig.png", _png_bytes(), content_type="image/png")},
        format="multipart",
    )

    stream = auth_client(staff).get(SIG_URL)
    assert stream.status_code == 200
    assert b"".join(stream.streaming_content).startswith(b"\x89PNG")

    assert auth_client(staff).delete(SIG_URL).status_code == 403
    assert auth_client(principal).delete(SIG_URL).status_code == 204
    assert auth_client(staff).get(SIG_URL).status_code == 404


def test_signature_appears_on_the_generated_signature_block(make_user):
    from django.core.files.base import ContentFile

    from apps.core.branding import signature_block_html, signature_data_uri

    principal = make_user(username="principal3", role="TEACHER")
    cfg = SchoolProfile.load()
    cfg.principal_name = "Dana Whitfield"
    cfg.principal_user = principal
    cfg.signature.save("sig.png", ContentFile(_png_bytes()), save=True)

    assert signature_data_uri(cfg).startswith("data:image/png;base64,")
    assert "<img src=\"data:image/png" in signature_block_html(cfg)
