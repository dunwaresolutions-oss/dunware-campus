# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the frozen Campus Central backend.

Build (from the repo root, with backend/.venv activated and
requirements/build.txt installed):

    cd backend
    ..\.venv\Scripts\pyinstaller ..\deploy\central.spec --distpath ..\dist --workpath ..\build --noconfirm

Produces dist/central-app/central-app.exe (onedir) — see central_app.py for
the `serve` / `manage` entrypoint contract and docs/PACKAGING.md for how
install-central.ps1 uses it. Mirrors deploy/campus.spec exactly, scoped down
to what Central's own central.settings.base.INSTALLED_APPS actually uses:
no django_q (Central has no scheduled jobs of its own — Q_CLUSTER is a
Campus-only concern), no WeasyPrint/GTK3 (Central renders no PDFs, only the
dashboard's CSV export). This directory is never committed (.gitignore:
build/, dist/).
"""
import os

from PyInstaller.utils.hooks import collect_submodules

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
BACKEND = os.path.join(REPO_ROOT, "backend")

hiddenimports = (
    collect_submodules("apps")
    + collect_submodules("django.contrib.admin")
    + collect_submodules("django.contrib.auth")
    + collect_submodules("django_otp")
    + collect_submodules("axes")
    + collect_submodules("corsheaders")
    + collect_submodules("rest_framework")
    # Same reason as campus.spec: MIDDLEWARE / STORAGES resolve whitenoise as
    # a dotted-path string, invisible to static analysis without this.
    + collect_submodules("whitenoise")
    + [
        "psycopg",
        "psycopg_binary",
        "waitress",
        "environ",
        "argon2",
        "cryptography",
        "qrcode",
        "qrcode.image.svg",
    ]
)

a = Analysis(
    [os.path.join(BACKEND, "central_app.py")],
    pathex=[BACKEND],
    binaries=[],
    datas=[
        # apps/ is shared with Campus (apps.core/accounts/audit/central) —
        # same reuse-without-recoupling reasoning as everywhere else this
        # project reuses Campus's generic apps; central/ is Central's own
        # settings/urls/wsgi/asgi package, the equivalent of Campus's config/.
        (os.path.join(BACKEND, "apps"), "apps"),
        (os.path.join(BACKEND, "central"), "central"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pyinstaller", "tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="central-app",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=os.path.join(REPO_ROOT, "deploy", "campus.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="central-app",
)
