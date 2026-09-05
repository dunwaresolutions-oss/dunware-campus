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

import os
import sys


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
