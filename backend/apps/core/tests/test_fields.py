"""EncryptedField round-trip / failure modes (no DB needed — the field hooks
are exercised directly)."""
from __future__ import annotations

import base64

import pytest
from django.test import override_settings

from apps.core.fields import EncryptedCharField, EncryptedTextField

PLAINTEXT = "Peanut and tree-nut allergy; carries an EpiPen"


def _field(cls=EncryptedTextField, name="secret"):
    f = cls()
    f.set_attributes_from_name(name)
    return f


def test_roundtrip_through_db_hooks():
    f = _field()
    token = f.get_prep_value(PLAINTEXT)
    assert token.startswith("cg1:")
    assert "allergy" not in token.lower()
    assert f.from_db_value(token, None, None) == PLAINTEXT


def test_charfield_roundtrip():
    f = _field(EncryptedCharField, "health_card")
    token = f.get_prep_value("1234-567-890-XY")
    assert f.from_db_value(token, None, None) == "1234-567-890-XY"


def test_none_and_blank_pass_through():
    f = _field()
    assert f.get_prep_value(None) is None
    assert f.get_prep_value("") == ""
    assert f.from_db_value(None, None, None) is None
    assert f.from_db_value("", None, None) == ""


def test_ciphertext_is_non_deterministic():
    f = _field()
    assert f.get_prep_value("same") != f.get_prep_value("same")


def test_already_encrypted_value_is_not_double_wrapped():
    f = _field()
    token = f.get_prep_value(PLAINTEXT)
    assert f.get_prep_value(token) == token


def test_tampered_ciphertext_is_rejected():
    f = _field()
    token = f.get_prep_value(PLAINTEXT)
    mutated = bytearray(token.encode("ascii"))
    mutated[12] ^= 0x01  # flip a bit inside the base64 body
    with pytest.raises(ValueError):
        f.from_db_value(mutated.decode("ascii", "ignore"), None, None)


def test_wrong_key_cannot_decrypt():
    f = _field()
    token = f.get_prep_value(PLAINTEXT)
    other_key = base64.b64encode(b"\x02" * 32).decode("ascii")
    with override_settings(FIELD_ENCRYPTION_KEY=other_key):
        with pytest.raises(ValueError):
            _field().from_db_value(token, None, None)
