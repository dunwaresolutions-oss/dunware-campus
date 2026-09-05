# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the frozen Campus backend (Phase 9 packaging).

Build (from the repo root, with backend/.venv activated and
requirements/build.txt installed):

    cd backend
    ..\.venv\Scripts\pyinstaller ..\deploy\campus.spec --distpath ..\dist --workpath ..\build --noconfirm

Produces dist/campus-app/campus-app.exe (onedir) — see campus_app.py for the
`serve` / `manage` entrypoint contract and docs/DEPLOYMENT.md for how
install.ps1 uses it. This directory is never committed (.gitignore: build/,
dist/) — it's a Release asset, same pattern as the bookkeeping-tool installer.

WeasyPrint is bundled as Python code, but its native Cairo/Pango/GObject
libraries are NOT included here — see docs/DEPLOYMENT.md#third-party-binaries.
Report-card generation degrades to HTML on a build lacking them, by design
(apps/grades/services.py PdfEngineUnavailable), so this is a documented
capability gap, not a broken build.
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
    + collect_submodules("django_q")
    + collect_submodules("corsheaders")
    + collect_submodules("rest_framework")
    # Django resolves MIDDLEWARE / STORAGES / AUTHENTICATION_BACKENDS entries
    # as dotted-path *strings* at runtime — static analysis can't trace those,
    # so any package referenced that way needs its submodules collected
    # explicitly, not just the top-level package name. whitenoise is the one
    # this build actually needs it for (settings.base MIDDLEWARE / STORAGES);
    # a frozen `serve` smoke test caught the omission — see
    # docs/PACKAGING.md.
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
    [os.path.join(BACKEND, "campus_app.py")],
    pathex=[BACKEND],
    binaries=[],
    datas=[
        # Django needs the actual template/migration files on disk, not just
        # compiled bytecode, for a few code paths (admin templates, etc.).
        (os.path.join(BACKEND, "apps"), "apps"),
        (os.path.join(BACKEND, "config"), "config"),
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
    name="campus-app",
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
    name="campus-app",
)
