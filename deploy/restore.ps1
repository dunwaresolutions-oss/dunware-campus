<#
  Campus - restore from an encrypted backup (Phase 8).

  Decrypt (gpg) -> expand -> [stop the Campus App service] -> pg_restore
  --clean --if-exists -> restore media -> `manage.py migrate` (in case the
  backup predates a schema change) -> [start the service] -> verify.

  Part of the Phase 8 test plan: every release must pass a
  backup -> wipe -> restore -> "everything still there" drill - see
  docs/BACKUP_RESTORE_DRILL.md.

  -Simulate mirrors backup.ps1: when there is no pg_restore yet (this repo,
  pre-Phase-9), it decrypts and expands the archive and prints what it would
  have restored, instead of touching a database. -SkipServiceRestart lets the
  drill run on a dev box with no "Campus App" service registered.

  Usage:
    .\restore.ps1 -Archive D:\backups\campus-20260904-120000.zip.gpg -Simulate
    .\restore.ps1 -Archive ... -Passphrase (Read-Host -AsSecureString)
#>
param(
  [string]$InstallRoot = "$env:ProgramData\Campus",
  [Parameter(Mandatory = $true)][string]$Archive,
  [string]$Passphrase = $env:CAMPUS_BACKUP_PASSPHRASE,
  [switch]$Simulate,
  [switch]$SkipServiceRestart
)

$ErrorActionPreference = "Stop"

function Resolve-PgRestore {
  $bundled = Join-Path $InstallRoot "pgsql\bin\pg_restore.exe"
  if (Test-Path $bundled) { return $bundled }
  $onPath = Get-Command pg_restore -ErrorAction SilentlyContinue
  if ($onPath) { return $onPath.Source }
  return $null
}

if (-not (Test-Path $Archive)) { throw "Archive not found: $Archive" }
if (-not $Passphrase) { throw "No backup passphrase. Pass -Passphrase or set CAMPUS_BACKUP_PASSPHRASE." }
if (-not (Get-Command gpg -ErrorAction SilentlyContinue)) { throw "gpg was not found on PATH." }

$work = Join-Path ([System.IO.Path]::GetTempPath()) ("campus-restore-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $work | Out-Null
$zipPath = Join-Path $work "archive.zip"

try {
  Write-Host "Decrypting $Archive ..."
  gpg --batch --yes --pinentry-mode loopback --passphrase $Passphrase -o $zipPath -d $Archive
  if ($LASTEXITCODE -ne 0) { throw "gpg decryption exited with code $LASTEXITCODE (wrong passphrase?)" }

  $expandDir = Join-Path $work "expanded"
  Expand-Archive -Path $zipPath -DestinationPath $expandDir -Force
  $dumpPath = Join-Path $expandDir "db.dump"
  if (-not (Test-Path $dumpPath)) { throw "Archive did not contain db.dump - refusing to restore." }
  Write-Host "Decrypted and expanded OK: $((Get-Item $dumpPath).Length) bytes in db.dump" -ForegroundColor Green

  $pgRestore = Resolve-PgRestore
  if ($pgRestore -and -not $Simulate) {
    if (-not $SkipServiceRestart) {
      Write-Host "Stopping Campus App service ..."
      Stop-Service -Name "Campus App" -ErrorAction SilentlyContinue
    }
    $envFile = Join-Path $InstallRoot "app\.env"
    $dbUrl = if (Test-Path $envFile) {
      (Select-String -Path $envFile -Pattern '^DATABASE_URL=(.*)$').Matches.Groups[1].Value
    } else { $env:DATABASE_URL }
    if (-not $dbUrl) { throw "No DATABASE_URL found in $envFile or the environment." }

    & $pgRestore --clean --if-exists --no-owner --dbname=$dbUrl $dumpPath
    if ($LASTEXITCODE -ne 0) { throw "pg_restore exited with code $LASTEXITCODE" }

    $mediaExpanded = Join-Path $expandDir "media"
    if (Test-Path $mediaExpanded) {
      $mediaDest = Join-Path $InstallRoot "media"
      robocopy $mediaExpanded $mediaDest /MIR | Out-Null
    }

    Push-Location (Join-Path $InstallRoot "app")
    try { & .\manage.py migrate } finally { Pop-Location }

    if (-not $SkipServiceRestart) {
      Write-Host "Starting Campus App service ..."
      Start-Service -Name "Campus App" -ErrorAction SilentlyContinue
    }
    Write-Host "Restore complete." -ForegroundColor Green
  } else {
    if (-not $Simulate) {
      throw "pg_restore was not found. Pass -Simulate to drill decrypt/expand without a live database."
    }
    Write-Host "SIMULATE: decrypt + expand verified; no database was touched." -ForegroundColor Yellow
    Write-Host "  Would restore: $dumpPath"
    if (Test-Path (Join-Path $expandDir "media")) {
      Write-Host "  Would restore media from: $(Join-Path $expandDir 'media')"
    }
  }
  exit 0
} finally {
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
}
