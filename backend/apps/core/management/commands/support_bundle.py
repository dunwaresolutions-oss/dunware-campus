"""
Write a **redacted** support bundle: one ZIP a technician can carry off-site.

    campus-app.exe manage support_bundle
    campus-app.exe manage support_bundle --output D:\\handoff --log-bytes 1048576

Contents (nothing in here is student data — see the redaction rules below):

    report.txt            build identity, platform, disk, service states
    env.redacted          .env with every secret value replaced by ***
    health/check.txt      `manage check --deploy`
    health/migrations.txt `manage showmigrations --list`
    health/services.txt   `sc query` for the Campus Windows services
    health/audit.json     audit-log entry counts by action, last 7 days (counts only)
    health/db.json        row count per table + total
    logs/*.log            the tail of each service log
    caddy/                the Caddyfile and its adapted JSON, best effort

The .env redaction replaces the value of any key whose name looks like a
secret (SECRET / KEY / PASSWORD / TOKEN / DSN / SALT / CREDENTIAL) and the
password inside any URL-shaped value. Log lines are already PII-scrubbed by
apps.core.logging.PIIScrubFilter before they are written.
"""
from __future__ import annotations

import collections
import datetime as dt
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.hotfix import active_hotfixes
from apps.core.support import install_root as _install_root
from apps.core.version import build_stamp

_SECRET_HINT = re.compile(r"(SECRET|KEY|PASSWORD|PASSWD|TOKEN|DSN|SALT|CREDENTIAL)", re.I)
_URL_PW = re.compile(r"(://[^:/@\s]+:)([^@/\s]+)(@)")
_SERVICES = ["Campus App", "Campus Proxy", "Campus PostgreSQL", "Campus Remote"]


def _redact_env(text: str) -> str:
    out = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key, _, value = line.partition("=")
        if _SECRET_HINT.search(key):
            out.append(f"{key}=***redacted***")
        elif "://" in value:
            out.append(f"{key}={_URL_PW.sub(r'\1***\3', value)}")
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def _tail(path: Path, nbytes: int) -> bytes:
    with path.open("rb") as fh:
        try:
            fh.seek(-nbytes, io.SEEK_END)
        except OSError:
            fh.seek(0)
        return fh.read()


def _run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(  # noqa: S603 - fixed argv lists built in this module only
            cmd, capture_output=True, text=True, timeout=30, check=False
        )
        return (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001
        return f"({' '.join(cmd)} failed: {exc})"


class Command(BaseCommand):
    help = "Write a redacted support bundle (logs, config, health) as one ZIP."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="ZIP path, or a directory to drop a timestamped ZIP in "
            "(default: <install root>\\support).",
        )
        parser.add_argument(
            "--log-bytes",
            type=int,
            default=512 * 1024,
            help="Tail this many bytes of each log file (default: 512 KiB).",
        )

    def handle(self, *args, **opts):
        root = _install_root()
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        out = opts.get("output")
        if not out:
            dest_dir = root / "support"
            dest_dir.mkdir(parents=True, exist_ok=True)
            zip_path = dest_dir / f"support-bundle-{stamp}.zip"
        else:
            p = Path(out)
            zip_path = p if p.suffix.lower() == ".zip" else p / f"support-bundle-{stamp}.zip"
            zip_path.parent.mkdir(parents=True, exist_ok=True)

        work = Path(tempfile.mkdtemp(prefix="campus-support-"))
        try:
            self._collect(work, root, opts["log_bytes"])
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(work.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(work).as_posix())
        finally:
            shutil.rmtree(work, ignore_errors=True)

        self.stdout.write(self.style.SUCCESS(f"support bundle written: {zip_path}"))

    # ── collectors ───────────────────────────────────────────────────────
    def _collect(self, work: Path, root: Path, log_bytes: int) -> None:
        (work / "health").mkdir(parents=True, exist_ok=True)
        (work / "logs").mkdir(parents=True, exist_ok=True)
        (work / "caddy").mkdir(parents=True, exist_ok=True)

        self._report(work / "report.txt", root)
        self._env(work / "env.redacted", root)
        self._health(work / "health")
        self._logs(work / "logs", root, log_bytes)
        self._caddy(work / "caddy", root)

    def _report(self, path: Path, root: Path) -> None:
        lines = [
            f"generated_at : {timezone.now().isoformat()}",
            f"build        : {json.dumps(build_stamp())}",
            f"platform     : {sys.platform} / {getattr(sys, 'getwindowsversion', lambda: '')()}",
            f"settings     : {settings.SETTINGS_MODULE}",
            f"install_root : {root}",
            f"remote_access: enabled={getattr(settings, 'REMOTE_ACCESS_ENABLED', False)} "
            f"hosts={getattr(settings, 'REMOTE_ACCESS_HOSTS', [])}",
        ]
        try:
            usage = shutil.disk_usage(str(root))
            lines.append(
                f"disk         : {usage.free // (1024**3)} GiB free of "
                f"{usage.total // (1024**3)} GiB"
            )
        except OSError as exc:  # noqa: BLE001
            lines.append(f"disk         : (unavailable: {exc})")

        lines.append(f"hotfixes     : {active_hotfixes() or 'none'}")

        if sys.platform == "win32":
            lines.append("")
            lines.append("services:")
            for name in _SERVICES:
                blob = _run(["sc", "query", name])
                state = "NOT INSTALLED"
                m = re.search(r"STATE\s+:\s+\d+\s+(\w+)", blob)
                if m:
                    state = m.group(1)
                lines.append(f"  {name:<20} {state}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _env(self, path: Path, root: Path) -> None:
        env_file = Path(settings.BASE_DIR) / ".env"
        if not env_file.exists():
            path.write_text("(no .env at " + str(env_file) + ")\n", encoding="utf-8")
            return
        raw = env_file.read_text(encoding="utf-8", errors="replace")
        path.write_text(_redact_env(raw), encoding="utf-8")

    def _health(self, out: Path) -> None:
        buf = io.StringIO()
        try:
            call_command("check", "--deploy", stdout=buf, stderr=buf)
        except SystemExit:
            pass
        except Exception as exc:  # noqa: BLE001
            buf.write(f"\n(check raised: {exc})\n")
        (out / "check.txt").write_text(buf.getvalue() or "(no output)\n", encoding="utf-8")

        buf = io.StringIO()
        try:
            call_command("showmigrations", "--list", stdout=buf)
        except Exception as exc:  # noqa: BLE001
            buf.write(f"(showmigrations raised: {exc})\n")
        (out / "migrations.txt").write_text(buf.getvalue(), encoding="utf-8")

        if sys.platform == "win32":
            (out / "services.txt").write_text(
                "\n\n".join(f"$ sc query {n}\n{_run(['sc', 'query', n])}" for n in _SERVICES),
                encoding="utf-8",
            )

        self._audit_json(out / "audit.json")
        self._db_json(out / "db.json")

    def _audit_json(self, path: Path) -> None:
        try:
            from apps.audit.models import AuditEntry

            since = timezone.now() - dt.timedelta(days=7)
            counts = collections.Counter(
                AuditEntry.objects.filter(at__gte=since).values_list("action", flat=True)
            )
            payload = {
                "window_days": 7,
                "since": since.isoformat(),
                "by_action": dict(sorted(counts.items())),
                "total": sum(counts.values()),
            }
        except Exception as exc:  # noqa: BLE001
            payload = {"error": str(exc)}
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _db_json(self, path: Path) -> None:
        payload: dict = {}
        try:
            for model in django_apps.get_models():
                label = f"{model._meta.app_label}.{model._meta.object_name}"
                try:
                    payload[label] = model.objects.count()
                except Exception as exc:  # noqa: BLE001
                    payload[label] = f"(error: {exc})"
        except Exception as exc:  # noqa: BLE001
            payload = {"error": str(exc)}
        blob = json.dumps(dict(sorted(payload.items())), indent=2)
        path.write_text(blob + "\n", encoding="utf-8")

    def _logs(self, out: Path, root: Path, log_bytes: int) -> None:
        candidates = [root / "logs", Path(settings.BASE_DIR) / "logs"]
        seen: set[Path] = set()
        found = False
        for d in candidates:
            if not d.is_dir() or d in seen:
                continue
            seen.add(d)
            for log in sorted(d.glob("*.log")):
                found = True
                try:
                    (out / log.name).write_bytes(_tail(log, log_bytes))
                except OSError as exc:
                    (out / (log.name + ".error")).write_text(str(exc), encoding="utf-8")
        if not found:
            (out / "README.txt").write_text(
                "no *.log files found under " + " or ".join(str(c) for c in candidates) + "\n",
                encoding="utf-8",
            )

    def _caddy(self, out: Path, root: Path) -> None:
        caddyfile = root / "caddy" / "Caddyfile"
        caddy_exe = root / "caddy" / "bin" / "caddy.exe"
        if caddyfile.exists():
            shutil.copyfile(caddyfile, out / "Caddyfile")
            if caddy_exe.exists():
                (out / "adapt.json").write_text(
                    _run([str(caddy_exe), "adapt", "--config", str(caddyfile)]),
                    encoding="utf-8",
                )
        else:
            (out / "README.txt").write_text(
                f"(no Caddyfile at {caddyfile})\n", encoding="utf-8"
            )
