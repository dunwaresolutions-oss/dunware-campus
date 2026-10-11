"""C5 -- the sync agent (apps/core/central_sync.py + the central_sync command).
See docs/CENTRAL_SYNC_SCOPE.md for how this fits with C1 (the link) and C2
(the bundle it sends)."""
from __future__ import annotations

import uuid

import httpx
import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.core.central_sync import run_sync, run_sync_with_retry
from apps.core.models import SiteConfiguration

pytestmark = pytest.mark.django_db


class FakeResponse:
    def __init__(self, status_code=201, text=""):
        self.status_code = status_code
        self.text = text


def _linked_cfg(**over):
    cfg = SiteConfiguration.load()
    cfg.deployment_mode = SiteConfiguration.DeploymentMode.SCHOOL
    cfg.school_id = uuid.uuid4()
    cfg.central_url = "https://hq.example.gov.bs"
    cfg.central_token = "sch_abc123"
    cfg.sync_enabled = True
    for k, v in over.items():
        setattr(cfg, k, v)
    cfg.save()
    return cfg


def test_refuses_when_sync_is_not_enabled():
    SiteConfiguration.load()  # defaults: not linked, not enabled
    outcome = run_sync()
    assert outcome.ok is False
    assert "not enabled" in outcome.message


def test_refuses_when_not_fully_linked(monkeypatch):
    cfg = SiteConfiguration.load()
    cfg.sync_enabled = True
    cfg.save()
    outcome = run_sync()
    assert outcome.ok is False
    assert "isn't fully linked" in outcome.message


def test_first_ever_sync_is_full_and_updates_both_timestamps(monkeypatch):
    cfg = _linked_cfg()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(201))

    outcome = run_sync()

    assert outcome.ok is True
    assert outcome.kind == "FULL"
    cfg.refresh_from_db()
    assert cfg.last_synced_at is not None
    assert cfg.last_full_synced_at is not None
    assert cfg.last_sync_error == ""


def test_second_sync_shortly_after_is_incremental(monkeypatch):
    _linked_cfg(last_synced_at=timezone.now(), last_full_synced_at=timezone.now())
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(201))

    outcome = run_sync()

    assert outcome.ok is True
    assert outcome.kind == "INCREMENTAL"


def test_full_resync_forced_after_a_week_even_with_recent_incremental_syncs(monkeypatch):
    stale_full = timezone.now() - timezone.timedelta(days=8)
    cfg = _linked_cfg(last_synced_at=timezone.now(), last_full_synced_at=stale_full)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(201))

    outcome = run_sync()

    assert outcome.kind == "FULL"
    cfg.refresh_from_db()
    assert cfg.last_full_synced_at > stale_full


def test_force_full_overrides_a_recent_full_sync(monkeypatch):
    _linked_cfg(last_synced_at=timezone.now(), last_full_synced_at=timezone.now())
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(201))

    outcome = run_sync(force_full=True)

    assert outcome.kind == "FULL"


def test_sends_the_bearer_token_and_the_right_url(monkeypatch):
    cfg = _linked_cfg()
    captured = {}

    def fake_post(url, content=None, timeout=None, headers=None, verify=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["content"] = content
        return FakeResponse(201)

    monkeypatch.setattr(httpx, "post", fake_post)
    run_sync()

    assert captured["url"] == f"https://hq.example.gov.bs/api/central/ingest/{cfg.school_id}/"
    assert captured["headers"]["Authorization"] == "Bearer sch_abc123"
    assert isinstance(captured["content"], bytes)


def test_network_failure_records_the_error_and_leaves_last_synced_at_alone(monkeypatch):
    cfg = _linked_cfg()

    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", boom)
    outcome = run_sync()

    assert outcome.ok is False
    assert "could not reach" in outcome.message
    cfg.refresh_from_db()
    assert cfg.last_synced_at is None
    assert "refused" in cfg.last_sync_error


def test_central_rejecting_the_bundle_is_recorded_as_an_error(monkeypatch):
    cfg = _linked_cfg()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(400, "bad bundle"))

    outcome = run_sync()

    assert outcome.ok is False
    assert "400" in outcome.message
    cfg.refresh_from_db()
    assert "400" in cfg.last_sync_error


def test_retry_eventually_succeeds_after_transient_failures(monkeypatch):
    _linked_cfg()
    monkeypatch.setattr("time.sleep", lambda *_: None)
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("refused")
        return FakeResponse(201)

    monkeypatch.setattr(httpx, "post", flaky)
    outcome = run_sync_with_retry(max_attempts=3)

    assert outcome.ok is True
    assert calls["n"] == 3


def test_retry_gives_up_after_max_attempts(monkeypatch):
    _linked_cfg()
    monkeypatch.setattr("time.sleep", lambda *_: None)

    def always_fails(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", always_fails)
    outcome = run_sync_with_retry(max_attempts=3)

    assert outcome.ok is False


def test_command_succeeds_and_prints_the_outcome(monkeypatch, capsys):
    _linked_cfg()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(201))

    call_command("central_sync")

    assert "synced" in capsys.readouterr().out


def test_command_raises_on_failure():
    SiteConfiguration.load()  # not enabled
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command("central_sync")


def test_command_full_flag_forces_a_full_export(monkeypatch, capsys):
    # Without --full this would be INCREMENTAL (both timestamps are recent).
    _linked_cfg(last_synced_at=timezone.now(), last_full_synced_at=timezone.now())
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(201))

    call_command("central_sync", "--full")

    assert "FULL" in capsys.readouterr().out
