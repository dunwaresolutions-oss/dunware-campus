<#
  repair-campus.ps1  --  fix a Campus 0.9.0 install that came up wrong.

  Handles both known 0.9.0 failure modes:
    1. install.ps1 ran non-elevated -> "Campus App" / "Campus Proxy" services
       were never registered -> https://localhost/ refused to connect.
    2. the Caddyfile proxied  /  to Django, which has no route for it ->
       https://localhost/ returned 404 (waitress/Caddy in the headers).
  It also strips a UTF-8 BOM from .env if an older install.ps1 left one.

  RUN AS ADMINISTRATOR:
    powershell -ExecutionPolicy Bypass -File <path>\repair-campus.ps1

  Optional in-place update of an existing install without a full reinstall:
    -RefreshFrontendFrom <repo>\frontend\out     swap the exported SPA
    -RefreshAppFrom      <repo>\dist\campus-app   swap the frozen backend
  Both keep .env and the database; -RefreshAppFrom re-runs migrate + collectstatic.

  Idempotent - safe to run again. Does not touch the database beyond
  confirming it answers (and migrate, if -RefreshAppFrom is given).
#>
param(
  [string]$InstallRoot = "$env:ProgramData\Campus",
  # optional: a freshly-built frontend export to drop in over the installed
  # one (e.g. D:\Solutions\dunware-campus\frontend\out). Stops Campus Proxy
  # for the copy so Caddy's file handles don't block it.
  [string]$RefreshFrontendFrom,
  # optional: a freshly-frozen backend (the dist\campus-app directory built by
  # deploy\campus.spec, e.g. D:\Solutions\dunware-campus\dist\campus-app). Swaps
  # campus-app.exe + its libs in place, keeping .env / frontend_out / media /
  # staticfiles. Stops Campus App for the copy, then re-migrates.
  [string]$RefreshAppFrom
)

$ErrorActionPreference = "Stop"
function Step($m){ Write-Host "==> $m" -ForegroundColor Cyan }
function Info($m){ Write-Host "    $m" }
function Warn($m){ Write-Host "    ! $m" -ForegroundColor Yellow }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Not elevated. Re-run this from an Administrator PowerShell."
}

$app   = Join-Path $InstallRoot "app\campus-app.exe"
$nssm  = Join-Path $InstallRoot "caddy\bin\nssm.exe"
$caddy = Join-Path $InstallRoot "caddy\bin\caddy.exe"
$cfile = Join-Path $InstallRoot "caddy\Caddyfile"
$pgBin = Join-Path $InstallRoot "pgsql\bin"
$envf  = Join-Path $InstallRoot "app\.env"
$webRoot = Join-Path $InstallRoot "app\frontend_out"
foreach ($p in @($app,$nssm,$caddy,$pgBin,$envf)) {
  if (-not (Test-Path $p)) { throw "missing expected path: $p" }
}
$LanHost = "localhost"
$ApiBind = "127.0.0.1:8001"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# --- 0. .env sanity + BOM strip -----------------------------------------
Step "Checking app\.env"
$envText = Get-Content $envf -Raw
foreach ($k in @("SECRET_KEY","FIELD_ENCRYPTION_KEY","DATABASE_URL")) {
  if ($envText -notmatch "(?m)^\s*$k\s*=\s*\S") { throw ".env is missing $k - the install's secret step did not complete. Reinstall." }
}
Info ".env has SECRET_KEY / FIELD_ENCRYPTION_KEY / DATABASE_URL"
$bytes = [System.IO.File]::ReadAllBytes($envf)
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
  [System.IO.File]::WriteAllText($envf, $envText, $utf8NoBom)
  Info "removed a UTF-8 BOM from .env"
}

# --- 1. database reachable --------------------------------------------
Step "Checking PostgreSQL"
if (-not (Get-Service "Campus PostgreSQL" -ErrorAction SilentlyContinue)) { throw "'Campus PostgreSQL' service missing - reinstall." }
if ((Get-Service "Campus PostgreSQL").Status -ne "Running") { Start-Service "Campus PostgreSQL"; Start-Sleep 3 }
$mig = (& (Join-Path $pgBin "psql.exe") -U postgres -h 127.0.0.1 -p 5432 -d campus -tAc "SELECT count(*) FROM django_migrations;" 2>$null | Select-Object -First 1)
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
  Warn "no index.html under $webRoot - the SPA can't be served. The exported frontend is missing from this build."
}
$caddyfile = @"
$LanHost {
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
# caddy writes its info logs to stderr; on PS 5.1 with $ErrorActionPreference=Stop,
# piping a native command's stderr (2>&1) throws NativeCommandError and aborts the
# script. Drop stderr, key off the exit code instead.
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
Step "Registering Campus App"
Ensure-Service "Campus App" $app "serve --host 127.0.0.1 --port 8001" (Join-Path $InstallRoot "app")
Step "Registering Campus Proxy"
Ensure-Service "Campus Proxy" $caddy ("run --config `"$cfile`"") (Join-Path $InstallRoot "caddy")

# --- 3a0. swap in a freshly-frozen backend, if asked -------------
if ($RefreshAppFrom) {
  Step "Refreshing the app (frozen backend) from $RefreshAppFrom"
  if (-not (Test-Path (Join-Path $RefreshAppFrom "campus-app.exe"))) {
    throw "no campus-app.exe under $RefreshAppFrom - build it first (cd backend; pyinstaller ..\deploy\campus.spec --distpath ..\dist)"
  }
  $appDir = Join-Path $InstallRoot "app"
  foreach ($svc in @("Campus Proxy","Campus App")) {
    if ((Get-Service $svc -EA SilentlyContinue).Status -eq "Running") { Stop-Service $svc -Force; Start-Sleep 1 }
  }
  # /MIR but never purge or overwrite the runtime data that isn't part of the freeze
  & robocopy $RefreshAppFrom $appDir /MIR /XF ".env" /XD (Join-Path $appDir "frontend_out") (Join-Path $appDir "media") (Join-Path $appDir "staticfiles") /NFL /NDL /NJH /NP /R:2 /W:2 | Out-Null
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
    throw "no index.html under $RefreshFrontendFrom - build it first (cd frontend; npm run build)"
  }
  if ((Get-Service "Campus Proxy" -EA SilentlyContinue).Status -eq "Running") {
    Stop-Service "Campus Proxy" -Force
    Start-Sleep 1
  }
  & robocopy $RefreshFrontendFrom $webRoot /MIR /NFL /NDL /NJH /NP /R:2 /W:2 | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }
  Info "frontend_out updated ($((Get-ChildItem $webRoot -Recurse -File).Count) files)"
}

# --- 3b. app icon (shortcut + browser favicon) --------------------
Step "Applying the Campus icon"
$icoSrc = @(
  (Join-Path $InstallRoot "campus.ico"),
  (Join-Path $InstallRoot "scripts\campus.ico"),
  (Join-Path $PSScriptRoot "campus.ico")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($icoSrc) {
  $icoDst = Join-Path $InstallRoot "campus.ico"
  if ($icoSrc -ne $icoDst) { Copy-Item $icoSrc $icoDst -Force }
  Set-Content -Path (Join-Path $InstallRoot "launch-campus.url") -Encoding ascii -Value @"
[InternetShortcut]
URL=https://$LanHost/
IconFile=$icoDst
IconIndex=0
"@
  # browser favicon for an install whose frontend_out predates the icon
  $favDst = Join-Path $webRoot "favicon.ico"
  if ((Test-Path $webRoot) -and -not (Test-Path $favDst)) { Copy-Item $icoDst $favDst -Force }
  $msg = "icon set on launch-campus.url"
  if (Test-Path $favDst) { $msg += " and frontend_out\favicon.ico" }
  Info $msg
} else {
  Warn "campus.ico not found - it ships with the next full reinstall (Campus-Setup.exe 0.9.0+ with the icon)"
}

# --- 4. restart everything (Caddyfile changed) --------------------
Step "Restarting services"
foreach ($svc in @("Campus PostgreSQL","Campus App","Campus Proxy")) {
  Set-Service -Name $svc -StartupType Automatic
  if ((Get-Service $svc).Status -eq "Running" -and $svc -ne "Campus PostgreSQL") { Restart-Service $svc -Force }
  elseif ((Get-Service $svc).Status -ne "Running") { Start-Service $svc }
  Start-Sleep 1
  Info ("{0,-18} {1}" -f $svc, (Get-Service $svc).Status)
}

# --- 5. health check ----------------------------------------------
# IMPORTANT: do not probe over HTTPS from PowerShell here. Django forces an
# HTTPS redirect on any request without Caddy's X-Forwarded-Proto header (so
# a direct probe of :<api port> is useless), and the Windows system TLS stack
# (Schannel - used by Invoke-WebRequest AND curl.exe) frequently fails the
# handshake against Caddy's `tls internal` cert with SEC_E_INTERNAL_ERROR even
# though Chrome / Edge (their own TLS libraries) connect fine. So we verify:
#   1. all three services are Running
#   2. Caddy answers on :80 with a 3xx redirect  (plain HTTP, curl.exe)
#   3. something is listening on :443
# and leave the actual HTTPS page load to a browser.
Step "Health check"
$curlExe = Join-Path $env:SystemRoot "System32\curl.exe"

$svcDown = @("Campus PostgreSQL","Campus App","Campus Proxy") |
  Where-Object { (Get-Service $_ -EA SilentlyContinue).Status -ne "Running" }

$httpCode = $null
if (Test-Path $curlExe) {
  foreach ($try in 1..8) {
    Start-Sleep 2
    $httpCode = (& $curlExe -s -o NUL -w "%{http_code}" --max-time 8 "http://$LanHost/") 2>$null
    if ($httpCode -match '^(200|301|302|308)$') { break }
  }
  Info "Caddy   http://$LanHost/  -> $httpCode  (308/301 = redirect to HTTPS, as intended)"
}

$tls443 = $false
try { $tls443 = (Test-NetConnection -ComputerName $LanHost -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue) } catch {}
Info ("Port 443 listening: {0}" -f $tls443)

Write-Host ""
$caddyServing = ($httpCode -match '^(200|301|302|308)$')
if ($svcDown.Count -eq 0 -and $caddyServing -and $tls443) {
  Write-Host "  Campus is up. Open it in a browser:  https://$LanHost/" -ForegroundColor Green
  Write-Host "  (first visit warns about the local certificate - that's expected; click through / 'Advanced -> proceed')" -ForegroundColor Green
  Write-Host "  Hard-refresh once (Ctrl+Shift+R) so the browser drops any old page bundle." -ForegroundColor Green
  Write-Host ""
  Write-Host "  First admin (this build):  & '$app' manage create_admin"
} elseif ($svcDown.Count -eq 0) {
  Write-Host "  All three services are Running and Caddy is listening, but the redirect probe was inconclusive." -ForegroundColor Yellow
  Write-Host "  Open https://$LanHost/ in Chrome or Edge - that is the real test. If it fails, check:" -ForegroundColor Yellow
  Write-Host "    $InstallRoot\logs\Campus-App.log"
  Write-Host "    $InstallRoot\logs\Campus-Proxy.log"
} else {
  Warn ("not Running: {0} - check {1}\logs\Campus-App.log and {1}\logs\Campus-Proxy.log" -f ($svcDown -join ', '), $InstallRoot)
}
