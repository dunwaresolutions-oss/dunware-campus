"""
Encrypted-at-rest file storage (see docs/PII_SECURITY.md §1).

Uploaded documents — birth certificates, custody orders, immunization records,
IEPs — are written to disk AES-256-GCM encrypted with the same
``FIELD_ENCRYPTION_KEY`` used for encrypted model fields. The plaintext never
touches the filesystem; ``open()`` decrypts on the way out.

On-disk layout per file:  MAGIC(4) || nonce(12) || ciphertext || tag(16)

This is a belt on top of the braces: the installer also puts %ProgramData%\\Campus
on a BitLocker volume (Phase 9). Either alone would protect a stolen disk; both
means a misconfigured volume still doesn't leak documents.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

_MAGIC = b"cf1:"


def _key() -> bytes:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not raw:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY is not set — encrypted document storage needs it."
        )
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY must decode to 32 bytes.")
    return key


class EncryptedFileSystemStorage(FileSystemStorage):
    """FileSystemStorage that transparently encrypts content on save and
    decrypts on open. Size/exists/delete/url behave as normal."""

    def _encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(12)
        ct = AESGCM(_key()).encrypt(nonce, data, None)
        return _MAGIC + nonce + ct

    def _decrypt(self, blob: bytes) -> bytes:
        if not blob.startswith(_MAGIC):
            return blob  # tolerate a legacy/plaintext file rather than 500
        body = blob[len(_MAGIC):]
        nonce, ct = body[:12], body[12:]
        return AESGCM(_key()).decrypt(nonce, ct, None)

    def _save(self, name, content):
        content.seek(0)
        enc = self._encrypt(content.read())
        return super()._save(name, ContentFile(enc))

    def _open(self, name, mode="rb"):
        if "w" in mode or "a" in mode:  # pragma: no cover - Campus never appends to a stored doc
            raise ValueError("Encrypted documents are write-once; save a new file instead.")
        with super()._open(name, "rb") as fh:
            return ContentFile(self._decrypt(fh.read()), name=os.path.basename(name))


def document_storage() -> EncryptedFileSystemStorage:
    """A callable so migrations serialize a reference, not a bound instance."""
    return EncryptedFileSystemStorage()
