<#
  Campus — restore from an encrypted backup.  STUB for Phase 0; real in Phase 8.

  Decrypt (age/GPG) -> stop the Campus App service -> pg_restore --clean --if-exists
  -> restore media -> run `manage.py migrate` (in case the backup predates a
  schema change) -> start the service -> verify the health check + a row count.

  Part of the Phase 8 test plan: every release must pass a backup -> wipe ->
  restore -> "everything still there" drill.

  Usage (finished):  .\restore.ps1 -Archive D:\backups\campus-2026-09-03.age
#>
param(
  [string]$InstallRoot = "$env:ProgramData\Campus",
  [string]$Archive = ""
)
Write-Host "Campus restore — Phase 0 stub. No-op." -ForegroundColor Yellow
exit 0
