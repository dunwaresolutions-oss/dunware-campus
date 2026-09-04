"""
Read-auditing for DRF viewsets.

Mix ``AuditReadMixin`` into any viewset whose model is a ``SensitiveModel``
subclass (or set ``audit_reads = True`` explicitly). Every successful
``retrieve`` records a READ of that one object; every ``list`` records a READ
with the returned id set in ``extra`` (names/ids only — never field values).

Writes are covered by the model signals, so this mixin only touches the read
path.
"""
from __future__ import annotations

from .models import AuditAction
from .registry import is_audited
from .services import record


class AuditReadMixin:
    #: force on/off regardless of registry membership
    audit_reads: bool | None = None

    def _reads_are_audited(self) -> bool:
        if self.audit_reads is not None:
            return self.audit_reads
        model = getattr(getattr(self, "queryset", None), "model", None)
        if model is None:
            try:
                model = self.get_queryset().model
            except Exception:  # noqa: BLE001
                return False
        return is_audited(model)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        if self._reads_are_audited():
            obj = getattr(self, "_audit_obj", None) or self.get_object()
            record(AuditAction.READ, obj, summary=f"viewed {obj._meta.verbose_name}")
        return response

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if self._reads_are_audited():
            model = self.get_queryset().model
            ids = _ids_from_response(response)
            record(
                AuditAction.READ,
                summary=f"listed {model._meta.verbose_name_plural} ({len(ids)})",
                extra={"object_type": f"{model._meta.app_label}.{model._meta.object_name}",
                       "object_ids": ids[:200]},
            )
        return response


def _ids_from_response(response) -> list[str]:
    data = getattr(response, "data", None)
    rows = data.get("results", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [str(r.get("id")) for r in rows if isinstance(r, dict) and "id" in r]
