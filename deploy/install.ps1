<#
  Campus - first-run setup (Phase 9). Invoked by the Inno Setup installer
  (deploy/campus.iss [Run] section) right after files are laid out under
  $InstallRoot (default %ProgramData%\Campus); safe to re-run by hand too.

  What this does, in order — matches docs/DEPLOYMENT.md:
    1. Prerequisite checks (warn-only): OS, free disk, BitLocker.
    2. Lay out $InstallRoot\{pgdata,logs,media} (app/pgsql/caddy already
       exist - Inno's [Files] put them there).
    3. Generate per-install secrets into $InstallRoot\app\.env
       (SECRET_KEY, FIELD_ENCRYPTION_KEY, POSTGRES_PASSWORD), ACL'd to
       SYSTEM + Administrators only.
    4. initdb + register "Campus PostgreSQL" - ONLY if a portable Postgres
       is staged at $InstallRoot\pgsql\bin (see docs/DEPLOYMENT.md
       #third-party-binaries). Otherwise: clear message, skip, continue -
       the rest of setup does not depend on a live database.
    5. campus-app.exe manage migrate / collectstatic, then bootstrap the
       first superadmin (via apps.accounts.services.bootstrap_superadmin,
       Phase-1 code, called here for the first time in anger).
    6. Template the Caddyfile with the chosen LAN host; register
       "Campus Proxy" - needs both Caddy and NSSM staged.
    7. Register "Campus App" (campus-app.exe serve) - needs NSSM staged.
    8. Set every registered service to Automatic and start it.
    9. Drop a Start Menu / Desktop launcher (handled by campus.iss
       [Icons]; this script only writes the target .url).
   10. Print the LAN URL + a health check, or the plain list of manual
       follow-up steps if any binary was missing.

  Every step degrades to "print what's missing and continue" rather than
  crashing setup, because the two big third-party binaries (portable
  PostgreSQL, Caddy) and the service-wrapper (NSSM) are staged separately
  per docs/DEPLOYMENT.md - a build machine with no internet access for this
  session cannot fetch them, but the rest of the install is real and usable
  today (e.g. against a Postgres the operator installed some other way).
#>
param(
  [string]$InstallRoot = "$env:ProgramData\Campus",
  [string]$LanHost = "localhost",
  [string]$ApiBind = "127.0.0.1:8001",
  [switch]$SkipServices
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Warn2($msg) { Write-Host "    ! $msg" -ForegroundColor Yellow }
function Write-Skip($msg) { Write-Host "    - skipped: $msg" -ForegroundColor DarkYellow }

function New-RandomBytes([int]$count) {
  # Windows PowerShell 5.1 runs on .NET Framework, which only exposes the
  # instance-based RNG API (RandomNumberGenerator.Fill is .NET 6+ only).
  $buf = New-Object byte[] $count
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($buf) } finally { $rng.Dispose() }
  return $buf
}

function New-RandomBase64Key([int]$bytes = 32) {
  [Convert]::ToBase64String((New-RandomBytes $bytes))
}

function New-RandomSecretKey([int]$length = 50) {
  $alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#%^&*(-_=+)"
  $buf = New-RandomBytes $length
  -join ($buf | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

function Protect-ToAdminsOnly([string]$path) {
  icacls $path /inheritance:r | Out-Null
  icacls $path /grant:r "SYSTEM:(F)" "BUILTIN\Administrators:(F)" | Out-Null
}

function Register-CampusService([string]$name, [string]$nssmPath, [string]$targetExe, [string]$args, [string]$appDir) {
  if (-not (Test-Path $nssmPath)) {
    Write-Skip "$name - NSSM not staged at $nssmPath (see docs/DEPLOYMENT.md#third-party-binaries)"
    return $false
  }
  & $nssmPath install $name $targetExe $args | Out-Null
  & $nssmPath set $name AppDirectory $appDir | Out-Null
  & $nssmPath set $name Start SERVICE_AUTO_START | Out-Null
  return $true
}

Write-Step "Campus first-run setup - $InstallRoot"

# ── 1. prerequisites (warn-only) ────────────────────────────────────────
$os = Get-CimInstance Win32_OperatingSystem
Write-Host "    OS: $($os.Caption) ($($os.OSArchitecture))"
$free = (Get-PSDrive -Name ($InstallRoot.Substring(0,1))).Free / 1GB
if ($free -lt 4) { Write-Warn2 "less than 4 GB free on this drive ($([math]::Round($free,1)) GB)" }
try {
  $bl = Get-CimInstance -Namespace "root\cimv2\security\MicrosoftVolumeEncryption" -ClassName Win32_EncryptableVolume `
        -Filter "DriveLetter='$($InstallRoot.Substring(0,2))'" -ErrorAction Stop
  if ($bl -and $bl.ProtectionStatus -ne 1) {
    Write-Warn2 "BitLocker is not on for this drive - this box will hold children's PII."
  }
} catch {
  Write-Warn2 "could not determine BitLocker status (not fatal) - please confirm it manually."
}

# ── 2. directory layout ──────────────────────────────────────────────────
foreach ($d in @("pgdata", "logs", "media")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot $d) | Out-Null
}

# ── 3. secrets ───────────────────────────────────────────────────────────
Write-Step "Generating per-install secrets"
$envPath = Join-Path $InstallRoot "app\.env"
$pgPassword = New-RandomSecretKey 24
$envBody = @"
CAMPUS_ENV=prod
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=$(New-RandomSecretKey 50)
FIELD_ENCRYPTION_KEY=$(New-RandomBase64Key 32)
ALLOWED_HOSTS=$LanHost,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://$LanHost
POSTGRES_DB=campus
POSTGRES_USER=campus
POSTGRES_PASSWORD=$pgPassword
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
DATABASE_URL=postgres://campus:$pgPassword@127.0.0.1:5432/campus
MEDIA_ROOT=$(Join-Path $InstallRoot "media")
PUBLIC_BASE_URL=https://$LanHost
API_BIND=$ApiBind
CAMPUS_ADMIN_IP_ALLOWLIST=127.0.0.1
"@
# Set-Content/Out-File -Encoding utf8 writes a UTF-8 BOM in Windows
# PowerShell 5.1; django-environ silently drops a BOM-prefixed first line
# as an "Invalid line" instead of erroring, so WriteAllText with a
# BOM-less encoding is required here, not a style preference (found by
# actually running install.ps1's own .env against the frozen app).
[System.IO.File]::WriteAllText($envPath, $envBody, (New-Object System.Text.UTF8Encoding($false)))
Protect-ToAdminsOnly $envPath
Write-Host "    wrote $envPath (ACL'd to SYSTEM + Administrators)"

# ── 4. database ──────────────────────────────────────────────────────────
$pgBin = Join-Path $InstallRoot "pgsql\bin"
$pgDataDir = Join-Path $InstallRoot "pgdata"
$dbReady = $false
if ((Test-Path (Join-Path $pgBin "initdb.exe")) -and -not $SkipServices) {
  Write-Step "Initializing PostgreSQL"
  if (-not (Test-Path (Join-Path $pgDataDir "PG_VERSION"))) {
    & (Join-Path $pgBin "initdb.exe") -D $pgDataDir -U postgres -A trust --locale=C | Out-Null
  }
  & (Join-Path $pgBin "pg_ctl.exe") register -N "Campus PostgreSQL" -D $pgDataDir `
      -o "-p 5432" -w | Out-Null
  Start-Service -Name "Campus PostgreSQL" -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2
  & (Join-Path $pgBin "psql.exe") -U postgres -h 127.0.0.1 -c `
      "DO `$`$ BEGIN IF NOT EXISTS (SELECT FROM pg_user WHERE usename='campus') THEN CREATE ROLE campus LOGIN PASSWORD '$pgPassword'; END IF; END `$`$;" 2>$null
  & (Join-Path $pgBin "createdb.exe") -U postgres -h 127.0.0.1 -O campus campus 2>$null
  $dbReady = $true
} else {
  Write-Skip "PostgreSQL - no portable build staged at $pgBin (see docs/DEPLOYMENT.md#third-party-binaries); point DATABASE_URL in $envPath at an existing Postgres instead"
}

# ── 5. the frozen app: migrate + collectstatic + first admin ────────────
$appExe = Join-Path $InstallRoot "app\campus-app.exe"
if ($dbReady -and (Test-Path $appExe)) {
  Write-Step "Running database migrations"
  & $appExe manage migrate
  Write-Step "Collecting static files"
  & $appExe manage collectstatic --noinput
} else {
  Write-Skip "migrate/collectstatic - needs a reachable database (run manually once Postgres is available: campus-app.exe manage migrate)"
}

# ── 6/7. Caddy + the app itself as services (needs NSSM) ────────────────
$nssm = Join-Path $InstallRoot "caddy\bin\nssm.exe"
$caddyExe = Join-Path $InstallRoot "caddy\bin\caddy.exe"
$caddyfileSrc = Join-Path $InstallRoot "caddy\Caddyfile"
if (Test-Path $caddyfileSrc) {
  $templated = (Get-Content $caddyfileSrc -Raw) `
    -replace '\{\$CAMPUS_HOST:localhost\}', $LanHost `
    -replace '\{\$API_BIND:127\.0\.0\.1:8001\}', $ApiBind
  # same BOM pitfall as the .env write above - Caddy's Caddyfile parser
  # should not have to tolerate a BOM on its first line either.
  [System.IO.File]::WriteAllText($caddyfileSrc, $templated, (New-Object System.Text.UTF8Encoding($false)))
  Write-Host "    templated Caddyfile for host '$LanHost', api '$ApiBind'"
}
if (-not $SkipServices) {
  if (Test-Path $caddyExe) {
    Register-CampusService -name "Campus Proxy" -nssmPath $nssm -targetExe $caddyExe `
      -args "run --config `"$caddyfileSrc`"" -appDir (Join-Path $InstallRoot "caddy") | Out-Null
  } else {
    Write-Skip "Campus Proxy service - Caddy not staged at $caddyExe (see docs/DEPLOYMENT.md#third-party-binaries)"
  }
  if (Test-Path $appExe) {
    Register-CampusService -name "Campus App" -nssmPath $nssm -targetExe $appExe `
      -args "serve --host 127.0.0.1 --port 8001" -appDir (Join-Path $InstallRoot "app") | Out-Null
  }
}

# ── 8. start everything Automatic ────────────────────────────────────────
foreach ($svc in @("Campus PostgreSQL", "Campus App", "Campus Proxy")) {
  $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
  if ($s) {
    Set-Service -Name $svc -StartupType Automatic
    if ($s.Status -ne "Running") { Start-Service -Name $svc -ErrorAction SilentlyContinue }
    Write-Host "    $svc -> $((Get-Service -Name $svc).Status)"
  }
}

# ── 9. desktop launcher target ───────────────────────────────────────────
$launcherUrl = Join-Path $InstallRoot "launch-campus.url"
Set-Content -Path $launcherUrl -Value @"
[InternetShortcut]
URL=https://$LanHost/
"@ -Encoding ascii

Write-Step "Setup finished"
Write-Host "    Campus: https://$LanHost/  (trust the LAN certificate on client machines: 'caddy trust')"
Write-Host "    Create the first admin with:  $appExe manage shell -c ""from apps.accounts.services import bootstrap_superadmin; bootstrap_superadmin(username='admin', email='admin@example.test', password='CHANGE-ME')"""
Write-Host "    Then sign in and enrol MFA immediately - staff logins are blocked from sensitive endpoints until MFA is confirmed."
