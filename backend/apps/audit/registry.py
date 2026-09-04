"""
Which models get automatic CRUD auditing.

Two ways in:

* subclass ``apps.core.models.SensitiveModel`` — registered automatically when
  the app registry is ready (these also get *read* auditing via
  ``apps.audit.mixins.AuditReadMixin``);
* call ``register_audited(SomeModel)`` from an app's ``ready()`` for a model
  that is not "sensitive" but is still worth a write trail (e.g. enrolment
  status, fee schedules).

Nothing else is audited at the row level — the log stays signal, not noise.
"""
from __future__ import annotations

from django.db.models import Model

_AUDITED: set[type[Model]] = set()


def register_audited(model: type[Model]) -> type[Model]:
    _AUDITED.add(model)
    return model


def is_audited(model: type[Model]) -> bool:
    return model in _AUDITED


def audited_models() -> frozenset[type[Model]]:
    return frozenset(_AUDITED)


def autodiscover_sensitive_models() -> None:
    """Register every concrete ``SensitiveModel`` subclass. Idempotent."""
    from apps.core.models import SensitiveModel

    for model in _all_concrete_subclasses(SensitiveModel):
        _AUDITED.add(model)


def _all_concrete_subclasses(base):
    for sub in base.__subclasses__():
        if not getattr(sub._meta, "abstract", False):
            yield sub
        yield from _all_concrete_subclasses(sub)
