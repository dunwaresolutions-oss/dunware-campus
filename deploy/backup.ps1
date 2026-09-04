<#
  Campus - encrypted backup (Phase 8).

  pg_dump (custom format) + the media directory, packed into one archive,
  then GPG symmetric-encrypted with the operator's passphrase. Nothing
  readable ever sits on disk once the run finishes. See
  docs/BACKUP_RESTORE_DRILL.md for the drill procedure and
  docs/DEPLOYMENT.md for backup rotation guidance.

  Where the binaries come from:
    - pg_dump: $InstallRoot\pgsql\bin\pg_dump.exe (the bundled portable
      PostgreSQL, present from Phase 9 on) falling back to PATH.
    - gpg: expected on PATH (bundled in the installer in Phase 9; on a dev
      box, Git for Windows / Gpg4win already provide it).

  On a box with no pg_dump yet (this repo, before Phase 9 bundles Postgres),
  pass -Simulate to exercise the full archive -> encrypt pipeline against a
  placeholder dump instead of a real database - that is exactly the Phase 8
  drill run; the real pg_dump path needs zero changes once Postgres exists.

  Usage:
    .\backup.ps1 -Out D:\backups -Passphrase (Read-Host -AsSecureString) ...
    $env:CAMPUS_BACKUP_PASSPHRASE = '...'; .\backup.ps1 -Out D:\backups
    .\backup.ps1 -Out D:\backups -Simulate   # drill / dev, no Postgres needed
#>
param(
  [string]$InstallRoot = "$env:ProgramData\Campus",
  [string]$Out = ".",
  [string]$Passphrase = $env:CAMPUS_BACKUP_PASSPHRASE,
  [int]$RetentionDays = 30,
  [switch]$Simulate
)

$ErrorActionPreference = "Stop"

function Resolve-PgDump {
  $bundled = Join-Path $InstallRoot "pgsql\bin\pg_dump.exe"
  if (Test-Path $bundled) { return $bundled }
  $onPath = Get-Command pg_dump -ErrorAction SilentlyContinue
  if ($onPath) { return $onPath.Source }
  return $null
}

if (-not $Passphrase) {
  throw "No backup passphrase. Pass -Passphrase or set CAMPUS_BACKUP_PASSPHRASE."
}
if (-not (Get-Command gpg -ErrorAction SilentlyContinue)) {
  throw "gpg was not found on PATH. Install Gpg4win (or Git for Windows) or bundle gpg.exe."
}

New-Item -ItemType Directory -Force -Path $Out | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$work = Join-Path $Out "_campus-backup-$stamp"
New-Item -ItemType Directory -Force -Path $work | Out-Null

try {
  $pgDump = Resolve-PgDump
  $dumpPath = Join-Path $work "db.dump"

  if ($pgDump -and -not $Simulate) {
    Write-Host "Dumping database via $pgDump ..."
    $envFile = Join-Path $InstallRoot "app\.env"
    $dbUrl = if (Test-Path $envFile) {
      (Select-String -Path $envFile -Pattern '^DATABASE_URL=(.*)$').Matches.Groups[1].Value
    } else { $env:DATABASE_URL }
    if (-not $dbUrl) { throw "No DATABASE_URL found in $envFile or the environment." }
    & $pgDump --format=custom --no-owner --file $dumpPath $dbUrl
    if ($LASTEXITCODE -ne 0) { throw "pg_dump exited with code $LASTEXITCODE" }
  } else {
    if (-not $Simulate) {
      throw "pg_dump was not found. Pass -Simulate to drill the archive/encrypt pipeline without it."
    }
    Write-Host "SIMULATE: no real pg_dump run - writing a placeholder dump for the drill." -ForegroundColor Yellow
    "campus simulated dump - $stamp" | Set-Content -Path $dumpPath -Encoding utf8
  }

  $mediaSrc = Join-Path $InstallRoot "media"
  if (Test-Path $mediaSrc) {
    Copy-Item $mediaSrc (Join-Path $work "media") -Recurse
  }

  $zipPath = Join-Path $Out "campus-$stamp.zip"
  Compress-Archive -Path (Join-Path $work "*") -DestinationPath $zipPath -Force

  $encPath = "$zipPath.gpg"
  gpg --batch --yes --pinentry-mode loopback --passphrase $Passphrase `
      --symmetric --cipher-algo AES256 -o $encPath $zipPath
  if ($LASTEXITCODE -ne 0) { throw "gpg encryption exited with code $LASTEXITCODE" }

  Remove-Item $zipPath -Force  # never leave the plaintext archive on disk

  if ($RetentionDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    Get-ChildItem $Out -Filter "campus-*.zip.gpg" |
      Where-Object { $_.LastWriteTime -lt $cutoff } |
      ForEach-Object { Write-Host "Pruning old backup: $($_.Name)"; Remove-Item $_.FullName -Force }
  }

  Write-Host "Backup complete: $encPath" -ForegroundColor Green
  exit 0
} finally {
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
}
