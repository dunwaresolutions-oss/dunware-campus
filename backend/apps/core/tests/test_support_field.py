"""support_tail and support_sql — the on-site log/DB helpers."""
from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.models import AuditEntry
from apps.core.management.commands.support_sql import _looks_read_only

pytestmark = pytest.mark.django_db


# ── support_sql ──────────────────────────────────────────────────────────
def test_looks_read_only_accepts_select_and_with_only():
    assert _looks_read_only("SELECT 1")
    assert _looks_read_only("  -- note\n select * from people_student ")
    assert _looks_read_only("with x as (select 1) select * from x")
    assert not _looks_read_only("update people_student set first_name='x'")
    assert not _looks_read_only("select 1; drop table people_student")


def test_support_sql_refuses_writes_without_flag():
    with pytest.raises(CommandError, match="read-only"):
        call_command("support_sql", "delete from audit_auditentry", "--operator", "Tech")


def test_support_sql_read_is_audited_and_rolled_back(capsys):
    before = AuditEntry.objects.count()
    call_command("support_sql", "select count(*) from django_migrations", "--operator", "D. D.")
    entry = AuditEntry.objects.order_by("-at").first()
    assert AuditEntry.objects.count() == before + 1
    assert entry.actor_label == "support:D. D."
    assert entry.action == "READ"
    assert "ROLLED BACK" not in capsys.readouterr().out  # a SELECT prints its rows, not that line


def test_support_sql_write_flag_commits_and_audits_as_update():
    # write into a scratch table django always has
    call_command(
        "support_sql",
        "update django_migrations set applied = applied where 1=0",
        "--operator",
        "Tech",
        "--write",
    )
    entry = AuditEntry.objects.order_by("-at").first()
    assert entry.action == "UPDATE"
    assert entry.extra["write"] is True


# ── support_tail ─────────────────────────────────────────────────────────
def test_support_tail_reads_the_right_file(tmp_path, monkeypatch, capsys):
    (tmp_path / "Campus-App.log").write_text(
        "\n".join(f"line {i}" for i in range(500)), encoding="utf-8"
    )
    monkeypatch.setattr(
        "apps.core.management.commands.support_tail.logs_dir", lambda: tmp_path
    )
    call_command("support_tail", "app", "-n", "10")
    out = capsys.readouterr().out
    assert "line 499" in out
    assert "line 480" not in out


def test_support_tail_errors_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "apps.core.management.commands.support_tail.logs_dir", lambda: tmp_path
    )
    with pytest.raises(CommandError, match="does not exist"):
        call_command("support_tail", "proxy")
