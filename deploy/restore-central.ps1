<#
  Campus Central - restore from an encrypted backup. Mirrors deploy/restore.ps1
  (Campus's own) exactly, adapted for Central's own paths/service/env file.

  Decrypt (gpg) -> expand -> [stop "Campus Central App"] -> restore the
  archive's CENTRAL_FIELD_ENCRYPTION_KEY into app\.env.central -> pg_restore
  --clean --if-exists -> restore media_central -> `central-app.exe manage
  migrate` (in case the backup predates a schema change) -> [start the
  service] -> verify.

  Only the CENTRAL_FIELD_ENCRYPTION_KEY line of the archive's env.backup is
  applied, never the whole file: a fresh install has its own
  CENTRAL_DATABASE_URL / Postgres password (port 5433 -- see
  install-central.ps1), and overwriting that would break the connection.

  -Simulate mirrors Campus's own restore.ps1: decrypts and expands the
  archive and prints what it would have restored, without touching a
  database. -SkipServiceRestart lets a drill run on a box with no
  "Campus Central App" service registered.

  Usage:
    .\restore-central.ps1 -Archive D:\backups\campus-central-20261009-120000.zip.gpg -Simulate
    .\restore-central.ps1 -Archive ... -Passphrase (Read-Host -AsSecureString)
#>
param(
  [string]$InstallRoot = "$env:ProgramData\CampusCentral",
  [Parameter(Mandatory = $true)][string]$Archive,
  [string]$Passphrase = $env:CAMPUS_CENTRAL_BACKUP_PASSPHRASE,
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

function Resolve-Gpg {
  $bundled = Join-Path $InstallRoot "gpg\bin\gpg.exe"
  if (Test-Path $bundled) { return $bundled }
  $onPath = Get-Command gpg -ErrorAction SilentlyContinue
  if ($onPath) { return $onPath.Source }
  return $null
}

# Put the backup's CENTRAL_FIELD_ENCRYPTION_KEY into the target .env.central
# (only that line).
function Restore-EncryptionKey {
  param([string]$BackupEnv, [string]$TargetEnv)
  $keyPattern = '^CENTRAL_FIELD_ENCRYPTION_KEY=(.*)$'
  $found = Select-String -Path $BackupEnv -Pattern $keyPattern | Select-Object -First 1
  if (-not $found) {
    Write-Warning "env.backup has no CENTRAL_FIELD_ENCRYPTION_KEY line - the encryption key was NOT restored."
    return
  }
  $newKey = $found.Matches.Groups[1].Value
  if (-not (Test-Path $TargetEnv)) {
    Write-Warning "No $TargetEnv to update - the encryption key was NOT applied. It is in the archive's env.backup."
    return
  }
  $lines = [System.IO.File]::ReadAllLines($TargetEnv)
  $current = $lines | Where-Object { $_ -match $keyPattern } | Select-Object -First 1
  if ($current -and ($current -replace '^CENTRAL_FIELD_ENCRYPTION_KEY=', '') -eq $newKey) {
    Write-Host "  CENTRAL_FIELD_ENCRYPTION_KEY already matches the backup."
    return
  }
  $updated = $false
  $result = New-Object System.Collections.Generic.List[string]
  foreach ($l in $lines) {
    if ($l -match $keyPattern) {
      if (-not $updated) { $result.Add("CENTRAL_FIELD_ENCRYPTION_KEY=$newKey"); $updated = $true }
    } else { $result.Add($l) }
  }
  if (-not $updated) { $result.Add("CENTRAL_FIELD_ENCRYPTION_KEY=$newKey") }
  [System.IO.File]::WriteAllLines($TargetEnv, $result.ToArray(), (New-Object System.Text.UTF8Encoding($false)))
  Write-Host "  Restored CENTRAL_FIELD_ENCRYPTION_KEY from the backup into $TargetEnv (the restored data is encrypted with it)." -ForegroundColor Yellow
}

if (-not (Test-Path $Archive)) { throw "Archive not found: $Archive" }
if (-not $Passphrase) { throw "No backup passphrase. Pass -Passphrase or set CAMPUS_CENTRAL_BACKUP_PASSPHRASE." }
$gpg = Resolve-Gpg
if (-not $gpg) {
  throw "gpg was not found (looked in $InstallRoot\gpg\bin and on PATH). It ships with the installer; on a dev box install Git for Windows or Gpg4win."
}
$env:GNUPGHOME = Join-Path $InstallRoot "gpg\home"
New-Item -ItemType Directory -Force -Path $env:GNUPGHOME | Out-Null

$appExe = Join-Path $InstallRoot "app\central-app.exe"
$work = Join-Path ([System.IO.Path]::GetTempPath()) ("campus-central-restore-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $work | Out-Null
$zipPath = Join-Path $work "archive.zip"

try {
  Write-Host "Decrypting $Archive ..."
  & $gpg --batch --yes --pinentry-mode loopback --passphrase $Passphrase -o $zipPath -d $Archive
  if ($LASTEXITCODE -ne 0) { throw "gpg decryption exited with code $LASTEXITCODE (wrong passphrase?)" }

  $expandDir = Join-Path $work "expanded"
  Expand-Archive -Path $zipPath -DestinationPath $expandDir -Force
  $dumpPath = Join-Path $expandDir "db.dump"
  if (-not (Test-Path $dumpPath)) { throw "Archive did not contain db.dump - refusing to restore." }
  Write-Host "Decrypted and expanded OK: $((Get-Item $dumpPath).Length) bytes in db.dump" -ForegroundColor Green

  $pgRestore = Resolve-PgRestore
  if ($pgRestore -and -not $Simulate) {
    if (-not $SkipServiceRestart) {
      Write-Host "Stopping Campus Central App service ..."
      Stop-Service -Name "Campus Central App" -ErrorAction SilentlyContinue
    }
    $envFile = Join-Path $InstallRoot "app\.env.central"
    $backupEnv = Join-Path $expandDir "env.backup"
    if (Test-Path $backupEnv) {
      Restore-EncryptionKey -BackupEnv $backupEnv -TargetEnv $envFile
    } else {
      Write-Warning "This archive has no env.backup. Make sure $envFile still holds the ORIGINAL CENTRAL_FIELD_ENCRYPTION_KEY, or restored encrypted fields will not decrypt."
    }
    $dbUrl = if (Test-Path $envFile) {
      (Select-String -Path $envFile -Pattern '^CENTRAL_DATABASE_URL=(.*)$').Matches.Groups[1].Value
    } else { $env:CENTRAL_DATABASE_URL }
    if (-not $dbUrl) { throw "No CENTRAL_DATABASE_URL found in $envFile or the environment." }

    & $pgRestore --clean --if-exists --no-owner --dbname=$dbUrl $dumpPath
    if ($LASTEXITCODE -ne 0) { throw "pg_restore exited with code $LASTEXITCODE" }

    $mediaExpanded = Join-Path $expandDir "media_central"
    if (Test-Path $mediaExpanded) {
      $mediaDest = Join-Path $InstallRoot "media_central"
      robocopy $mediaExpanded $mediaDest /MIR | Out-Null
    }

    if (Test-Path $appExe) {
      & $appExe manage migrate --noinput
    } else {
      Push-Location (Join-Path $InstallRoot "app")
      try { & python manage_central.py migrate --noinput } finally { Pop-Location }
    }
    if ($LASTEXITCODE -ne 0) { throw "post-restore migrate exited with code $LASTEXITCODE" }

    if (-not $SkipServiceRestart) {
      Write-Host "Starting Campus Central App service ..."
      Start-Service -Name "Campus Central App" -ErrorAction SilentlyContinue
    }
    Write-Host "Restore complete." -ForegroundColor Green
  } else {
    if (-not $Simulate) {
      throw "pg_restore was not found. Pass -Simulate to drill decrypt/expand without a live database."
    }
    Write-Host "SIMULATE: decrypt + expand verified; no database was touched." -ForegroundColor Yellow
    Write-Host "  Would restore: $dumpPath"
    if (Test-Path (Join-Path $expandDir "env.backup")) {
      Write-Host "  Would restore CENTRAL_FIELD_ENCRYPTION_KEY from: $(Join-Path $expandDir 'env.backup')"
    } else {
      Write-Warning "This archive has no env.backup - it carries no encryption key."
    }
    if (Test-Path (Join-Path $expandDir "media_central")) {
      Write-Host "  Would restore media_central from: $(Join-Path $expandDir 'media_central')"
    }
  }
  exit 0
} finally {
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
}
