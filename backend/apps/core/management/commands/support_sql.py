"""
Run a query against the live database from a support shell — audited.

    campus-app.exe manage support_sql "select count(*) from people_student" --operator "D. Duncombe"
    campus-app.exe manage support_sql "update ..." --operator "D. Duncombe" --write

Without --write only a single read-only SELECT is allowed and the transaction is
rolled back no matter what. Every run writes one audit-log entry attributed to
``support:<operator>`` — the audit log is append-only, so a field fix always
leaves a trace.
"""
from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.audit.models import AuditAction
from apps.audit.services import record

_LEADING_COMMENT = re.compile(r"^\s*(--[^\n]*\n|/\*.*?\*/|\s)+", re.S)


class _Operator:
    """A stand-in 'actor' so record() labels the entry support:<name> without a
    real User row (these commands run from an OS shell, not a request)."""

    username = ""
    role = "SUPPORT"

    def __init__(self, name: str) -> None:
        self._name = name

    def get_full_name(self) -> str:
        return f"support:{self._name}"


def _looks_read_only(sql: str) -> bool:
    body = _LEADING_COMMENT.sub("", sql).strip().rstrip(";")
    if ";" in body:  # one statement only
        return False
    return body[:6].lower() == "select" or body[:4].lower() == "with"


class Command(BaseCommand):
    help = "Run an audited SQL query (read-only unless --write)."

    def add_arguments(self, parser):
        parser.add_argument("sql", help="The SQL to run.")
        parser.add_argument(
            "--operator", required=True, help="Who is running this (goes in the audit log)."
        )
        parser.add_argument(
            "--write",
            action="store_true",
            help="Allow a writing statement and COMMIT it. Without this the "
            "transaction is always rolled back.",
        )

    def handle(self, *args, **opts):
        sql, operator, write = opts["sql"], opts["operator"], opts["write"]
        if not write and not _looks_read_only(sql):
            raise CommandError(
                "refusing to run: not a single read-only SELECT/WITH. "
                "Pass --write to run a writing statement."
            )

        actor = _Operator(operator)
        rowcount = None
        rows: list = []
        columns: list = []
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(sql)
                    rowcount = cur.rowcount
                    if cur.description:
                        columns = [c[0] for c in cur.description]
                        rows = cur.fetchall()
                if not write:
                    transaction.set_rollback(True)
        except Exception as exc:  # noqa: BLE001 - report + still audit the attempt
            record(
                AuditAction.UPDATE if write else AuditAction.READ,
                summary=f"support_sql FAILED: {sql}"[:255],
                actor=actor,
                extra={"write": write, "error": str(exc)},
            )
            raise CommandError(f"query failed (audited): {exc}") from exc

        record(
            AuditAction.UPDATE if write else AuditAction.READ,
            summary=f"support_sql{' [WRITE]' if write else ''}: {sql}"[:255],
            actor=actor,
            extra={"write": write, "rowcount": rowcount},
        )

        if columns:
            self.stdout.write(" | ".join(columns))
            self.stdout.write("-" * 60)
            for r in rows:
                self.stdout.write(" | ".join("" if v is None else str(v) for v in r))
            self.stdout.write(f"({len(rows)} row(s))")
        else:
            self.stdout.write(f"{rowcount} row(s) affected"
                              + ("" if write else " — ROLLED BACK (no --write)"))
