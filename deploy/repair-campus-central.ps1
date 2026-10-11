<#
  repair-campus-central.ps1  --  fix a Campus Central install that came up
  wrong, or push a day-2 refresh. Mirrors deploy/repair-campus.ps1 (Campus's
  own) structure and fixes exactly - same two failure modes are possible
  here (non-elevated install -> missing services; a Caddyfile proxying /
  straight to Django -> 404), so the same repair script shape applies.

  RUN AS ADMINISTRATOR:
    powershell -ExecutionPolicy Bypass -File <path>\repair-campus-central.ps1

  Optional in-place update of an existing install without a full reinstall:
    -RefreshFrontendFrom <repo>\frontend_central\out    swap the exported SPA
    -RefreshAppFrom      <repo>\dist\central-app         swap the frozen backend
    -RefreshScriptsFrom  <repo>\deploy                   swap the day-2 *.ps1 scripts
  All keep .env.central and the database; -RefreshAppFrom re-runs migrate +
  collectstatic.

  Idempotent - safe to run again.
#>
param(
  [string]$InstallRoot = "$env:ProgramData\CampusCentral",
  [string]$RefreshFrontendFrom,
  [string]$RefreshAppFrom,
  [string]$RefreshScriptsFrom
)

$ErrorActionPreference = "Stop"
function Step($m){ Write-Host "==> $m" -ForegroundColor Cyan }
function Info($m){ Write-Host "    $m" }
function Warn($m){ Write-Host "    ! $m" -ForegroundColor Yellow }

function Trust-CaddyLocalCA {
  param([Parameter(Mandatory)][string]$InstallRoot)
  $sys = "$env:SystemRoot\System32\config\systemprofile\AppData\Roaming\Caddy"
  $candidates = @(
    (Join-Path $InstallRoot "caddy\data\caddy\pki\authorities\local\root.crt"),
    (Join-Path $sys "pki\authorities\local\root.crt"),
    "$env:ProgramData\Caddy\pki\authorities\local\root.crt",
    "$env:APPDATA\Caddy\pki\authorities\local\root.crt",
    "$env:LOCALAPPDATA\Caddy\pki\authorities\local\root.crt"
  )
  $root = $null
  foreach ($try in 1..8) {
    $root = $candidates | Where-Object { Test-Path $_ } |
      Get-Item | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($root) { break }
    Start-Sleep 2
  }
  if (-not $root) {
    Warn "Caddy's local CA (pki\authorities\local\root.crt) was not found yet."
    Warn "Open https:// once in a browser to make Caddy issue it, then re-run this script."
    return
  }
  try {
    $imported = Import-Certificate -FilePath $root.FullName `
      -CertStoreLocation Cert:\LocalMachine\Root -ErrorAction Stop
    Info "trusted: $($imported.Subject)  (thumbprint $($imported.Thumbprint))"
  } catch {
    & certutil.exe -f -addstore Root "`"$($root.FullName)`"" | Out-Null
    if ($LASTEXITCODE -ne 0) { Warn "could not add the CA to the trust store ($($_.Exception.Message))"; return }
    Info "trusted via certutil: $($root.FullName)"
  }
  $shareCopy = Join-Path $InstallRoot "campus-central-local-ca.crt"
  Copy-Item $root.FullName $shareCopy -Force
  Info "copy for other machines: $shareCopy"
}

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Not elevated. Re-run this from an Administrator PowerShell."
}

$app   = Join-Path $InstallRoot "app\central-app.exe"
$nssm  = Join-Path $InstallRoot "caddy\bin\nssm.exe"
$caddy = Join-Path $InstallRoot "caddy\bin\caddy.exe"
$cfile = Join-Path $InstallRoot "caddy\Caddyfile"
$pgBin = Join-Path $InstallRoot "pgsql\bin"
$envf  = Join-Path $InstallRoot "app\.env.central"
$webRoot = Join-Path $InstallRoot "app\frontend_central_out"
foreach ($p in @($app,$nssm,$caddy,$pgBin,$envf)) {
  if (-not (Test-Path $p)) { throw "missing expected path: $p" }
}
$CentralHost = "localhost"
$ApiBind = "127.0.0.1:8002"
# NOT 443 -- see proxy/central-caddyfile's own comment: Caddy's admin API
# also always binds a fixed 127.0.0.1:2019 regardless of this value, which
# is what actually crashed "Campus Central Proxy" on a real co-located
# Campus+Central box (confirmed 2026-10-09) while Campus's own Caddy kept
# 443/80 -- every request silently fell through to Campus's own frontend.
$WebPort = "8443"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# --- 0. .env.central sanity + BOM strip ---------------------------------
Step "Checking app\.env.central"
$envText = Get-Content $envf -Raw
foreach ($k in @("CENTRAL_SECRET_KEY","CENTRAL_FIELD_ENCRYPTION_KEY","CENTRAL_DATABASE_URL")) {
  if ($envText -notmatch "(?m)^\s*$k\s*=\s*\S") { throw ".env.central is missing $k - the install's secret step did not complete. Reinstall." }
}
Info ".env.central has CENTRAL_SECRET_KEY / CENTRAL_FIELD_ENCRYPTION_KEY / CENTRAL_DATABASE_URL"
$bytes = [System.IO.File]::ReadAllBytes($envf)
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
  [System.IO.File]::WriteAllText($envf, $envText, $utf8NoBom)
  Info "removed a UTF-8 BOM from .env.central"
}

# --- 1. database reachable (port 5433 - see install-central.ps1) --------
Step "Checking PostgreSQL"
if (-not (Get-Service "Campus Central PostgreSQL" -ErrorAction SilentlyContinue)) { throw "'Campus Central PostgreSQL' service missing - reinstall." }
if ((Get-Service "Campus Central PostgreSQL").Status -ne "Running") { Start-Service "Campus Central PostgreSQL"; Start-Sleep 3 }
$mig = (& (Join-Path $pgBin "psql.exe") -U postgres -h 127.0.0.1 -p 5433 -d campus_central -tAc "SELECT count(*) FROM django_migrations;" 2>$null | Select-Object -First 1)
if ($mig) { $mig = $mig.Trim() }
Info "django_migrations rows: $mig"
if (-not $mig -or [int]$mig -lt 1) {
  Step "Applying migrations (none were present)"
  $ErrorActionPreference = "Continue"
  & $app manage migrate --noinput
  & $app manage collectstatic --noinput
  $ErrorActionPreference = "Stop"
}

# --- 2. Caddyfile: rewrite to the SPA-serving layout ------------------
Step "Writing Caddyfile (Caddy serves the SPA off disk; only /api /admin /static /media proxy to Django)"
$webRootFwd = ($webRoot -replace '\\','/')
if (-not (Test-Path (Join-Path $webRoot "index.html"))) {
  Warn "no index.html under $webRoot - the SPA can't be served. The exported frontend_central build is missing."
}
$caddyfile = @"
{
	admin off
	auto_https disable_redirects
	skip_install_trust
}

${CentralHost}:${WebPort} {
	encode gzip zstd

	@dynamic path /api/* /admin/* /static/* /media/*
	handle @dynamic {
		reverse_proxy $ApiBind
	}

	handle {
		root * $webRootFwd
		try_files {path} {path}/index.html {path}.html /index.html
		file_server
	}

	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		Referrer-Policy "same-origin"
	}

	tls internal
}
"@
[System.IO.File]::WriteAllText($cfile, $caddyfile, $utf8NoBom)
$ErrorActionPreference = "Continue"
& $caddy validate --config $cfile --adapter caddyfile 2>$null | Out-Null
$caddyRc = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($caddyRc -eq 0) { Info "Caddyfile is valid" }
else { Warn "caddy validate exit $caddyRc - the Caddyfile may be wrong; continuing" }

# --- 3. (re)register the two app-side services ----------------------
function Ensure-Service($name, $exe, $svcArgs, $dir) {
  if (Get-Service $name -ErrorAction SilentlyContinue) {
    Info "$name exists - reconfiguring"
    & $nssm set $name Application $exe       | Out-Null
    & $nssm set $name AppParameters $svcArgs | Out-Null
    & $nssm set $name AppDirectory $dir      | Out-Null
  } else {
    & $nssm install $name $exe $svcArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "nssm install $name failed (exit $LASTEXITCODE)" }
    & $nssm set $name AppDirectory $dir | Out-Null
    Info "$name installed"
  }
  & $nssm set $name Start SERVICE_AUTO_START | Out-Null
  & $nssm set $name AppStdout (Join-Path $InstallRoot ("logs\" + ($name -replace ' ','-') + ".log")) | Out-Null
  & $nssm set $name AppStderr (Join-Path $InstallRoot ("logs\" + ($name -replace ' ','-') + ".log")) | Out-Null
  if (-not (Get-Service $name -ErrorAction SilentlyContinue)) { throw "$name still absent after nssm install" }
}
Step "Registering Campus Central App"
Ensure-Service "Campus Central App" $app "serve --host 127.0.0.1 --port 8002" (Join-Path $InstallRoot "app")
Step "Registering Campus Central Proxy"
Ensure-Service "Campus Central Proxy" $caddy ("run --config `"$cfile`"") (Join-Path $InstallRoot "caddy")

# --- 3a0. swap in a freshly-frozen backend, if asked -------------
if ($RefreshAppFrom) {
  Step "Refreshing the app (frozen backend) from $RefreshAppFrom"
  if (-not (Test-Path (Join-Path $RefreshAppFrom "central-app.exe"))) {
    throw "no central-app.exe under $RefreshAppFrom - build it first (cd backend; pyinstaller ..\deploy\central.spec --distpath ..\dist)"
  }
  $appDir = Join-Path $InstallRoot "app"
  foreach ($svc in @("Campus Central Proxy","Campus Central App")) {
    if ((Get-Service $svc -EA SilentlyContinue).Status -eq "Running") { Stop-Service $svc -Force; Start-Sleep 1 }
  }
  & robocopy $RefreshAppFrom $appDir /MIR /XF ".env.central" /XD (Join-Path $appDir "frontend_central_out") (Join-Path $appDir "media_central") (Join-Path $appDir "staticfiles_central") /NFL /NDL /NJH /NP /R:2 /W:2 | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }
  Info "app updated ($((Get-ChildItem $appDir -Recurse -File).Count) files)"
  $ErrorActionPreference = "Continue"
  & $app manage migrate --noinput
  & $app manage collectstatic --noinput
  $ErrorActionPreference = "Stop"
}

# --- 3a. refresh the exported frontend, if asked ------------------
if ($RefreshFrontendFrom) {
  Step "Refreshing the frontend export from $RefreshFrontendFrom"
  if (-not (Test-Path (Join-Path $RefreshFrontendFrom "index.html"))) {
    throw "no index.html under $RefreshFrontendFrom - build it first (cd frontend_central; npm run build)"
  }
  if ((Get-Service "Campus Central Proxy" -EA SilentlyContinue).Status -eq "Running") {
    Stop-Service "Campus Central Proxy" -Force
    Start-Sleep 1
  }
  & robocopy $RefreshFrontendFrom $webRoot /MIR /NFL /NDL /NJH /NP /R:2 /W:2 | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }
  Info "frontend_central_out updated ($((Get-ChildItem $webRoot -Recurse -File).Count) files)"
}

# --- 3a1. refresh the day-2 deploy scripts, if asked -------------
if ($RefreshScriptsFrom) {
  Step "Refreshing day-2 scripts from $RefreshScriptsFrom"
  if (-not (Test-Path (Join-Path $RefreshScriptsFrom "install-central.ps1"))) {
    throw "no install-central.ps1 under $RefreshScriptsFrom - point this at the repo's deploy\ directory"
  }
  $scriptsDir = Join-Path $InstallRoot "scripts"
  New-Item -ItemType Directory -Force -Path $scriptsDir | Out-Null
  & robocopy $RefreshScriptsFrom $scriptsDir *.ps1 /NFL /NDL /NJH /NP /R:2 /W:2 | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }
  Info ("scripts updated: {0}" -f ((Get-ChildItem $scriptsDir -Filter *.ps1 | ForEach-Object Name) -join ', '))
}

# --- 4. restart everything (Caddyfile changed) --------------------
Step "Restarting services"
foreach ($svc in @("Campus Central PostgreSQL","Campus Central App","Campus Central Proxy")) {
  Set-Service -Name $svc -StartupType Automatic
  if ((Get-Service $svc).Status -eq "Running" -and $svc -ne "Campus Central PostgreSQL") { Restart-Service $svc -Force }
  elseif ((Get-Service $svc).Status -ne "Running") { Start-Service $svc }
  Start-Sleep 1
  Info ("{0,-24} {1}" -f $svc, (Get-Service $svc).Status)
}

# --- 4b. trust Caddy's local CA ----------------------------------
Step "Trusting the local HTTPS certificate on this machine"
Trust-CaddyLocalCA -InstallRoot $InstallRoot

# --- 5. health check ----------------------------------------------
Step "Health check"
$curlExe = Join-Path $env:SystemRoot "System32\curl.exe"
$svcDown = @("Campus Central PostgreSQL","Campus Central App","Campus Central Proxy") |
  Where-Object { (Get-Service $_ -EA SilentlyContinue).Status -ne "Running" }

$httpCode = $null
if (Test-Path $curlExe) {
  foreach ($try in 1..8) {
    Start-Sleep 2
    $httpCode = (& $curlExe -s -k -o NUL -w "%{http_code}" --max-time 8 "https://${CentralHost}:${WebPort}/") 2>$null
    if ($httpCode -match '^(200|301|302|308)$') { break }
  }
  Info "Caddy   https://${CentralHost}:${WebPort}/  -> $httpCode"
}

$tlsPort = $false
try { $tlsPort = (Test-NetConnection -ComputerName $CentralHost -Port $WebPort -InformationLevel Quiet -WarningAction SilentlyContinue) } catch {}
Info ("Port $WebPort listening: {0}" -f $tlsPort)

Write-Host ""
$caddyServing = ($httpCode -match '^(200|301|302|308)$')
if ($svcDown.Count -eq 0 -and $caddyServing -and $tlsPort) {
  Write-Host "  Campus Central is up. Open it in a browser:  https://${CentralHost}:${WebPort}/" -ForegroundColor Green
} elseif ($svcDown.Count -eq 0) {
  Write-Host "  All three services are Running and Caddy is listening, but the probe was inconclusive." -ForegroundColor Yellow
  Write-Host "  Open https://${CentralHost}:${WebPort}/ in Chrome or Edge - that is the real test. If it fails, check:" -ForegroundColor Yellow
  Write-Host "    $InstallRoot\logs\Campus-Central-App.log"
  Write-Host "    $InstallRoot\logs\Campus-Central-Proxy.log"
} else {
  Warn ("not Running: {0} - check {1}\logs\Campus-Central-App.log and {1}\logs\Campus-Central-Proxy.log" -f ($svcDown -join ', '), $InstallRoot)
}
