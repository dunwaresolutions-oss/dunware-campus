<#
  Campus — encrypted backup.  STUB for Phase 0; real version lands in Phase 8.

  pg_dump (custom format) + the media directory  ->  a single archive, then
  age/GPG encrypt it with the operator's recipient key. Nothing readable ever
  lands on disk in the clear. Backups are the operator's responsibility to
  move off-box; docs/DEPLOYMENT.md covers rotation and the restore drill.

  Usage (finished):  .\backup.ps1 -Out D:\backups -Recipient <age-pubkey-or-gpg-id>
#>
param(
  [string]$InstallRoot = "$env:ProgramData\Campus",
  [string]$Out = ".",
  [string]$Recipient = ""
)
Write-Host "Campus backup — Phase 0 stub. No-op." -ForegroundColor Yellow
exit 0
