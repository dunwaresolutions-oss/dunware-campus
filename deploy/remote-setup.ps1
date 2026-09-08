<#
  remote-setup.ps1  --  turn optional OFF-PREMISES access on (or off) for a
  Campus install.

  Campus ships LAN-only. This script is the companion a technician runs *only*
  for a site that needs staff / parents / students to reach their profiles from
  outside the building. It never runs during the normal installer. Nothing here
  moves stored data off the box: the database, uploaded files and backups stay
  on this machine in every mode. See docs/REMOTE_ACCESS_AND_YOUR_DATA.md.

  RUN AS ADMINISTRATOR, from the install's scripts folder:
    powershell -ExecutionPolicy Bypass -File remote-setup.ps1 -Mode <mode> ...

  ─────────────────────────────────────────────────────────────────────────────
  MODES  --  fill in the bracketed values for the site:

  Cloudflare Tunnel  (easiest for parents -- no client to install)
    -Mode Tunnel -Hostname <portal.school.edu.bs> [-TunnelName campus]
                 [-AccessEmails "head@school.edu.bs,office@school.edu.bs"]
    Prereqs the school provides: a Cloudflare account (free tier is fine) and a
    domain in Cloudflare. The script opens a browser for you to sign in.
    After it finishes, set up Cloudflare Access on that hostname (it prints the
    exact steps) so every visitor authenticates at Cloudflare's edge first.

  WireGuard VPN  (best for staff -- keeps ciphertext-only in transit)
    -Mode WireGuard [-WgListenPort 51820] [-Endpoint <school-public-ip-or-ddns>]
    then, per device:
    -Mode WireGuard -AddPeer <"Ms Rolle laptop">
    Prereq: one UDP port forwarded on the school router to this box. Each
    -AddPeer writes a <name>.conf (and prints a QR if qrencode is present).

  Plain gateway  (own domain, own Let's Encrypt cert, TLS ends on this box)
    -Mode Gateway -Hostname <portal.school.edu.bs> -AcmeEmail <admin@school.edu.bs>
    Prereq: ports 80 AND 443 forwarded to this box, and a public DNS A record
    for the hostname pointing at the school's public IP.

  Housekeeping
    -Mode Status      what is currently enabled
    -Mode Off         tear it all down, back to LAN-only

  ─────────────────────────────────────────────────────────────────────────────
  Idempotent where it can be. -Mode Off always leaves a working LAN install.
#>
param(
  [Parameter(Mandatory)]
  [ValidateSet("Tunnel", "WireGuard", "Gateway", "Status", "Off")]
  [string]$Mode,

  [string]$InstallRoot = "$env:ProgramData\Campus",

  # --- Tunnel / Gateway ---
  [string]$Hostname,
  [string]$TunnelName = "campus",
  [string]$AccessEmails,
  [string]$AcmeEmail,
  [string]$CloudflaredExe,

  # --- WireGuard ---
  [int]$WgListenPort = 51820,
  [string]$WgSubnet = "10.55.0.0/24",
  [string]$Endpoint,
  [string]$AddPeer,
  [string]$WireGuardExe,

  [switch]$Force
)

$ErrorActionPreference = "Stop"
function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Info($m) { Write-Host "    $m" }
function Warn($m) { Write-Host "    ! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "    x $m" -ForegroundColor Red; exit 1 }

# ── elevation guard (same reasoning as install.ps1) ───────────────────────
if (-not ([Security.Principal.WindowsPrincipal] `
      [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
  Die "run this from an elevated PowerShell (Run as administrator)."
}

$AppDir       = Join-Path $InstallRoot "app"
$EnvPath      = Join-Path $AppDir ".env"
$RemoteDir    = Join-Path $InstallRoot "remote"
$RemoteBin    = Join-Path $RemoteDir  "bin"
$LogDir       = Join-Path $InstallRoot "logs"
$Nssm         = Join-Path $InstallRoot "caddy\bin\nssm.exe"
$CaddyfileLan = Join-Path $InstallRoot "caddy\Caddyfile"
$CaddyLanBak  = Join-Path $InstallRoot "caddy\Caddyfile.lan.bak"
if (-not (Test-Path $EnvPath)) { Die "no Campus install at $InstallRoot (missing $EnvPath)." }
New-Item -ItemType Directory -Force -Path $RemoteDir | Out-Null

# ── .env helpers (BOM-less write + re-lock, mirrors install.ps1) ──────────
function Read-EnvMap {
  $map = [ordered]@{}
  foreach ($line in Get-Content $EnvPath) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $k, $v = $line -split '=', 2
    $map[$k.Trim()] = $v
  }
  $map
}

function Set-EnvValues([hashtable]$Values) {
  # unlock (a prior install ACL'd this to SYSTEM+Administrators, inheritance off)
  & icacls $EnvPath /grant "*S-1-5-32-544:(F)" /inheritance:e | Out-Null
  $lines = [System.Collections.Generic.List[string]]::new()
  $seen  = @{}
  foreach ($line in Get-Content $EnvPath) {
    $m = [regex]::Match($line, '^\s*([A-Z0-9_]+)\s*=')
    if ($m.Success -and $Values.ContainsKey($m.Groups[1].Value)) {
      $key = $m.Groups[1].Value
      $lines.Add("$key=$($Values[$key])"); $seen[$key] = $true
    } else {
      $lines.Add($line)
    }
  }
  foreach ($key in $Values.Keys) {
    if (-not $seen.ContainsKey($key)) { $lines.Add("$key=$($Values[$key])") }
  }
  # django-environ drops a BOM-prefixed first line silently -> WriteAllText, no BOM
  [System.IO.File]::WriteAllText($EnvPath, ($lines -join "`r`n") + "`r`n",
    (New-Object System.Text.UTF8Encoding($false)))
  # re-lock: break inheritance, SYSTEM + Administrators full, nothing else
  & icacls $EnvPath /inheritance:r /grant:r `
    "*S-1-5-18:(F)" "*S-1-5-32-544:(F)" | Out-Null
  Info "updated $EnvPath ($($Values.Keys -join ', '))"
}

function Append-CsvEnv([string]$key, [string]$value) {
  $map = Read-EnvMap
  $cur = @()
  if ($map.Contains($key) -and $map[$key].Trim()) { $cur = $map[$key].Split(',') | ForEach-Object { $_.Trim() } }
  if ($cur -notcontains $value) { $cur += $value }
  Set-EnvValues @{ $key = ($cur -join ',') }
}

function Restart-CampusApp   { Step "restarting Campus App"; Restart-Service "Campus App" -ErrorAction SilentlyContinue }
function Restart-CampusProxy { Step "restarting Campus Proxy"; Restart-Service "Campus Proxy" -ErrorAction SilentlyContinue }

function Register-RemoteService([string]$exe, [string]$svcArgs, [string]$workDir) {
  if (-not (Test-Path $Nssm)) { Die "NSSM not found at $Nssm -- cannot register the Campus Remote service." }
  $log = Join-Path $LogDir "Campus-Remote.log"
  if (Get-Service "Campus Remote" -ErrorAction SilentlyContinue) {
    & $Nssm set "Campus Remote" Application $exe | Out-Null
    & $Nssm set "Campus Remote" AppParameters $svcArgs | Out-Null
  } else {
    & $Nssm install "Campus Remote" $exe $svcArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { Die "nssm install 'Campus Remote' failed ($LASTEXITCODE) -- is this shell elevated?" }
  }
  & $Nssm set "Campus Remote" AppDirectory $workDir | Out-Null
  & $Nssm set "Campus Remote" Start SERVICE_AUTO_START | Out-Null
  & $Nssm set "Campus Remote" AppStdout $log | Out-Null
  & $Nssm set "Campus Remote" AppStderr $log | Out-Null
  if (-not (Get-Service "Campus Remote" -ErrorAction SilentlyContinue)) {
    Die "'Campus Remote' was not created (nssm returned 0 but the service is absent)."
  }
  Restart-Service "Campus Remote"
  Info "Campus Remote service registered and started (log: $log)"
}

function Remove-RemoteService {
  if (Get-Service "Campus Remote" -ErrorAction SilentlyContinue) {
    & $Nssm stop "Campus Remote" | Out-Null
    & $Nssm remove "Campus Remote" confirm | Out-Null
    Info "removed the Campus Remote service"
  }
}

function Resolve-Tool([string]$explicit, [string]$staged, [string]$onPath) {
  if ($explicit -and (Test-Path $explicit)) { return (Resolve-Path $explicit).Path }
  if (Test-Path $staged) { return $staged }
  $c = Get-Command $onPath -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  return $null
}

function Lan-SiteName {
  # the hostname the LAN Caddyfile answers on -- reused as the tunnel origin SNI
  if (Test-Path $CaddyfileLan) {
    $m = [regex]::Match((Get-Content $CaddyfileLan -Raw), '(?m)^\s*([^\s{#][^\s{]*)\s*\{')
    if ($m.Success) { return $m.Groups[1].Value }
  }
  return "localhost"
}

# ════════════════════════════════════════════════════════════════════════════
switch ($Mode) {

  # ── STATUS ────────────────────────────────────────────────────────────────
  "Status" {
    Step "Remote access status"
    $map = Read-EnvMap
    foreach ($k in "REMOTE_ACCESS_ENABLED", "REMOTE_ACCESS_HOSTS", "REMOTE_ACCESS_CLIENT_IP_HEADER") {
      Info ("{0,-30} {1}" -f $k, ($(if ($map.Contains($k)) { $map[$k] } else { "(unset)" })))
    }
    $svc = Get-Service "Campus Remote" -ErrorAction SilentlyContinue
    Info ("{0,-30} {1}" -f "Campus Remote service", ($(if ($svc) { $svc.Status } else { "not installed" })))
    if (Test-Path (Join-Path $RemoteDir "config.yml")) {
      Info "cloudflared config: $(Join-Path $RemoteDir 'config.yml')"
      $cf = Resolve-Tool $CloudflaredExe (Join-Path $RemoteBin "cloudflared.exe") "cloudflared"
      if ($cf) { & $cf --origincert (Join-Path $RemoteDir ".cloudflared\cert.pem") tunnel info $TunnelName 2>$null }
    }
    if (Test-Path (Join-Path $RemoteDir "wg\wg0.conf")) {
      $wg = Resolve-Tool $WireGuardExe (Join-Path $RemoteBin "wg.exe") "wg"
      if ($wg) { & $wg show 2>$null }
    }
    $hf = Join-Path $AppDir "hotfix"
    if (Test-Path $hf) {
      $active = Get-ChildItem $hf -Recurse -Filter *.py -ErrorAction SilentlyContinue
      if ($active) { Warn "hotfix overlay active: $(($active | ForEach-Object { $_.FullName.Substring($hf.Length + 1) }) -join ', ')" }
    }
    break
  }

  # ── OFF ───────────────────────────────────────────────────────────────────
  "Off" {
    Step "Disabling remote access"
    Remove-RemoteService
    $wg = Resolve-Tool $WireGuardExe (Join-Path $RemoteBin "wireguard.exe") "wireguard"
    if ($wg -and (Get-Service "WireGuardTunnel`$wg0" -ErrorAction SilentlyContinue)) {
      & $wg /uninstalltunnelservice wg0 | Out-Null
      Info "removed the WireGuard tunnel service"
    }
    if (Test-Path $CaddyLanBak) {
      Copy-Item $CaddyLanBak $CaddyfileLan -Force
      Remove-Item $CaddyLanBak -Force
      Info "restored the LAN-only Caddyfile"
      Restart-CampusProxy
    }
    Set-EnvValues @{
      REMOTE_ACCESS_ENABLED         = "0"
      REMOTE_ACCESS_HOSTS           = ""
      REMOTE_ACCESS_CLIENT_IP_HEADER = ""
    }
    Restart-CampusApp
    Info "Campus is LAN-only again. Nothing was removed from the database."
    break
  }

  # ── TUNNEL (Cloudflare) ──────────────────────────────────────────────────
  "Tunnel" {
    if (-not $Hostname) { Die "-Hostname <portal.school.edu.bs> is required for -Mode Tunnel." }
    $cf = Resolve-Tool $CloudflaredExe (Join-Path $RemoteBin "cloudflared.exe") "cloudflared"
    if (-not $cf) { Die "cloudflared.exe not found. Stage it at $RemoteBin\cloudflared.exe or pass -CloudflaredExe." }
    Step "Cloudflare Tunnel -> $Hostname (via $cf)"

    $cfHome = Join-Path $RemoteDir ".cloudflared"
    New-Item -ItemType Directory -Force -Path $cfHome | Out-Null
    $cert = Join-Path $cfHome "cert.pem"
    $env:TUNNEL_ORIGIN_CERT = $cert

    if (-not (Test-Path $cert)) {
      Info "a browser will open -- sign in to the school's Cloudflare account and pick the zone for $Hostname"
      & $cf tunnel login
      if (-not (Test-Path $cert)) { Die "Cloudflare login did not produce $cert." }
    }

    $existing = (& $cf --origincert $cert tunnel list --output json 2>$null | ConvertFrom-Json) |
      Where-Object { $_.name -eq $TunnelName }
    if (-not $existing) {
      & $cf --origincert $cert tunnel create $TunnelName
      if ($LASTEXITCODE -ne 0) { Die "tunnel create failed." }
    } else {
      Info "reusing existing tunnel '$TunnelName' ($($existing.id))"
    }
    $credFile = (Get-ChildItem $cfHome -Filter *.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
    if (-not $credFile) { Die "no tunnel credentials .json under $cfHome." }

    $origin = Lan-SiteName
    $configYml = Join-Path $RemoteDir "config.yml"
    @"
# generated by remote-setup.ps1 -- $(Get-Date -Format s)
tunnel: $TunnelName
credentials-file: $credFile
originRequest:
  originServerName: $origin
  noTLSVerify: true
ingress:
  - hostname: $Hostname
    service: https://localhost:443
  - service: http_status:404
"@ | Set-Content -Path $configYml -Encoding utf8
    Info "wrote $configYml"

    & $cf --origincert $cert tunnel route dns $TunnelName $Hostname
    if ($LASTEXITCODE -ne 0) { Warn "route dns returned $LASTEXITCODE -- add a CNAME for $Hostname -> <tunnel-id>.cfargotunnel.com by hand if needed." }

    Register-RemoteService $cf "tunnel --config `"$configYml`" --origincert `"$cert`" run" $RemoteDir

    Set-EnvValues @{
      REMOTE_ACCESS_ENABLED         = "1"
      REMOTE_ACCESS_HOSTS           = $Hostname
      REMOTE_ACCESS_CLIENT_IP_HEADER = "CF-Connecting-IP"
    }
    Append-CsvEnv "ALLOWED_HOSTS" $Hostname
    Append-CsvEnv "CSRF_TRUSTED_ORIGINS" "https://$Hostname"
    Restart-CampusApp

    Write-Host ""
    Step "LAST STEP -- set up Cloudflare Access (do this in the Cloudflare dashboard):"
    Info  "Zero Trust -> Access -> Applications -> Add an application -> Self-hosted"
    Info  "  Application domain : $Hostname"
    Info  "  Session duration   : 24h (or your policy)"
    if ($AccessEmails) {
      Info "  Policy 'Staff & families' -> Include -> Emails: $AccessEmails"
    } else {
      Info "  Policy -> Include -> Emails (list) OR your Google/Microsoft IdP"
    }
    Info  "Until Access is on, $Hostname is protected only by Campus's own login."
    break
  }

  # ── WIREGUARD ────────────────────────────────────────────────────────────
  "WireGuard" {
    $wgExe = Resolve-Tool $WireGuardExe (Join-Path $RemoteBin "wireguard.exe") "wireguard"
    $wg    = Resolve-Tool $null (Join-Path $RemoteBin "wg.exe") "wg"
    if (-not $wgExe -or -not $wg) { Die "wireguard.exe / wg.exe not found. Stage them at $RemoteBin\ or install WireGuard." }
    $wgDir  = Join-Path $RemoteDir "wg"
    $srvConf = Join-Path $wgDir "wg0.conf"
    New-Item -ItemType Directory -Force -Path $wgDir | Out-Null
    $net = $WgSubnet.Split('/')[0]; $prefix = $net.Substring(0, $net.LastIndexOf('.'))

    if ($AddPeer) {
      if (-not (Test-Path $srvConf)) { Die "run -Mode WireGuard once (no -AddPeer) to create the server first." }
      if (-not $Endpoint) { Die "-Endpoint <school-public-ip-or-ddns> is required when adding a peer." }
      Step "WireGuard: adding peer '$AddPeer'"
      $used = [regex]::Matches((Get-Content $srvConf -Raw), '10\.\d+\.\d+\.(\d+)/32') | ForEach-Object { [int]$_.Groups[1].Value }
      $next = 2; while ($used -contains $next) { $next++ }
      $peerIp = "$prefix.$next"
      $peerPriv = (& $wg genkey).Trim()
      $peerPub  = ($peerPriv | & $wg pubkey).Trim()
      $srvPub   = ((Get-Content $srvConf | Where-Object { $_ -match '^\s*#\s*PublicKey\s*=' }) -replace '.*=\s*', '').Trim()
      Add-Content $srvConf "`r`n[Peer]`r`n# $AddPeer`r`nPublicKey = $peerPub`r`nAllowedIPs = $peerIp/32"
      & $wg syncconf wg0 $srvConf 2>$null
      $campusIp = (Test-Connection -ComputerName $env:COMPUTERNAME -Count 1).IPV4Address.IPAddressToString
      $clientConf = Join-Path $wgDir "$($AddPeer -replace '[^\w.-]', '_').conf"
      @"
[Interface]
PrivateKey = $peerPriv
Address = $peerIp/32

[Peer]
PublicKey = $srvPub
Endpoint = $Endpoint`:$WgListenPort
# split tunnel: only Campus traffic goes through the VPN
AllowedIPs = $campusIp/32
PersistentKeepalive = 25
"@ | Set-Content -Path $clientConf -Encoding utf8
      Info "wrote $clientConf  (import it into the WireGuard app on '$AddPeer')"
      $qr = Get-Command qrencode -ErrorAction SilentlyContinue
      if ($qr) { & qrencode -t ANSIUTF8 -r $clientConf }
      break
    }

    Step "WireGuard: server setup (UDP $WgListenPort, $WgSubnet)"
    if (-not (Test-Path $srvConf)) {
      $srvPriv = (& $wg genkey).Trim()
      $srvPub  = ($srvPriv | & $wg pubkey).Trim()
      @"
[Interface]
# PublicKey = $srvPub   (peers need this; kept here for reference)
PrivateKey = $srvPriv
Address = $prefix.1/24
ListenPort = $WgListenPort
"@ | Set-Content -Path $srvConf -Encoding utf8
      Info "wrote $srvConf"
    } else {
      Info "server config already exists -- keeping it"
    }
    if (-not (Get-Service "WireGuardTunnel`$wg0" -ErrorAction SilentlyContinue)) {
      & $wgExe /installtunnelservice $srvConf
    }
    Set-EnvValues @{ REMOTE_ACCESS_ENABLED = "1"; REMOTE_ACCESS_CLIENT_IP_HEADER = "" }
    if ($Hostname) { Append-CsvEnv "ALLOWED_HOSTS" $Hostname; Set-EnvValues @{ REMOTE_ACCESS_HOSTS = $Hostname } }
    Restart-CampusApp
    Write-Host ""
    Step "Forward UDP $WgListenPort on the school router to this box ($($env:COMPUTERNAME))."
    Info  "Then, per device:  remote-setup.ps1 -Mode WireGuard -AddPeer `"<device name>`" -Endpoint <public-ip-or-ddns>"
    break
  }

  # ── GATEWAY (public Caddy + its own ACME cert) ──────────────────────────
  "Gateway" {
    if (-not $Hostname) { Die "-Hostname <portal.school.edu.bs> is required for -Mode Gateway." }
    if (-not $AcmeEmail) { Die "-AcmeEmail <admin@school.edu.bs> is required (Let's Encrypt account)." }
    if (-not (Test-Path $CaddyfileLan)) { Die "no Caddyfile at $CaddyfileLan." }
    Step "Public gateway -> https://$Hostname (Let's Encrypt via $AcmeEmail)"
    if (-not (Test-Path $CaddyLanBak)) { Copy-Item $CaddyfileLan $CaddyLanBak -Force; Info "backed up LAN Caddyfile -> $CaddyLanBak" }

    $reverse = (Get-Content $CaddyfileLan -Raw)
    $apiBind = "127.0.0.1:8001"
    $m = [regex]::Match($reverse, 'reverse_proxy\s+@?api?\s*([0-9.:]+)')
    if ($m.Success) { $apiBind = $m.Groups[1].Value }
    $block = @"

# --- added by remote-setup.ps1 (public gateway) $(Get-Date -Format s) ---
$Hostname {
	encode gzip
	@api path /api/* /admin/* /static/* /media/*
	reverse_proxy @api $apiBind {
		header_up X-Forwarded-Proto https
	}
	root * {`$CAMPUS_WEB_ROOT:./frontend_out}
	file_server
	tls $AcmeEmail
}
"@
    Add-Content -Path $CaddyfileLan -Value $block -Encoding utf8
    Info "appended a public site block for $Hostname"
    Restart-CampusProxy

    Set-EnvValues @{
      REMOTE_ACCESS_ENABLED         = "1"
      REMOTE_ACCESS_HOSTS           = $Hostname
      REMOTE_ACCESS_CLIENT_IP_HEADER = "X-Forwarded-For"
    }
    Append-CsvEnv "ALLOWED_HOSTS" $Hostname
    Append-CsvEnv "CSRF_TRUSTED_ORIGINS" "https://$Hostname"
    Restart-CampusApp
    Write-Host ""
    Step "Forward ports 80 AND 443 on the school router to this box, and add a public DNS A record:"
    Info  "  $Hostname  ->  <school public IP>"
    Info  "Caddy will fetch the certificate automatically on the first external hit."
    break
  }
}

Write-Host ""
Write-Host "done ($Mode)." -ForegroundColor Green
