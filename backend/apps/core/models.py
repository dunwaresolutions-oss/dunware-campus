"""Shared base models."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """Every domain model inherits this: UUID pk + created/updated timestamps."""

    class Meta:
        abstract = True


class SensitiveModel(BaseModel):
    """
    Marker base for models that hold high-sensitivity PII (health, custody,
    identifiers). The audit layer logs *reads* of these, not just writes, and
    the retention jobs treat them with the shortest configured window.
    """

    #: field names on the subclass that must be retained / anonymized carefully.
    PII_FIELDS: tuple[str, ...] = ()
    #: purpose statement per PII field, mirrored into docs/DATA_MODEL.md.
    PII_PURPOSE: dict[str, str] = {}

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteModel(BaseModel):
    """
    Records are not hard-deleted through the app — retention/erasure jobs and
    the explicit admin "erase this person" action are the only paths that
    actually remove data, and they are audited.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, by=None):
        from django.utils import timezone

        self.deleted_at = timezone.now()
        self.deleted_by = by if getattr(by, "pk", None) else None
        self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])

    def restore(self):
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])


class SensitiveSoftDeleteModel(SensitiveModel, SoftDeleteModel):
    """High-sensitivity PII that also needs history-preserving deletes
    (students, health records, observations, documents)."""

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True
