# Campus — Backup / Restore Drill

Part of the Phase 8 hardening pass: every release must survive a
**backup → wipe → restore → "everything's still there"** drill before it
ships. This document is both the procedure and the record of the drill run
against this build.

## What the scripts do

`deploy/backup.ps1` — `pg_dump` (custom format) + the `media/` directory,
packed into one zip, then GPG symmetric-encrypted with the operator's
passphrase (`AES256`, `gpg --symmetric`). The plaintext zip is deleted the
moment encryption succeeds; nothing readable is ever left on disk. Old
encrypted backups past `-RetentionDays` (default 30) are pruned.

`deploy/restore.ps1` — decrypts, expands, stops the `Campus App` service,
`pg_restore --clean --if-exists`, restores `media/`, runs `manage.py migrate`
(covers a backup taken before a schema change), restarts the service.

Both resolve `pg_dump`/`pg_restore` from the bundled portable PostgreSQL
(`%ProgramData%\Campus\pgsql\bin`, present from Phase 9 on) and fall back to
`PATH`. `gpg` is expected on `PATH` — bundled with the installer in Phase 9,
already present on a dev box via Git for Windows / Gpg4win.

## Honest scope of this drill

This repository's dev environment has **no PostgreSQL installed** (no
`pg_dump`/`pg_restore` on `PATH`, and the portable copy Phase 9 bundles
doesn't exist yet). So:

- **Proven for real, today:** the archive → GPG-encrypt → decrypt → expand
  pipeline, the wrong-passphrase rejection, and the retention pruning logic.
  Both scripts support a `-Simulate` flag for exactly this — it swaps a real
  `pg_dump`/`pg_restore` call for a placeholder file, exercising every other
  line of the script unchanged.
- **Deferred to Phase 9:** the actual `pg_dump` / `pg_restore` calls against
  a running Campus database, once the portable PostgreSQL is bundled and
  installed. The script code for that path is written now (see above) and
  needs no changes once Postgres exists — only `-Simulate` goes away.
- **Proven for real, today, by a different mechanism:** that Campus data
  really can be recovered from a stored state — the retention/erasure drill
  (`docs/RETENTION_ERASURE_DRILL.md`) exercises the Django ORM / migrations
  path end to end against a real (SQLite, for local dev) database.

## Drill transcript — 2026-09-04

```
> $env:CAMPUS_BACKUP_PASSPHRASE = "<drill passphrase>"
> .\backup.ps1 -Out D:\<drill-dir> -Simulate

SIMULATE: no real pg_dump run - writing a placeholder dump for the drill.
Backup complete: D:\<drill-dir>\campus-20260904-133756.zip.gpg
```

```
> .\restore.ps1 -Archive D:\<drill-dir>\campus-20260904-133756.zip.gpg -Simulate -SkipServiceRestart

Decrypting D:\<drill-dir>\campus-20260904-133756.zip.gpg ...
gpg: AES256.CFB encrypted data
gpg: encrypted with 1 passphrase
Decrypted and expanded OK: 44 bytes in db.dump
SIMULATE: decrypt + expand verified; no database was touched.
  Would restore: ...\expanded\db.dump
```

**Negative case — wrong passphrase is rejected, not silently accepted:**

```
> .\restore.ps1 -Archive ... -Passphrase "wrong-passphrase" -Simulate -SkipServiceRestart

gpg: decryption failed: Bad session key
ERROR: gpg decryption exited with code 2 (wrong passphrase?)
```

Result: **pass** for everything in scope today. No plaintext archive was left
on disk at any point (verified — the working directory is removed in a
`finally` block on both scripts, and the intermediate plaintext zip is deleted
immediately after encryption in `backup.ps1`).

## Re-running the drill

```powershell
cd deploy
$env:CAMPUS_BACKUP_PASSPHRASE = "some-test-passphrase"
.\backup.ps1  -Out D:\some-scratch-dir -Simulate
.\restore.ps1 -Archive D:\some-scratch-dir\campus-*.zip.gpg -Simulate -SkipServiceRestart
```

Re-run the same two commands with `-Simulate` removed once a real Campus
install (with `pg_dump`/`pg_restore` on `PATH` or bundled) is available — that
is the Phase-9 acceptance test for these scripts, not new code.
