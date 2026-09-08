"""
Campus frozen entrypoint (PyInstaller — see deploy/campus.spec).

This is the *only* script the installer / Windows service ever calls. Two
modes:

    campus-app.exe serve [--host H] [--port P]
        Run waitress serving config.wsgi. This is what "Campus App" (the
        Windows service, sc.exe-registered by install.ps1) runs — it never
        returns until stopped.

    campus-app.exe manage <django management command> [args...]
        Proxies straight to manage.py. install.ps1 uses this for `migrate`,
        `collectstatic`, `createsuperuser`, and the operator uses it for
        `run_retention` / `export_student` / `erase_student` post-install —
        there is no Python on the target machine to run manage.py directly.

Always config.settings.prod. Reads <exe dir>\\.env (settings/base.py resolves
BASE_DIR from sys.executable when frozen — see the `sys.frozen` check there).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _apply_hotfix_overlay() -> None:
    """Let a corrected ``.py`` dropped under ``<exe dir>\\hotfix`` at its real
    package path shadow the frozen copy — the sanctioned way to fix a logic bug
    on a customer site without a full re-freeze (see docs/DEPLOYMENT.md and
    apps/core/hotfix.py). A frozen build serves modules from the PYZ via a
    meta-path importer that outranks ``sys.path``; this puts a narrow
    filesystem finder ahead of it that only claims names actually present in
    the hotfix dir, so everything else is untouched. No-op when the dir is
    absent or empty. Active overlays are printed to stderr (-> the service log)
    and re-surfaced by the ``core.W001`` system check.
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
    print(f"campus: HOTFIX OVERLAY ACTIVE — {', '.join(overlaid)}", file=sys.stderr, flush=True)


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    import django

    django.setup()


def cmd_serve(argv: list[str]) -> None:
    _bootstrap_django()
    from waitress import serve

    from config.wsgi import application

    host, port = "127.0.0.1", 8001
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
            raise SystemExit(f"campus-app.exe serve: unknown argument {a!r}")

    print(f"Campus serving on {host}:{port} (config.settings.prod)", flush=True)
    # Caddy (the bundled front door) terminates TLS and forwards to waitress
    # over plain HTTP on the LAN box itself, setting X-Forwarded-Proto/-For/
    # -Host so Django's SECURE_PROXY_SSL_HEADER can tell the request was
    # HTTPS on the wire. Waitress does NOT trust those headers by default
    # (anti-spoofing) - without trusted_proxy/trusted_proxy_headers here,
    # Django never sees is_secure()=True and SECURE_SSL_REDIRECT loops
    # forever. A frozen smoke test caught this - see docs/PACKAGING.md.
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
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    from django.core.management import execute_from_command_line

    execute_from_command_line(["campus-app.exe manage", *argv])


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
    main()
