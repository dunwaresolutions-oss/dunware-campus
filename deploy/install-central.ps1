<#
  Campus Central - first-run setup. Invoked by the Inno Setup installer
  (deploy/central.iss [Run] section) right after files are laid out under
  $InstallRoot (default %ProgramData%\CampusCentral); safe to re-run by hand
  too. Mirrors deploy/install.ps1 (Campus's own) structure and every
  already-proven fix in it (BOM-free secret/Caddyfile writes, the elevation
  guard, the nssm exit-code double-check, the HTTP-only verify probe) --
  this is the SAME install pattern, a second, independent product.

  What this does, in order:
    1. Prerequisite checks (warn-only): OS, free disk, BitLocker (Central
       holds synced copies of real student/guardian PII too - same warning
       as Campus's own, same reason).
    2. Lay out $InstallRoot\{pgdata,logs,media_central,app\hotfix}.
    3. Generate per-install secrets into $InstallRoot\app\.env.central
       (CENTRAL_SECRET_KEY, CENTRAL_FIELD_ENCRYPTION_KEY, Postgres password),
       ACL'd to SYSTEM + Administrators only. Deliberately a DIFFERENT
       filename from Campus's own .env (central/settings/base.py reads
       .env.central specifically) so the two can never be confused if ever
       staged on the same machine.
    4. initdb + register "Campus Central PostgreSQL" on port 5433 (not
       5432) - ONLY if a portable Postgres is staged at
       $InstallRoot\pgsql\bin. 5433 is a deliberate choice, not Postgres's
       default: a Ministry test box running both a Campus install (for
       support/demo purposes) and Campus Central side by side must never
       have the two collide on the same port. Otherwise: clear message,
       skip, continue.
    5. central-app.exe manage migrate / collectstatic.
    6. Template the Caddyfile (deploy/proxy/central-caddyfile) with the
       chosen host; register "Campus Central Proxy" - needs Caddy + NSSM.
    7. Register "Campus Central App" (central-app.exe serve) - needs NSSM.
       No scheduler service: Central has no django_q / Q_CLUSTER of its own
       (central/settings/base.py's INSTALLED_APPS has no django_q) - that
       gap is Campus-side only (see install.ps1's "Campus Scheduler").
    8. Set every registered service to Automatic and start it.
    9. Drop a Start Menu / Desktop launcher target.
   10. Print the URL + a health check, or the plain list of manual
       follow-up steps if any binary was missing.
    11. Trust Caddy's local CA.

  Every step degrades to "print what's missing and continue" rather than
  crashing setup - the third-party binaries (portable PostgreSQL, Caddy,
  NSSM) are the SAME ones staged for Campus at deploy/_thirdparty/ (they are
  generic, not Campus-specific), so a checkout that has already staged them
  for a Campus build needs nothing extra staged for Central.

  Central has no backup/restore tooling yet (Campus's backup.ps1/restore.ps1
  are Campus-specific scripts with no Central equivalent built) - that
  remains an open, unbuilt item, not silently assumed to exist.
#>
param(
  [string]$InstallRoot = "$env:ProgramData\CampusCentral",
  [string]$CentralHost = "localhost",
  [string]$ApiBind = "127.0.0.1:8002",
  # NOT 443 -- Caddy's admin API also always binds a fixed 127.0.0.1:2019
  # regardless of this value (see proxy/central-caddyfile's own comment);
  # that -- not this port choice alone -- is what actually broke a real
  # co-located Campus+Central test box (confirmed 2026-10-09): "Campus
  # Central Proxy" crashed on startup, "Campus Proxy" kept 443/80, and the
  # browser silently got served Campus's OWN frontend for every request.
  [string]$WebPort = "8443",
  [switch]$SkipServices
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Warn2($msg) { Write-Host "    ! $msg" -ForegroundColor Yellow }
function Write-Skip($msg) { Write-Host "    - skipped: $msg" -ForegroundColor DarkYellow }

$__id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $SkipServices -and -not (New-Object Security.Principal.WindowsPrincipal($__id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "install-central.ps1 needs to run elevated (it registers Windows services). Re-run from an Administrator PowerShell, or pass -SkipServices to only lay down files + secrets."
}

function Invoke-Manage([string]$exe, [string[]]$mArgs) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $exe @mArgs 2>&1 | ForEach-Object { Write-Host "    | $_" }
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = $old }
  if ($code -ne 0) { throw "central-app.exe $($mArgs -join ' ') failed (exit $code)" }
}

function New-RandomBytes([int]$count) {
  $buf = New-Object byte[] $count
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($buf) } finally { $rng.Dispose() }
  return $buf
}
function New-RandomBase64Key([int]$bytes = 32) { [Convert]::ToBase64String((New-RandomBytes $bytes)) }
function New-RandomSecretKey([int]$length = 50) {
  $alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#%^&*(-_=+)"
  $buf = New-RandomBytes $length
  -join ($buf | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}
function New-UrlSafeSecret([int]$length = 32) {
  $alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
  $buf = New-RandomBytes $length
  -join ($buf | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}
function Protect-ToAdminsOnly([string]$path) {
  icacls $path /inheritance:r | Out-Null
  icacls $path /grant:r "SYSTEM:(F)" "BUILTIN\Administrators:(F)" | Out-Null
}

function Register-CentralService([string]$name, [string]$nssmPath, [string]$targetExe, [string]$svcArgs, [string]$appDir) {
  if (-not (Test-Path $nssmPath)) {
    Write-Skip "$name - NSSM not staged at $nssmPath (see docs/PACKAGING.md#third-party-binaries)"
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
  if (-not (Get-Service -Name $name -ErrorAction SilentlyContinue)) {
    throw "'$name' was not created (nssm returned 0 but the service is absent) - install-central.ps1 is not running elevated."
  }
  return $true
}

function Trust-CaddyLocalCA([string]$root) {
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
    Write-Warn2 "Caddy's local CA was not found - open https://$CentralHost/ once in a browser to issue it, then run repair-campus-central.ps1 to trust it."
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
  Copy-Item $crt.FullName (Join-Path $root "campus-central-local-ca.crt") -Force
  Write-Host "    other LAN machines: import $root\campus-central-local-ca.crt into 'Trusted Root Certification Authorities'"
}

Write-Step "Campus Central first-run setup - $InstallRoot"

# ── 1. prerequisites (warn-only) ────────────────────────────────────────
$os = Get-CimInstance Win32_OperatingSystem
Write-Host "    OS: $($os.Caption) ($($os.OSArchitecture))"
$free = (Get-PSDrive -Name ($InstallRoot.Substring(0,1))).Free / 1GB
if ($free -lt 4) { Write-Warn2 "less than 4 GB free on this drive ($([math]::Round($free,1)) GB)" }
try {
  $bl = Get-CimInstance -Namespace "root\cimv2\security\MicrosoftVolumeEncryption" -ClassName Win32_EncryptableVolume `
        -Filter "DriveLetter='$($InstallRoot.Substring(0,2))'" -ErrorAction Stop
  if ($bl -and $bl.ProtectionStatus -ne 1) {
    Write-Warn2 "BitLocker is not on for this drive - Central holds synced copies of real students' PII across every linked school."
  }
} catch {
  Write-Warn2 "could not determine BitLocker status (not fatal) - please confirm it manually."
}

# ── 2. directory layout ──────────────────────────────────────────────────
foreach ($d in @("pgdata", "logs", "media_central", "app\hotfix", "backups", "gpg\home")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot $d) | Out-Null
}
# GNUPGHOME for the bundled gpg (backup-central.ps1/restore-central.ps1 set
# it themselves); only agent sockets / a scratch keybox land here, but lock
# it down anyway, same as Campus's own install.ps1 does.
Protect-ToAdminsOnly (Join-Path $InstallRoot "gpg\home")
Protect-ToAdminsOnly (Join-Path $InstallRoot "backups")

# ── 3. secrets ───────────────────────────────────────────────────────────
Write-Step "Generating per-install secrets"
$envPath = Join-Path $InstallRoot "app\.env.central"
$pgPassword = New-UrlSafeSecret 32
$envBody = @"
CAMPUS_ENV=prod
DJANGO_SETTINGS_MODULE=central.settings.prod
CENTRAL_SECRET_KEY=$(New-RandomSecretKey 50)
CENTRAL_FIELD_ENCRYPTION_KEY=$(New-RandomBase64Key 32)
ALLOWED_HOSTS=$CentralHost,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://${CentralHost}:${WebPort}
CENTRAL_DATABASE_URL=postgres://campus_central:$pgPassword@127.0.0.1:5433/campus_central
CENTRAL_MEDIA_ROOT=$(Join-Path $InstallRoot "media_central")
API_BIND=$ApiBind
CAMPUS_ADMIN_IP_ALLOWLIST=127.0.0.1
"@
if (Test-Path $envPath) {
  & icacls $envPath /grant "*S-1-5-32-544:(F)" /inheritance:e | Out-Null
  try { Remove-Item $envPath -Force } catch { }
}
# Same BOM pitfall as Campus's own install.ps1 (django-environ silently drops
# a BOM-prefixed first line as an "Invalid line" rather than erroring) -
# WriteAllText with a BOM-less encoding, not Set-Content, is required.
[System.IO.File]::WriteAllText($envPath, $envBody, (New-Object System.Text.UTF8Encoding($false)))
Protect-ToAdminsOnly $envPath
Write-Host "    wrote $envPath (ACL'd to SYSTEM + Administrators)"

# ── 4. database ──────────────────────────────────────────────────────────
$pgBin = Join-Path $InstallRoot "pgsql\bin"
$pgDataDir = Join-Path $InstallRoot "pgdata"
$dbReady = $false
if ((Test-Path (Join-Path $pgBin "initdb.exe")) -and -not $SkipServices) {
  Write-Step "Initializing PostgreSQL (port 5433 - deliberately not 5432, so a Campus install on the same box never collides)"
  if (-not (Test-Path (Join-Path $pgDataDir "PG_VERSION"))) {
    & (Join-Path $pgBin "initdb.exe") -D $pgDataDir -U postgres -A trust --locale=C | Out-Null
  }
  & (Join-Path $pgBin "pg_ctl.exe") register -N "Campus Central PostgreSQL" -D $pgDataDir `
      -o "-p 5433" -w | Out-Null
  Start-Service -Name "Campus Central PostgreSQL" -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2
  & (Join-Path $pgBin "psql.exe") -U postgres -h 127.0.0.1 -p 5433 -c `
      "DO `$`$ BEGIN IF NOT EXISTS (SELECT FROM pg_user WHERE usename='campus_central') THEN CREATE ROLE campus_central LOGIN PASSWORD '$pgPassword'; END IF; END `$`$;" 2>$null
  & (Join-Path $pgBin "createdb.exe") -U postgres -h 127.0.0.1 -p 5433 -O campus_central campus_central 2>$null
  $dbReady = $true
} else {
  Write-Skip "PostgreSQL - no portable build staged at $pgBin (see docs/PACKAGING.md#third-party-binaries); point CENTRAL_DATABASE_URL in $envPath at an existing Postgres instead"
}

# ── 5. the frozen app: migrate + collectstatic ──────────────────────────
$appExe = Join-Path $InstallRoot "app\central-app.exe"
if ($dbReady -and (Test-Path $appExe)) {
  Write-Step "Running database migrations"
  Invoke-Manage $appExe @("manage", "migrate", "--noinput")
  Write-Step "Collecting static files"
  Invoke-Manage $appExe @("manage", "collectstatic", "--noinput")
} else {
  Write-Skip "migrate/collectstatic - needs a reachable database (run manually once Postgres is available: central-app.exe manage migrate)"
}

# ── 5b. gpg for encrypted backups (warn-only) ────────────────────────────
$gpgExe = Join-Path $InstallRoot "gpg\bin\gpg.exe"
if (Test-Path $gpgExe) {
  $env:GNUPGHOME = Join-Path $InstallRoot "gpg\home"
  $gpgVer = (& $gpgExe --version 2>$null | Select-Object -First 1)
  Write-Host "    bundled gpg: $gpgVer  (GNUPGHOME $($env:GNUPGHOME))"
} elseif (Get-Command gpg -ErrorAction SilentlyContinue) {
  Write-Host "    gpg: using the copy on PATH ($((Get-Command gpg).Source))"
} else {
  Write-Warn2 "no gpg bundled at $gpgExe and none on PATH - encrypted backups (scripts\backup-central.ps1) will not run until GnuPG is staged (see docs/PACKAGING.md#third-party-binaries)"
}

# ── 6/7. Caddy + the app itself as services (needs NSSM) ────────────────
$nssm = Join-Path $InstallRoot "caddy\bin\nssm.exe"
$caddyExe = Join-Path $InstallRoot "caddy\bin\caddy.exe"
$caddyfileSrc = Join-Path $InstallRoot "caddy\Caddyfile"
$caddyfileTpl = Join-Path $InstallRoot "caddy\Caddyfile.template"
$webRoot = Join-Path $InstallRoot "app\frontend_central_out"
if (-not (Test-Path $caddyfileSrc) -and (Test-Path $caddyfileTpl)) {
  Copy-Item $caddyfileTpl $caddyfileSrc -Force
  Write-Host "    seeded caddy\Caddyfile from Caddyfile.template"
}
if (Test-Path $caddyfileSrc) {
  $webRootFwd = $webRoot -replace '\\', '/'
  $templated = (Get-Content $caddyfileSrc -Raw) `
    -replace '\{\$CENTRAL_HOST:localhost\}', $CentralHost `
    -replace '\{\$CENTRAL_WEB_PORT:8443\}', $WebPort `
    -replace '\{\$CENTRAL_API_BIND:127\.0\.0\.1:8002\}', $ApiBind `
    -replace '\{\$CENTRAL_WEB_ROOT:\./frontend_central_out\}', $webRootFwd
  [System.IO.File]::WriteAllText($caddyfileSrc, $templated, (New-Object System.Text.UTF8Encoding($false)))
  Write-Host "    templated Caddyfile (host '$CentralHost`:$WebPort', api '$ApiBind', web root '$webRootFwd')"
  if (-not (Test-Path (Join-Path $webRoot "index.html"))) {
    Write-Warn2 "no frontend_central_out\index.html under $webRoot - the SPA will 404 until the exported frontend is present"
  }
}
if (-not $SkipServices) {
  if (Test-Path $caddyExe) {
    Register-CentralService -name "Campus Central Proxy" -nssmPath $nssm -targetExe $caddyExe `
      -svcArgs "run --config `"$caddyfileSrc`"" -appDir (Join-Path $InstallRoot "caddy") | Out-Null
  } else {
    Write-Skip "Campus Central Proxy service - Caddy not staged at $caddyExe (see docs/PACKAGING.md#third-party-binaries)"
  }
  if (Test-Path $appExe) {
    Register-CentralService -name "Campus Central App" -nssmPath $nssm -targetExe $appExe `
      -svcArgs "serve --host 127.0.0.1 --port 8002" -appDir (Join-Path $InstallRoot "app") | Out-Null
  }
}

# ── 8. start everything Automatic ────────────────────────────────────────
if (-not $SkipServices) {
  foreach ($svc in @("Campus Central PostgreSQL", "Campus Central App", "Campus Central Proxy")) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s) {
      Set-Service -Name $svc -StartupType Automatic
      if ($s.Status -ne "Running") { Start-Service -Name $svc -ErrorAction SilentlyContinue }
      Write-Host "    $svc -> $((Get-Service -Name $svc).Status)"
    }
  }
}

# ── 9. desktop launcher target ───────────────────────────────────────────
$launcherUrl = Join-Path $InstallRoot "launch-campus-central.url"
$icoPath = Join-Path $InstallRoot "campus.ico"
Set-Content -Path $launcherUrl -Value @"
[InternetShortcut]
URL=https://$CentralHost`:$WebPort/
IconFile=$icoPath
IconIndex=0
"@ -Encoding ascii

# ── 10. verify - a half-install must NOT look like a success ────────────
if (-not $SkipServices) {
  Write-Step "Verifying"
  $missing = @("Campus Central PostgreSQL", "Campus Central App", "Campus Central Proxy") |
    Where-Object { -not (Get-Service -Name $_ -ErrorAction SilentlyContinue) }
  if ($missing) { throw "these services were not registered: $($missing -join ', '). Setup did not complete." }

  $down = @("Campus Central PostgreSQL", "Campus Central App", "Campus Central Proxy") |
    Where-Object { (Get-Service -Name $_).Status -ne "Running" }
  if ($down) { Write-Warn2 "not Running yet: $($down -join ', ') - give them a moment, or check $InstallRoot\logs\" }

  # No plain-HTTP companion on $WebPort (Central is an internal admin
  # console, not parent-facing like Campus) - probe the HTTPS port directly
  # with curl's own -k (self-signed `tls internal` cert) instead of a
  # redirect-based check.
  $curl = Join-Path $env:SystemRoot "System32\curl.exe"
  $httpCode = $null
  if (Test-Path $curl) {
    foreach ($try in 1..8) {
      Start-Sleep -Seconds 2
      $httpCode = (& $curl -s -k -o NUL -w "%{http_code}" --max-time 6 "https://${CentralHost}:${WebPort}/") 2>$null
      if ($httpCode -match '^(200|301|302|308)$') { break }
    }
  }
  $tlsPort = $false
  try { $tlsPort = (Test-NetConnection -ComputerName $CentralHost -Port $WebPort -InformationLevel Quiet -WarningAction SilentlyContinue) } catch {}
  Write-Host "    Caddy https://${CentralHost}:${WebPort}/ -> $httpCode   |   :$WebPort listening: $tlsPort"
  if (-not (($httpCode -match '^(200|301|302|308)$') -and $tlsPort)) {
    Write-Warn2 "the HTTPS check was inconclusive - open https://${CentralHost}:${WebPort}/ in Chrome or Edge to confirm; logs are in $InstallRoot\logs\"
  }

  Write-Step "Trusting the local HTTPS certificate"
  try { Trust-CaddyLocalCA $InstallRoot }
  catch { Write-Warn2 "could not trust the local CA ($($_.Exception.Message)); run repair-campus-central.ps1 later, or 'caddy trust'" }
}

Write-Step "Setup finished"
Write-Host "    Open Campus Central:  https://${CentralHost}:${WebPort}/" -ForegroundColor Green
Write-Host "    The first visit shows a 'Welcome' screen - create the first Ministry"
Write-Host "    account there (break-glass SUPERADMIN), then set up an authenticator"
Write-Host "    app when prompted."
Write-Host "    This machine already trusts the HTTPS certificate. For other"
Write-Host "    machines, import  $InstallRoot\campus-central-local-ca.crt  into their"
Write-Host "    Trusted Root store."
Write-Host "    Register a school:  & '$appExe' manage register_school --name ""...""   "
Write-Host "    (prints the one-time sync token to paste into that school's own"
Write-Host "    Campus - Central Link Setup)."
