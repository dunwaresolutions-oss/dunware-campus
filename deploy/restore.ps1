<#
  Campus - restore from an encrypted backup (Phase 8).

  Decrypt (gpg) -> expand -> [stop the Campus App service] -> restore the
  archive's FIELD_ENCRYPTION_KEY into app\.env -> pg_restore --clean
  --if-exists -> restore media -> `campus-app.exe manage migrate` (in case
  the backup predates a schema change) -> [start the service] -> verify.

  Only the FIELD_ENCRYPTION_KEY line of the archive's env.backup is applied,
  never the whole file: a fresh install has its own DATABASE_URL / Postgres
  password, and overwriting that would break the connection. Archives made
  before env.backup existed carry no key; the script warns.

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

function Resolve-Gpg {
  $bundled = Join-Path $InstallRoot "gpg\bin\gpg.exe"
  if (Test-Path $bundled) { return $bundled }
  $onPath = Get-Command gpg -ErrorAction SilentlyContinue
  if ($onPath) { return $onPath.Source }
  return $null
}

# Put the backup's FIELD_ENCRYPTION_KEY into the target .env (only that line).
function Restore-EncryptionKey {
  param([string]$BackupEnv, [string]$TargetEnv)
  $keyPattern = '^FIELD_ENCRYPTION_KEY=(.*)$'
  $found = Select-String -Path $BackupEnv -Pattern $keyPattern | Select-Object -First 1
  if (-not $found) {
    Write-Warning "env.backup has no FIELD_ENCRYPTION_KEY line - the encryption key was NOT restored."
    return
  }
  $newKey = $found.Matches.Groups[1].Value
  if (-not (Test-Path $TargetEnv)) {
    Write-Warning "No $TargetEnv to update - the encryption key was NOT applied. It is in the archive's env.backup."
    return
  }
  $lines = [System.IO.File]::ReadAllLines($TargetEnv)
  $current = $lines | Where-Object { $_ -match $keyPattern } | Select-Object -First 1
  if ($current -and ($current -replace '^FIELD_ENCRYPTION_KEY=', '') -eq $newKey) {
    Write-Host "  FIELD_ENCRYPTION_KEY already matches the backup."
    return
  }
  $updated = $false
  $result = New-Object System.Collections.Generic.List[string]
  foreach ($l in $lines) {
    if ($l -match $keyPattern) {
      if (-not $updated) { $result.Add("FIELD_ENCRYPTION_KEY=$newKey"); $updated = $true }
    } else { $result.Add($l) }
  }
  if (-not $updated) { $result.Add("FIELD_ENCRYPTION_KEY=$newKey") }
  # UTF-8 without a BOM: django-environ silently drops a BOM-prefixed first line.
  [System.IO.File]::WriteAllLines($TargetEnv, $result.ToArray(), (New-Object System.Text.UTF8Encoding($false)))
  Write-Host "  Restored FIELD_ENCRYPTION_KEY from the backup into $TargetEnv (the restored data is encrypted with it)." -ForegroundColor Yellow
}

# Record a restore-verification run so the console shows "last verified".
$script:AppExe = Join-Path $InstallRoot "app\campus-app.exe"
function Record-Verify {
  param([string[]]$RecordArgs)
  if (-not (Test-Path $script:AppExe)) { return }
  try { & $script:AppExe manage record_backup @RecordArgs 2>$null | Out-Null } catch { }
}

$startIso = (Get-Date).ToString("o")

if (-not (Test-Path $Archive)) { throw "Archive not found: $Archive" }
if (-not $Passphrase) { throw "No backup passphrase. Pass -Passphrase or set CAMPUS_BACKUP_PASSPHRASE." }
$gpg = Resolve-Gpg
if (-not $gpg) {
  throw "gpg was not found (looked in $InstallRoot\gpg\bin and on PATH). It ships with the installer; on a dev box install Git for Windows or Gpg4win."
}
$env:GNUPGHOME = Join-Path $InstallRoot "gpg\home"
New-Item -ItemType Directory -Force -Path $env:GNUPGHOME | Out-Null

$work = Join-Path ([System.IO.Path]::GetTempPath()) ("campus-restore-" + [guid]::NewGuid())
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
      Write-Host "Stopping Campus App service ..."
      Stop-Service -Name "Campus App" -ErrorAction SilentlyContinue
    }
    $envFile = Join-Path $InstallRoot "app\.env"
    $backupEnv = Join-Path $expandDir "env.backup"
    if (Test-Path $backupEnv) {
      Restore-EncryptionKey -BackupEnv $backupEnv -TargetEnv $envFile
    } else {
      Write-Warning "This archive has no env.backup (made before the encryption key was included). Make sure $envFile still holds the ORIGINAL FIELD_ENCRYPTION_KEY, or restored encrypted fields will not decrypt."
    }
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

    # Apply any migrations the backup predates. The frozen install has no
    # Python / manage.py - it is campus-app.exe manage <cmd> (same as
    # repair-campus.ps1); fall back to manage.py only on a dev checkout.
    if (Test-Path $script:AppExe) {
      & $script:AppExe manage migrate --noinput
    } else {
      Push-Location (Join-Path $InstallRoot "app")
      try { & python manage.py migrate --noinput } finally { Pop-Location }
    }
    if ($LASTEXITCODE -ne 0) { throw "post-restore migrate exited with code $LASTEXITCODE" }

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
    if (Test-Path (Join-Path $expandDir "env.backup")) {
      Write-Host "  Would restore FIELD_ENCRYPTION_KEY from: $(Join-Path $expandDir 'env.backup')"
    } else {
      Write-Warning "This archive has no env.backup - it carries no encryption key."
    }
    if (Test-Path (Join-Path $expandDir "media")) {
      Write-Host "  Would restore media from: $(Join-Path $expandDir 'media')"
    }
  }
  $dumpBytes = (Get-Item $dumpPath).Length
  $verifyArgs = @(
    "--status", "SUCCESS", "--kind", "VERIFY", "--started", $startIso,
    "--archive", (Split-Path $Archive -Leaf), "--size", "$dumpBytes",
    "--host", $env:COMPUTERNAME
  )
  if (-not $Simulate) { $verifyArgs += "--database-ok" }
  if (Test-Path (Join-Path $expandDir "media")) { $verifyArgs += "--media-ok" }
  Record-Verify $verifyArgs

  exit 0
} catch {
  Record-Verify @("--status", "FAILED", "--kind", "VERIFY", "--started", $startIso,
                  "--error", $_.Exception.Message, "--host", $env:COMPUTERNAME)
  throw
} finally {
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
}
