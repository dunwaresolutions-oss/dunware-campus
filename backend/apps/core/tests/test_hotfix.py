"""Field hotfix overlay — inspection helpers and the core.W001 check."""
from __future__ import annotations

import subprocess
import sys

from apps.core import checks, hotfix


def test_active_hotfixes_empty_when_dir_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(hotfix, "hotfix_dir", lambda: tmp_path / "nope")
    assert hotfix.active_hotfixes() == []


def test_active_hotfixes_lists_sorted_relative_paths(tmp_path, monkeypatch):
    (tmp_path / "apps" / "grades").mkdir(parents=True)
    (tmp_path / "apps" / "grades" / "services.py").write_text("# fix", encoding="utf-8")
    (tmp_path / "apps" / "core").mkdir(parents=True)
    (tmp_path / "apps" / "core" / "logging.py").write_text("# fix", encoding="utf-8")
    monkeypatch.setattr(hotfix, "hotfix_dir", lambda: tmp_path)
    assert hotfix.active_hotfixes() == [
        "apps/core/logging.py",
        "apps/grades/services.py",
    ]


def test_w001_silent_without_hotfixes(monkeypatch):
    monkeypatch.setattr(checks, "active_hotfixes", lambda: [])
    assert checks.hotfix_overlay_active(None) == []


def test_w001_warns_with_hotfixes(monkeypatch):
    monkeypatch.setattr(checks, "active_hotfixes", lambda: ["apps/grades/services.py"])
    out = checks.hotfix_overlay_active(None)
    assert len(out) == 1
    assert out[0].id == "core.W001"
    assert "apps/grades/services.py" in out[0].msg


# ---------------------------------------------------------------------------
# core.W002 — BitLocker / disk-encryption-at-rest
# ---------------------------------------------------------------------------

def test_w002_silent_when_not_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert checks.disk_encryption_at_rest(None) == []


def _frozen(monkeypatch, exe=r"C:\ProgramData\Campus\app\campus-app.exe"):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", exe)


def test_w002_silent_when_bitlocker_on(monkeypatch):
    _frozen(monkeypatch)
    fake = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Protection Status:    Protection On\n", stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    assert checks.disk_encryption_at_rest(None) == []


def test_w002_warns_when_bitlocker_off(monkeypatch):
    _frozen(monkeypatch)
    fake = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Protection Status:    Protection Off\n", stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    out = checks.disk_encryption_at_rest(None)
    assert len(out) == 1
    assert out[0].id == "core.W002"
    assert "C:" in out[0].msg


def test_w002_silent_on_inconclusive_output(monkeypatch):
    _frozen(monkeypatch)
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="garbage\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    assert checks.disk_encryption_at_rest(None) == []


def test_w002_silent_when_manage_bde_missing(monkeypatch):
    _frozen(monkeypatch)

    def boom(*a, **k):
        raise FileNotFoundError("manage-bde not found")

    monkeypatch.setattr(subprocess, "run", boom)
    assert checks.disk_encryption_at_rest(None) == []


def test_w002_silent_when_command_fails(monkeypatch):
    _frozen(monkeypatch)
    fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="denied")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    assert checks.disk_encryption_at_rest(None) == []


def test_w002_silent_on_timeout(monkeypatch):
    _frozen(monkeypatch)

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="manage-bde", timeout=10)

    monkeypatch.setattr(subprocess, "run", boom)
    assert checks.disk_encryption_at_rest(None) == []
