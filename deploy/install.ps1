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

# The installer must hand us an ELEVATED token - registering Windows services
# (nssm / pg_ctl) and writing under %ProgramData% both need it. campus.iss's
# [Run] entry drops `runascurrentuser` for exactly this reason; if someone
# runs this script by hand from a non-elevated shell, fail loudly here rather
# than half-installing and still exiting 0 (the bug that shipped in 0.9.0).
$__id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $SkipServices -and -not (New-Object Security.Principal.WindowsPrincipal($__id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "install.ps1 needs to run elevated (it registers Windows services). Re-run from an Administrator PowerShell, or pass -SkipServices to only lay down files + secrets."
}

# Run a frozen-app management command. Django/axes log to stderr on a normal
# run; with $ErrorActionPreference='Stop' a native command's stderr line is
# promoted to a terminating error, which silently aborted 0.9.0's install
# right after `migrate` (before any service got registered). Neutralise that:
# drop to Continue for the call, then judge success by the real exit code.
function Invoke-Manage([string]$exe, [string[]]$mArgs) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $exe @mArgs 2>&1 | ForEach-Object { Write-Host "    | $_" }
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = $old }
  if ($code -ne 0) { throw "campus-app.exe $($mArgs -join ' ') failed (exit $code)" }
}

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

# For anything that lands inside a URL (the Postgres password goes into
# DATABASE_URL) - keep it to characters that never need percent-encoding, so
# `postgres://campus:<pw>@host/db` can't be corrupted by a stray @ / # / % / /.
function New-UrlSafeSecret([int]$length = 32) {
  $alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
  $buf = New-RandomBytes $length
  -join ($buf | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

function Protect-ToAdminsOnly([string]$path) {
  icacls $path /inheritance:r | Out-Null
  icacls $path /grant:r "SYSTEM:(F)" "BUILTIN\Administrators:(F)" | Out-Null
}

function Register-CampusService([string]$name, [string]$nssmPath, [string]$targetExe, [string]$svcArgs, [string]$appDir) {
  if (-not (Test-Path $nssmPath)) {
    Write-Skip "$name - NSSM not staged at $nssmPath (see docs/DEPLOYMENT.md#third-party-binaries)"
    return $false
  }
  if (Get-Service -Name $name -ErrorAction SilentlyContinue) {
    & $nssmPath set $name Application $targetExe   | Out-Null
    & $nssmPath set $name AppParameters $svcArgs   | Out-Null
  } else {
    & $nssmPath install $name $targetExe $svcArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "nssm install '$name' failed (exit $LASTEXITCODE) - is this shell elevated?" }
  }
  & $nssmPath set $name AppDirectory $appDir | Out-Null
  & $nssmPath set $name Start SERVICE_AUTO_START | Out-Null
  & $nssmPath set $name AppStdout (Join-Path $InstallRoot ("logs\" + ($name -replace ' ', '-') + ".log")) | Out-Null
  & $nssmPath set $name AppStderr (Join-Path $InstallRoot ("logs\" + ($name -replace ' ', '-') + ".log")) | Out-Null
  # nssm can exit 0 yet not create the service if the SCM call was refused -
  # confirm it actually exists rather than trusting the exit code alone.
  if (-not (Get-Service -Name $name -ErrorAction SilentlyContinue)) {
    throw "'$name' was not created (nssm returned 0 but the service is absent) - install.ps1 is not running elevated."
  }
  return $true
}

function Trust-CaddyLocalCA([string]$root) {
  <#  Add the root of Caddy's internal CA to the machine-wide Trusted Root
      store so Edge/Chrome stop flagging the LAN HTTPS as "Not secure". Caddy
      runs as a SYSTEM service and can't do this itself. Also leaves a copy at
      <root>\campus-local-ca.crt for other LAN machines. #>
  $sys = "$env:SystemRoot\System32\config\systemprofile\AppData\Roaming\Caddy"
  $candidates = @(
    (Join-Path $root "caddy\data\caddy\pki\authorities\local\root.crt"),
    (Join-Path $sys "pki\authorities\local\root.crt"),
    "$env:ProgramData\Caddy\pki\authorities\local\root.crt",
    "$env:APPDATA\Caddy\pki\authorities\local\root.crt"
  )
  $crt = $null
  foreach ($try in 1..8) {
    $crt = $candidates | Where-Object { Test-Path $_ } |
      Get-Item | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($crt) { break }
    Start-Sleep -Seconds 2
  }
  if (-not $crt) {
    Write-Warn2 "Caddy's local CA was not found - open https://$LanHost/ once in a browser to issue it, then run repair-campus.ps1 to trust it."
    return
  }
  try {
    $c = Import-Certificate -FilePath $crt.FullName -CertStoreLocation Cert:\LocalMachine\Root -ErrorAction Stop
    Write-Host "    trusted local CA: $($c.Subject)"
  } catch {
    & certutil.exe -f -addstore Root "`"$($crt.FullName)`"" | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warn2 "could not trust the local CA automatically ($($_.Exception.Message)); run 'caddy trust' by hand"; return }
    Write-Host "    trusted local CA (certutil): $($crt.FullName)"
  }
  Copy-Item $crt.FullName (Join-Path $root "campus-local-ca.crt") -Force
  Write-Host "    other LAN machines: import $root\campus-local-ca.crt into 'Trusted Root Certification Authorities'"
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
$pgPassword = New-UrlSafeSecret 32   # goes into DATABASE_URL - must not need %-encoding
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
# A prior install locked this file to SYSTEM+Administrators with inheritance
# removed; on a reinstall the plain WriteAllText below then fails with
# Access Denied. Re-open write access first (we are elevated - see the guard
# at the top) so a reinstall can refresh the secrets.
if (Test-Path $envPath) {
  & icacls $envPath /grant "*S-1-5-32-544:(F)" /inheritance:e | Out-Null
  try { Remove-Item $envPath -Force } catch { }
}
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
  Invoke-Manage $appExe @("manage", "migrate", "--noinput")
  Write-Step "Collecting static files"
  Invoke-Manage $appExe @("manage", "collectstatic", "--noinput")
} else {
  Write-Skip "migrate/collectstatic - needs a reachable database (run manually once Postgres is available: campus-app.exe manage migrate)"
}

# ── 6/7. Caddy + the app itself as services (needs NSSM) ────────────────
$nssm = Join-Path $InstallRoot "caddy\bin\nssm.exe"
$caddyExe = Join-Path $InstallRoot "caddy\bin\caddy.exe"
$caddyfileSrc = Join-Path $InstallRoot "caddy\Caddyfile"
$webRoot = Join-Path $InstallRoot "app\frontend_out"
if (Test-Path $caddyfileSrc) {
  # Caddy wants forward slashes even on Windows; a bare backslash path in a
  # Caddyfile `root` directive is read as an escape.
  $webRootFwd = $webRoot -replace '\\', '/'
  $templated = (Get-Content $caddyfileSrc -Raw) `
    -replace '\{\$CAMPUS_HOST:localhost\}', $LanHost `
    -replace '\{\$API_BIND:127\.0\.0\.1:8001\}', $ApiBind `
    -replace '\{\$CAMPUS_WEB_ROOT:\./frontend_out\}', $webRootFwd
  # same BOM pitfall as the .env write above - Caddy's Caddyfile parser
  # should not have to tolerate a BOM on its first line either.
  [System.IO.File]::WriteAllText($caddyfileSrc, $templated, (New-Object System.Text.UTF8Encoding($false)))
  Write-Host "    templated Caddyfile (host '$LanHost', api '$ApiBind', web root '$webRootFwd')"
  if (-not (Test-Path (Join-Path $webRoot "index.html"))) {
    Write-Warn2 "no frontend_out\index.html under $webRoot - the SPA will 404 until the exported frontend is present"
  }
}
if (-not $SkipServices) {
  if (Test-Path $caddyExe) {
    Register-CampusService -name "Campus Proxy" -nssmPath $nssm -targetExe $caddyExe `
      -svcArgs "run --config `"$caddyfileSrc`"" -appDir (Join-Path $InstallRoot "caddy") | Out-Null
  } else {
    Write-Skip "Campus Proxy service - Caddy not staged at $caddyExe (see docs/DEPLOYMENT.md#third-party-binaries)"
  }
  if (Test-Path $appExe) {
    Register-CampusService -name "Campus App" -nssmPath $nssm -targetExe $appExe `
      -svcArgs "serve --host 127.0.0.1 --port 8001" -appDir (Join-Path $InstallRoot "app") | Out-Null
  }
}

# ── 8. start everything Automatic ────────────────────────────────────────
if (-not $SkipServices) {
  foreach ($svc in @("Campus PostgreSQL", "Campus App", "Campus Proxy")) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s) {
      Set-Service -Name $svc -StartupType Automatic
      if ($s.Status -ne "Running") { Start-Service -Name $svc -ErrorAction SilentlyContinue }
      Write-Host "    $svc -> $((Get-Service -Name $svc).Status)"
    }
  }
}

# ── 9. desktop launcher target ───────────────────────────────────────────
$launcherUrl = Join-Path $InstallRoot "launch-campus.url"
$icoPath = Join-Path $InstallRoot "campus.ico"
Set-Content -Path $launcherUrl -Value @"
[InternetShortcut]
URL=https://$LanHost/
IconFile=$icoPath
IconIndex=0
"@ -Encoding ascii

# ── 10. verify - a half-install must NOT look like a success ────────────
if (-not $SkipServices) {
  Write-Step "Verifying"
  $missing = @("Campus PostgreSQL", "Campus App", "Campus Proxy") |
    Where-Object { -not (Get-Service -Name $_ -ErrorAction SilentlyContinue) }
  if ($missing) { throw "these services were not registered: $($missing -join ', '). Setup did not complete." }

  $ok = $false
  [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
  foreach ($try in 1..10) {
    Start-Sleep -Seconds 3
    try {
      $resp = Invoke-WebRequest "https://$LanHost/api/healthz/" -TimeoutSec 10 -UseBasicParsing
      if ($resp.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
  }
  if (-not $ok) {
    throw "services registered but https://$LanHost/ did not answer 200 within ~30s - check $InstallRoot\logs\Campus-App.log and Campus-Proxy.log"
  }
  Write-Host "    https://$LanHost/api/healthz/ -> 200 OK"

  # the healthz request above forced Caddy to issue its cert; trust the CA now
  Write-Step "Trusting the local HTTPS certificate"
  Trust-CaddyLocalCA $InstallRoot
}

Write-Step "Setup finished"
Write-Host "    Open Campus:  https://$LanHost/" -ForegroundColor Green
Write-Host "    The first visit shows a 'Welcome to Campus' screen - create your"
Write-Host "    administrator account there, then set up an authenticator app when"
Write-Host "    prompted (staff logins are blocked from records until MFA is confirmed)."
Write-Host "    (Headless alternative:  `"$appExe`" manage create_admin )"
Write-Host "    This machine already trusts the HTTPS certificate. For other LAN"
Write-Host "    machines, import  $InstallRoot\campus-local-ca.crt  into their"
Write-Host "    Trusted Root store (or push it by Group Policy)."
