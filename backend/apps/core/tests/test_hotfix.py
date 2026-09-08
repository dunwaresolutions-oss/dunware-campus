"""Field hotfix overlay — inspection helpers and the core.W001 check."""
from __future__ import annotations

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
