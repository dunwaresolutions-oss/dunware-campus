"""
Campus Central frozen entrypoint (PyInstaller — see deploy/central.spec).

This is the *only* script the Central installer / Windows service ever
calls — the Central counterpart of backend/campus_app.py, kept deliberately
separate (not a shared entrypoint with a --project flag) so there is never
any ambiguity about which project's settings module, database, or .env file
a frozen build is about to touch. Two modes, same shape as Campus's own:

    central-app.exe serve [--host H] [--port P]
        Run waitress serving central.wsgi. This is what "Campus Central App"
        (the Windows service, NSSM-registered by deploy/install-central.ps1)
        runs — it never returns until stopped.

    central-app.exe manage <django management command> [args...]
        Proxies straight to manage_central.py's own dispatch. install-
        central.ps1 uses this for `migrate` / `collectstatic`; the operator
        uses it for `register_school` / `rotate_school_token` post-install —
        there is no Python on the target machine to run manage_central.py
        directly.

Always central.settings.prod. Reads <exe dir>\\.env.central (settings/
base.py resolves BASE_DIR from sys.executable when frozen — see the
`sys.frozen` check there). Central has no PDF-rendering feature (unlike
Campus's report cards), so unlike campus_app.py there is no
_ensure_native_pdf_libs() step here — nothing in apps.central uses
WeasyPrint, so no GTK3 runtime needs staging for Central.
"""
from __future__ import annotations

import importlib.util
import multiprocessing
import os
import sys
from pathlib import Path


def _apply_hotfix_overlay() -> None:
    """Identical mechanism to campus_app.py's own — apps.core.hotfix (and this
    overlay finder) are generic, reused-as-is infra, not Campus-specific, so
    Central gets the same sanctioned on-site patch path without a re-freeze.
    """
    root = Path(sys.executable).resolve().parent / "hotfix" if getattr(
        sys, "frozen", False
    ) else Path(__file__).resolve().parent / "hotfix"
    if not root.is_dir():
        return
    overlaid = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.py"))
    if not overlaid:
        return

    class _HotfixFinder:
        @staticmethod
        def find_spec(fullname, path=None, target=None):
            rel = fullname.replace(".", os.sep)
            for cand in (root / rel / "__init__.py", root / f"{rel}.py"):
                if cand.is_file():
                    return importlib.util.spec_from_file_location(fullname, str(cand))
            return None

    sys.meta_path.insert(0, _HotfixFinder)
    print(f"central: HOTFIX OVERLAY ACTIVE — {', '.join(overlaid)}", file=sys.stderr, flush=True)


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "central.settings.prod")
    import django

    django.setup()


def cmd_serve(argv: list[str]) -> None:
    _bootstrap_django()
    from waitress import serve

    from central.wsgi import application

    host, port = "127.0.0.1", 8002
    trusted_proxy = os.environ.get("CAMPUS_TRUSTED_PROXY", "127.0.0.1")
    args = iter(argv)
    for a in args:
        if a == "--host":
            host = next(args)
        elif a == "--port":
            port = int(next(args))
        elif a == "--trusted-proxy":
            trusted_proxy = next(args)
        else:
            raise SystemExit(f"central-app.exe serve: unknown argument {a!r}")

    print(f"Campus Central serving on {host}:{port} (central.settings.prod)", flush=True)
    # Same waitress trusted-proxy fix as campus_app.py's cmd_serve, for the
    # identical reason: Caddy terminates TLS and forwards over plain HTTP,
    # setting X-Forwarded-*; waitress ignores those headers by default, so
    # without this Django's SECURE_SSL_REDIRECT loops forever behind Caddy.
    serve(
        application,
        host=host,
        port=port,
        threads=8,
        trusted_proxy=trusted_proxy,
        trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"},
        clear_untrusted_proxy_headers=True,
    )


def cmd_manage(argv: list[str]) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "central.settings.prod")
    from django.core.management import execute_from_command_line

    execute_from_command_line(["central-app.exe manage", *argv])


def main() -> None:
    _apply_hotfix_overlay()
    if len(sys.argv) < 2 or sys.argv[1] not in ("serve", "manage"):
        print(__doc__)
        raise SystemExit(2)
    mode, rest = sys.argv[1], sys.argv[2:]
    if mode == "serve":
        cmd_serve(rest)
    else:
        cmd_manage(rest)


if __name__ == "__main__":
    # Same reason as campus_app.py's own: required before anything that might
    # use multiprocessing in a frozen exe. Central has no multiprocessing-
    # using management command today (no django_q), but this costs nothing
    # and keeps the two entrypoints' startup sequence identical.
    multiprocessing.freeze_support()
    main()
