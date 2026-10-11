"""C5 -- the sync agent on the school (Campus) side. Builds the bundle
(apps/core/central_export.py) and POSTs it to Central's ingest endpoint
(a separate Django project/database -- apps/central/views.py's IngestView,
see docs/CENTRAL_SYNC_SCOPE.md). Records the outcome on ``SiteConfiguration``;
touches nothing else.

**No automatic schedule calls this yet.** django_q is configured
(``Q_CLUSTER`` in settings) and, as of the "Campus Scheduler" Windows
service (deploy/install.ps1 / repair-campus.ps1, campus-app.exe manage
qcluster), a worker process is now registered and running on every install
-- so a django_q ``Schedule`` row would actually execute, product-wide, for
the first time. What's still missing is the schedule itself: nothing yet
inserts a ``Schedule`` row for ``run_sync_with_retry`` keyed to
``SiteConfiguration.sync_interval_minutes``. That's a separate, feature-level
decision (schedule it unconditionally once linked? only when sync_enabled
flips on? on install or on link_central?) and remains unbuilt. Until then, a
sync only happens when something actually calls ``run_sync()`` -- the
on-demand command below, or the companion's "Sync now" button.
"""
from __future__ import annotations

import dataclasses
import time
from datetime import timedelta

from django.utils import timezone

from apps.core.central_export import build_bundle_bytes
from apps.core.models import SiteConfiguration

# A FULL bundle is forced at least this often even when every sync in
# between was incremental, so Central's copy eventually catches a hard
# delete an incremental bundle's own absence-of-a-row can't prove (the
# plan's own "weekly full reconcile").
FULL_RESYNC_AFTER_DAYS = 7
REQUEST_TIMEOUT_SECONDS = 30


@dataclasses.dataclass
class SyncOutcome:
    ok: bool
    message: str
    kind: str | None = None  # "FULL" | "INCREMENTAL"; None if never attempted (not configured)


def _due_for_full_resync(cfg: SiteConfiguration) -> bool:
    if cfg.last_full_synced_at is None:
        return True
    return timezone.now() - cfg.last_full_synced_at >= timedelta(days=FULL_RESYNC_AFTER_DAYS)


def trusted_ssl_context():
    """httpx's default TLS verification (``verify=True``) checks against its
    own bundled ``certifi`` CA list -- it never consults the OS certificate
    store. Both Campus's and Campus Central's own Caddyfiles default to
    ``tls internal`` (a self-signed, locally-generated cert), and
    install.ps1 / install-central.ps1's ``Trust-CaddyLocalCA`` already
    imports that cert into the Windows machine trust store so a *browser*
    stops warning about it -- but httpx never looked there, so the exact
    same URL that loads fine in a browser failed every sync/test-connection
    call with ``CERTIFICATE_VERIFY_FAILED`` (confirmed live, 2026-10-09, a
    real end-to-end link test between a real Campus and a real Central
    install, both still on self-signed certs -- the default and by far the
    most common real-world case, not a one-off local testing quirk).
    ``truststore`` makes Python's own ``ssl`` module delegate verification
    to the OS-native store instead, closing that gap without disabling
    verification -- the same trust boundary the install scripts already
    establish, not a weaker one."""
    import ssl

    import truststore

    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def run_sync(force_full: bool = False) -> SyncOutcome:
    """One sync attempt: build the bundle, POST it, record the outcome.
    Never raises on a network/HTTP failure -- that's an expected, recorded
    outcome, not a bug -- but does let a genuinely unexpected error (e.g. a
    broken SiteConfiguration row) propagate, same as any other service call
    in this codebase."""
    import httpx

    cfg = SiteConfiguration.load()
    if not cfg.sync_enabled:
        return SyncOutcome(ok=False, message="sync is not enabled on this install")
    if not (cfg.school_id and cfg.central_url and cfg.central_token):
        return SyncOutcome(
            ok=False, message="this install isn't fully linked to a Head Office yet"
        )

    full = force_full or _due_for_full_resync(cfg)
    since = None if full else cfg.last_synced_at
    data, manifest = build_bundle_bytes(cfg.school_id, since)
    kind = manifest["kind"]

    url = cfg.central_url.rstrip("/") + f"/api/central/ingest/{cfg.school_id}/"
    try:
        resp = httpx.post(
            url, content=data, timeout=REQUEST_TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Bearer {cfg.central_token}",
                "Content-Type": "application/gzip",
            },
            verify=trusted_ssl_context(),
        )
    except httpx.HTTPError as e:
        return _record_failure(cfg, kind, f"could not reach {cfg.central_url}: {e}")

    if resp.status_code >= 400:
        return _record_failure(
            cfg, kind, f"Central rejected the bundle ({resp.status_code}): {resp.text[:300]}"
        )

    now = timezone.now()
    cfg.last_synced_at = now
    cfg.last_sync_error = ""
    if full:
        cfg.last_full_synced_at = now
    cfg.save(
        update_fields=["last_synced_at", "last_sync_error", "last_full_synced_at", "updated_at"]
    )
    total_rows = sum(manifest["tables"].values())
    return SyncOutcome(ok=True, message=f"synced ({kind}, {total_rows} rows)", kind=kind)


def _record_failure(cfg: SiteConfiguration, kind: str, message: str) -> SyncOutcome:
    cfg.last_sync_error = message[:2000]
    cfg.save(update_fields=["last_sync_error", "updated_at"])
    return SyncOutcome(ok=False, message=message, kind=kind)


def run_sync_with_retry(force_full: bool = False, max_attempts: int = 3) -> SyncOutcome:
    """Retries a failed attempt with exponential backoff (2s, 4s, ...) --
    for whenever a real scheduled runner exists (see this module's own
    docstring). The on-demand command/button call ``run_sync()`` directly
    instead: blocking an interactive click for up to ~6s of retries on
    failure buys nothing a human can't just click again for themselves."""
    delay = 2
    outcome = run_sync(force_full=force_full)
    attempts = 1
    while not outcome.ok and attempts < max_attempts:
        time.sleep(delay)
        delay *= 2
        outcome = run_sync(force_full=force_full)
        attempts += 1
    return outcome
