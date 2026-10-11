<#
  Campus Central - encrypted backup. Mirrors deploy/backup.ps1 (Campus's own)
  exactly -- same pipeline, same already-proven fixes (BOM-free env writes,
  never leaving a plaintext archive on disk, GNUPGHOME isolated from any
  operator GnuPG setup) -- adapted for Central's own paths:

    pg_dump (custom format) + media_central + a copy of app\.env.central (as
    env.backup -- carries CENTRAL_FIELD_ENCRYPTION_KEY, without which the
    restored encrypted fields cannot be decrypted), packed into one archive,
    then GPG symmetric-encrypted with the operator's passphrase. Nothing
    readable ever sits on disk once the run finishes.

  Where the binaries come from:
    - pg_dump: $InstallRoot\pgsql\bin\pg_dump.exe (same staged portable
      PostgreSQL install-central.ps1 already uses) falling back to PATH.
    - gpg: $InstallRoot\gpg\bin\gpg.exe (staged the same way Campus's own
      install stages it -- see central.iss) falling back to PATH.

  Archive filenames are prefixed campus-central- (not campus-), so Campus's
  own and Central's own backups can sit in the same folder without ever
  being confused with each other or pruned against the wrong retention scan.

  Usage:
    .\backup-central.ps1 -Out D:\backups -Passphrase (Read-Host -AsSecureString)
    $env:CAMPUS_CENTRAL_BACKUP_PASSPHRASE = '...'; .\backup-central.ps1 -Out D:\backups
    .\backup-central.ps1 -Out D:\backups -Simulate   # drill / dev, no Postgres needed

  Deliberately NOT built: a BackupRun / "Backups" console page the way
  Campus's own apps.reporting provides -- Central has no equivalent app.
  This script's own exit code / console output is the operator-facing
  signal; wire it into Windows Task Scheduler for a recurring run, same as
  Campus's own documented recommendation (see docs/DEPLOYMENT.md).
#>
param(
  [string]$InstallRoot = "$env:ProgramData\CampusCentral",
  [string]$Out = ".",
  [string]$Passphrase = $env:CAMPUS_CENTRAL_BACKUP_PASSPHRASE,
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

function Resolve-Gpg {
  $bundled = Join-Path $InstallRoot "gpg\bin\gpg.exe"
  if (Test-Path $bundled) { return $bundled }
  $onPath = Get-Command gpg -ErrorAction SilentlyContinue
  if ($onPath) { return $onPath.Source }
  return $null
}

New-Item -ItemType Directory -Force -Path $Out | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$work = Join-Path $Out "_campus-central-backup-$stamp"
New-Item -ItemType Directory -Force -Path $work | Out-Null

try {
  if (-not $Passphrase) {
    throw "No backup passphrase. Pass -Passphrase or set CAMPUS_CENTRAL_BACKUP_PASSPHRASE."
  }
  $gpg = Resolve-Gpg
  if (-not $gpg) {
    throw "gpg was not found (looked in $InstallRoot\gpg\bin and on PATH). It ships with the installer; on a dev box install Git for Windows or Gpg4win."
  }
  $env:GNUPGHOME = Join-Path $InstallRoot "gpg\home"
  New-Item -ItemType Directory -Force -Path $env:GNUPGHOME | Out-Null

  $pgDump = Resolve-PgDump
  $dumpPath = Join-Path $work "db.dump"

  if ($pgDump -and -not $Simulate) {
    Write-Host "Dumping database via $pgDump ..."
    $envFile = Join-Path $InstallRoot "app\.env.central"
    $dbUrl = if (Test-Path $envFile) {
      (Select-String -Path $envFile -Pattern '^CENTRAL_DATABASE_URL=(.*)$').Matches.Groups[1].Value
    } else { $env:CENTRAL_DATABASE_URL }
    if (-not $dbUrl) { throw "No CENTRAL_DATABASE_URL found in $envFile or the environment." }
    & $pgDump --format=custom --no-owner --file $dumpPath $dbUrl
    if ($LASTEXITCODE -ne 0) { throw "pg_dump exited with code $LASTEXITCODE" }
  } else {
    if (-not $Simulate) {
      throw "pg_dump was not found. Pass -Simulate to drill the archive/encrypt pipeline without it."
    }
    Write-Host "SIMULATE: no real pg_dump run - writing a placeholder dump for the drill." -ForegroundColor Yellow
    "campus central simulated dump - $stamp" | Set-Content -Path $dumpPath -Encoding utf8
  }

  $mediaSrc = Join-Path $InstallRoot "media_central"
  if (Test-Path $mediaSrc) {
    Copy-Item $mediaSrc (Join-Path $work "media_central") -Recurse
  }

  # Every encrypted database field is keyed by CENTRAL_FIELD_ENCRYPTION_KEY,
  # and a fresh install generates a different one -- a backup without it
  # cannot be restored onto new hardware. Plaintext copy lives only in
  # $work (deleted in `finally`); the archive itself is encrypted.
  $envSrc = Join-Path $InstallRoot "app\.env.central"
  if (Test-Path $envSrc) {
    Copy-Item $envSrc (Join-Path $work "env.backup")
  } elseif (-not $Simulate) {
    Write-Warning "No $envSrc found - this archive will NOT contain CENTRAL_FIELD_ENCRYPTION_KEY, so it cannot be restored onto a fresh install unless you keep that key elsewhere."
  }

  $zipPath = Join-Path $Out "campus-central-$stamp.zip"
  Compress-Archive -Path (Join-Path $work "*") -DestinationPath $zipPath -Force

  $encPath = "$zipPath.gpg"
  & $gpg --batch --yes --pinentry-mode loopback --passphrase $Passphrase `
      --symmetric --cipher-algo AES256 -o $encPath $zipPath
  if ($LASTEXITCODE -ne 0) { throw "gpg encryption exited with code $LASTEXITCODE" }
  $encryptedOk = $true

  Remove-Item $zipPath -Force  # never leave the plaintext archive on disk

  if ($RetentionDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    Get-ChildItem $Out -Filter "campus-central-*.zip.gpg" |
      Where-Object { $_.LastWriteTime -lt $cutoff } |
      ForEach-Object { Write-Host "Pruning old backup: $($_.Name)"; Remove-Item $_.FullName -Force }
  }

  Write-Host "Backup complete: $encPath" -ForegroundColor Green
  exit 0
} finally {
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
  if ($zipPath -and (Test-Path $zipPath)) { Remove-Item $zipPath -Force -ErrorAction SilentlyContinue }
  if ($encPath -and -not $encryptedOk -and (Test-Path $encPath)) { Remove-Item $encPath -Force -ErrorAction SilentlyContinue }
}
