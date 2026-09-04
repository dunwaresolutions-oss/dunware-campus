"""
Field-level encryption at rest (see docs/PII_SECURITY.md).

Sensitive PII — medical conditions, allergies, medications, action plans,
custody / legal notes, government identifiers — is stored AES-256-GCM
encrypted. The key comes from ``settings.FIELD_ENCRYPTION_KEY`` (32 bytes,
base64), which the installer's first-run wizard generates and stores outside
the database. It is never logged and never in the repo.

Ciphertext layout stored in the DB (base64 of):  nonce(12) || ciphertext || tag(16)
Values decrypt transparently on read; querying by encrypted value is not
supported by design (that is the point).
"""
from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.functional import cached_property

_MAGIC = b"cg1:"  # so we can tell an already-encrypted value from a plaintext one


def _load_key() -> bytes:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not raw:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY is not set. Campus cannot store or read "
            "encrypted PII without it (the installer generates it on first run)."
        )
    try:
        key = base64.b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not valid base64") from exc
    if len(key) != 32:
        raise ImproperlyConfigured(
            f"FIELD_ENCRYPTION_KEY must decode to 32 bytes, got {len(key)}"
        )
    return key


class EncryptedMixin:
    """Transparently AES-GCM encrypt on the way to the DB, decrypt on the way out."""

    @cached_property
    def _aead(self) -> AESGCM:
        return AESGCM(_load_key())

    def _encrypt(self, value: str) -> str:
        nonce = os.urandom(12)
        ct = self._aead.encrypt(nonce, value.encode("utf-8"), None)
        return (_MAGIC + base64.b64encode(nonce + ct)).decode("ascii")

    def _decrypt(self, token: str) -> str:
        blob = base64.b64decode(token.encode("ascii")[len(_MAGIC):])
        nonce, ct = blob[:12], blob[12:]
        try:
            return self._aead.decrypt(nonce, ct, None).decode("utf-8")
        except InvalidTag as exc:  # wrong key, or tampered data
            raise ValueError("Encrypted field failed authentication on decrypt") from exc

    # Django field hooks ---------------------------------------------------
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        if isinstance(value, str) and value.encode("ascii", "ignore").startswith(_MAGIC):
            return value  # already encrypted (e.g. a bulk copy)
        return self._encrypt(str(value))

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        if isinstance(value, str) and value.encode("ascii", "ignore").startswith(_MAGIC):
            return self._decrypt(value)
        return value  # legacy plaintext (e.g. a migration in progress)


class EncryptedTextField(EncryptedMixin, models.TextField):
    """Use for free-text PII: medical notes, action plans, custody arrangements."""


class EncryptedCharField(EncryptedMixin, models.CharField):
    """Use for short PII: a health-card number, an allergen name, an ID."""

    def __init__(self, *args, **kwargs):
        # Ciphertext is ~2.5x the plaintext; give the column headroom.
        kwargs.setdefault("max_length", 512)
        super().__init__(*args, **kwargs)
