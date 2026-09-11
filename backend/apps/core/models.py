"""Shared base models + the single-row school profile."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.storage import document_storage


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


def _school_logo_path(instance, filename: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] or "png").lower()[:5]
    return f"school/logo.{ext}"


class SchoolProfile(BaseModel):
    """The institution's own identity — name, contact details, logo — shown on
    generated documents (report cards, IEPs) and in the console chrome.

    Single row. Not PII (it describes the school, not a person), so a plain
    ``BaseModel``: no read-audit, no encryption. The logo is public branding
    and lives on ordinary media storage, not the encrypted document store.
    """

    name = models.CharField(max_length=200, blank=True)
    legal_name = models.CharField(max_length=200, blank=True)
    motto = models.CharField(max_length=200, blank=True)

    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)  # state / province
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=120, blank=True)

    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    website = models.CharField(max_length=200, blank=True)

    principal_name = models.CharField(max_length=150, blank=True)
    principal_title = models.CharField(max_length=80, blank=True, default="Principal")
    # The one staff account allowed to place a signature on report cards.
    # Assigning this is superadmin-only; uploading the image itself is
    # restricted to this account (or a superadmin) — see SchoolProfileView.
    principal_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    signature = models.ImageField(
        upload_to="school/signatures/%Y/", storage=document_storage,
        blank=True, null=True,
    )

    logo = models.ImageField(upload_to=_school_logo_path, blank=True, null=True)
    report_card_footer = models.TextField(blank=True)

    class Meta:
        db_table = "core_school_profile"
        verbose_name = "school profile"

    def __str__(self) -> str:
        return self.name or "School profile (unset)"

    def save(self, *args, **kwargs):
        if self._state.adding and SchoolProfile.objects.exists():
            raise ValidationError("SchoolProfile is a singleton — edit the existing row.")
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> SchoolProfile:
        obj = cls.objects.first()
        return obj if obj is not None else cls.objects.create()

    @property
    def address_block(self) -> str:
        parts = [
            self.address_line1,
            self.address_line2,
            " ".join(p for p in (self.city, self.region, self.postal_code) if p).strip(),
            self.country,
        ]
        return "\n".join(p for p in parts if p)


class SiteConfiguration(BaseModel):
    """Per-install region / fiscal settings. Single row.

    Set at install and changed by the companion tool (``manage
    set_site_config``); the console can edit it too (superadmin) before any
    invoice exists. ``currency`` locks once an ``Invoice`` exists;
    ``collects_fees`` can't be turned off while an issued unpaid invoice
    exists. Not PII — a plain ``BaseModel``.
    """

    class DeploymentMode(models.TextChoices):
        SINGLE = "SINGLE", "Single institution"
        SCHOOL = "SCHOOL", "School (spoke of a headquarters)"
        HEADQUARTERS = "HEADQUARTERS", "Headquarters"

    country = models.CharField(max_length=2, blank=True)  # ISO-3166 alpha-2
    currency = models.CharField(max_length=3, default="CAD")  # ISO-4217
    locale = models.CharField(max_length=10, blank=True)  # e.g. "en-CA"
    collects_fees = models.BooleanField(default=True)
    deployment_mode = models.CharField(
        max_length=12, choices=DeploymentMode.choices, default=DeploymentMode.SINGLE
    )

    class Meta:
        db_table = "core_site_configuration"
        verbose_name = "site configuration"

    def __str__(self) -> str:
        return f"{self.country or '??'} / {self.currency}"

    def save(self, *args, **kwargs):
        if self._state.adding and SiteConfiguration.objects.exists():
            raise ValidationError("SiteConfiguration is a singleton.")
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> SiteConfiguration:
        obj = cls.objects.first()
        return obj if obj is not None else cls.objects.create()
