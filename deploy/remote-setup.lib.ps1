<#
  remote-setup.lib.ps1  --  shared implementation for the remote-access
  companion. Dot-sourced by BOTH:
      remote-setup.ps1      (command line)
      remote-setup-ui.ps1   (the window a technician actually uses)

  Defines functions only; no side effects on load. Call Initialize-RemoteSetup
  first. Progress goes through Write-RSLog, which the GUI redirects into its log
  pane; on the command line it just writes to the host. Errors are raised as a
  terminating [RemoteSetupError] so the caller (CLI or GUI) decides what to do.
#>

if (-not ('RemoteSetupError' -as [type])) {
  Add-Type -IgnoreWarnings -WarningAction SilentlyContinue -TypeDefinition @'
public class RemoteSetupError : System.Exception {
    public RemoteSetupError(string message) : base(message) { }
}
'@
}

# ── logging ──────────────────────────────────────────────────────────────
$script:RSLogSink = $null   # GUI sets this to  { param($msg, $level) ... }

function Set-RSLogSink { param([scriptblock]$Sink) $script:RSLogSink = $Sink }

function Write-RSLog {
  param([string]$Message, [ValidateSet('step', 'info', 'warn', 'err')][string]$Level = 'info')
  if ($script:RSLogSink) { & $script:RSLogSink $Message $Level; return }
  switch ($Level) {
    'step' { Write-Host "==> $Message" -ForegroundColor Cyan }
    'warn' { Write-Host "    ! $Message" -ForegroundColor Yellow }
    'err'  { Write-Host "    x $Message" -ForegroundColor Red }
    default { Write-Host "    $Message" }
  }
}
function Step($m) { Write-RSLog $m 'step' }
function Info($m) { Write-RSLog $m 'info' }
function Warn($m) { Write-RSLog $m 'warn' }
function Die($m)  { Write-RSLog $m 'err'; throw [RemoteSetupError]::new($m) }

# ── paths ────────────────────────────────────────────────────────────────
function Initialize-RemoteSetup {
  param([string]$InstallRoot = "$env:ProgramData\Campus")
  $app = Join-Path $InstallRoot 'app'
  $remote = Join-Path $InstallRoot 'remote'
  $script:RS = @{
    InstallRoot  = $InstallRoot
    AppDir       = $app
    EnvPath      = Join-Path $app '.env'
    RemoteDir    = $remote
    RemoteBin    = Join-Path $remote 'bin'
    LogDir       = Join-Path $InstallRoot 'logs'
    Nssm         = Join-Path $InstallRoot 'caddy\bin\nssm.exe'
    CaddyfileLan = Join-Path $InstallRoot 'caddy\Caddyfile'
    CaddyLanBak  = Join-Path $InstallRoot 'caddy\Caddyfile.lan.bak'
  }
  if (-not (Test-Path $script:RS.EnvPath)) {
    Die "no Campus install at $InstallRoot (missing $($script:RS.EnvPath))."
  }
  New-Item -ItemType Directory -Force -Path $script:RS.RemoteDir | Out-Null
}

function Test-RSAdmin {
  ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

# ── .env helpers (BOM-less write + re-lock, mirrors install.ps1) ──────────
function Read-EnvMap {
  $map = [ordered]@{}
  foreach ($line in Get-Content $script:RS.EnvPath) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $k, $v = $line -split '=', 2
    $map[$k.Trim()] = $v
  }
  $map
}

function Set-EnvValues([hashtable]$Values) {
  $envPath = $script:RS.EnvPath
  & icacls $envPath /grant "*S-1-5-32-544:(F)" /inheritance:e | Out-Null
  $lines = [System.Collections.Generic.List[string]]::new()
  $seen = @{}
  foreach ($line in Get-Content $envPath) {
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
  [System.IO.File]::WriteAllText($envPath, ($lines -join "`r`n") + "`r`n",
    (New-Object System.Text.UTF8Encoding($false)))
  & icacls $envPath /inheritance:r /grant:r "*S-1-5-18:(F)" "*S-1-5-32-544:(F)" | Out-Null
  Info "updated .env ($($Values.Keys -join ', '))"
}

function Append-CsvEnv([string]$key, [string]$value) {
  $map = Read-EnvMap
  $cur = @()
  if ($map.Contains($key) -and $map[$key].Trim()) {
    $cur = $map[$key].Split(',') | ForEach-Object { $_.Trim() }
  }
  if ($cur -notcontains $value) { $cur += $value }
  Set-EnvValues @{ $key = ($cur -join ',') }
}

function Restart-CampusApp   { Step 'restarting Campus App';   Restart-Service 'Campus App'   -ErrorAction SilentlyContinue }
function Restart-CampusProxy { Step 'restarting Campus Proxy'; Restart-Service 'Campus Proxy' -ErrorAction SilentlyContinue }

function Register-RemoteService([string]$exe, [string]$svcArgs, [string]$workDir) {
  $nssm = $script:RS.Nssm
  if (-not (Test-Path $nssm)) { Die "NSSM not found at $nssm -- cannot register the Campus Remote service." }
  $log = Join-Path $script:RS.LogDir 'Campus-Remote.log'
  if (Get-Service 'Campus Remote' -ErrorAction SilentlyContinue) {
    & $nssm set 'Campus Remote' Application $exe | Out-Null
    & $nssm set 'Campus Remote' AppParameters $svcArgs | Out-Null
  } else {
    & $nssm install 'Campus Remote' $exe $svcArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { Die "nssm install 'Campus Remote' failed ($LASTEXITCODE) -- not elevated?" }
  }
  & $nssm set 'Campus Remote' AppDirectory $workDir | Out-Null
  & $nssm set 'Campus Remote' Start SERVICE_AUTO_START | Out-Null
  & $nssm set 'Campus Remote' AppStdout $log | Out-Null
  & $nssm set 'Campus Remote' AppStderr $log | Out-Null
  if (-not (Get-Service 'Campus Remote' -ErrorAction SilentlyContinue)) {
    Die "'Campus Remote' was not created (nssm returned 0 but the service is absent)."
  }
  Restart-Service 'Campus Remote'
  Info "Campus Remote service registered and started (log: $log)"
}

function Remove-RemoteService {
  $nssm = $script:RS.Nssm
  if (Get-Service 'Campus Remote' -ErrorAction SilentlyContinue) {
    & $nssm stop 'Campus Remote' | Out-Null
    & $nssm remove 'Campus Remote' confirm | Out-Null
    Info 'removed the Campus Remote service'
  }
}

function Resolve-Tool([string]$explicit, [string]$staged, [string]$onPath) {
  if ($explicit -and (Test-Path $explicit)) { return (Resolve-Path $explicit).Path }
  if (Test-Path $staged) { return $staged }
  $c = Get-Command $onPath -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  return $null
}

function Get-LanSiteName {
  $f = $script:RS.CaddyfileLan
  if (Test-Path $f) {
    $m = [regex]::Match((Get-Content $f -Raw), '(?m)^\s*([^\s{#][^\s{]*)\s*\{')
    if ($m.Success) { return $m.Groups[1].Value }
  }
  return 'localhost'
}

# ── status ───────────────────────────────────────────────────────────────
function Get-RemoteStatus {
  $map = Read-EnvMap
  $svc = Get-Service 'Campus Remote' -ErrorAction SilentlyContinue
  $header = if ($map.Contains('REMOTE_ACCESS_CLIENT_IP_HEADER')) { $map['REMOTE_ACCESS_CLIENT_IP_HEADER'].Trim() } else { '' }
  $enabled = ($map.Contains('REMOTE_ACCESS_ENABLED') -and $map['REMOTE_ACCESS_ENABLED'].Trim() -eq '1')
  $mode = 'Off (LAN only)'
  if ($enabled) {
    if ($header -ieq 'CF-Connecting-IP' -or (Test-Path (Join-Path $script:RS.RemoteDir 'config.yml'))) { $mode = 'Cloudflare Tunnel' }
    elseif (Test-Path (Join-Path $script:RS.RemoteDir 'wg\wg0.conf')) { $mode = 'WireGuard VPN' }
    elseif ($header -ieq 'X-Forwarded-For') { $mode = 'Plain gateway' }
    else { $mode = 'On (unrecognised)' }
  }
  $hf = Join-Path $script:RS.AppDir 'hotfix'
  $hotfixes = @()
  if (Test-Path $hf) {
    $hotfixes = @(Get-ChildItem $hf -Recurse -Filter *.py -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName.Substring($hf.Length + 1) })
  }
  [pscustomobject]@{
    Enabled  = $enabled
    Mode     = $mode
    Hosts    = if ($map.Contains('REMOTE_ACCESS_HOSTS')) { $map['REMOTE_ACCESS_HOSTS'].Trim() } else { '' }
    Header   = $header
    Service  = if ($svc) { "$($svc.Status)" } else { 'not installed' }
    Hotfixes = $hotfixes
  }
}

# ── Cloudflare tunnel ────────────────────────────────────────────────────
function Get-CloudflaredExe([string]$explicit) {
  Resolve-Tool $explicit (Join-Path $script:RS.RemoteBin 'cloudflared.exe') 'cloudflared'
}
function Get-CloudflaredCert { Join-Path $script:RS.RemoteDir '.cloudflared\cert.pem' }

function Invoke-CloudflaredLogin([string]$CloudflaredExe) {
  $cf = Get-CloudflaredExe $CloudflaredExe
  if (-not $cf) { Die "cloudflared.exe not found. Stage it at $($script:RS.RemoteBin)\cloudflared.exe." }
  $cfHome = Join-Path $script:RS.RemoteDir '.cloudflared'
  New-Item -ItemType Directory -Force -Path $cfHome | Out-Null
  $env:TUNNEL_ORIGIN_CERT = Get-CloudflaredCert
  Step 'a browser will open -- sign in to the school Cloudflare account and pick the zone'
  & $cf tunnel login
  if (-not (Test-Path (Get-CloudflaredCert))) { Die 'Cloudflare login did not produce cert.pem.' }
  Info 'Cloudflare sign-in complete.'
}

function Enable-Tunnel {
  param([hashtable]$Opt)   # Hostname, TunnelName, AccessEmails, CloudflaredExe
  if (-not $Opt.Hostname) { Die 'a public hostname is required.' }
  $tunnelName = if ($Opt.TunnelName) { $Opt.TunnelName } else { 'campus' }
  $cf = Get-CloudflaredExe $Opt.CloudflaredExe
  if (-not $cf) { Die "cloudflared.exe not found. Stage it at $($script:RS.RemoteBin)\cloudflared.exe." }
  Step "Cloudflare Tunnel -> $($Opt.Hostname)"

  $cert = Get-CloudflaredCert
  $env:TUNNEL_ORIGIN_CERT = $cert
  if (-not (Test-Path $cert)) { Invoke-CloudflaredLogin $Opt.CloudflaredExe }

  $cfHome = Split-Path $cert
  $existing = (& $cf --origincert $cert tunnel list --output json 2>$null | ConvertFrom-Json) |
    Where-Object { $_.name -eq $tunnelName }
  if (-not $existing) {
    & $cf --origincert $cert tunnel create $tunnelName
    if ($LASTEXITCODE -ne 0) { Die 'tunnel create failed.' }
    Info "created tunnel '$tunnelName'"
  } else {
    Info "reusing tunnel '$tunnelName' ($($existing.id))"
  }
  $credFile = (Get-ChildItem $cfHome -Filter *.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
  if (-not $credFile) { Die "no tunnel credentials .json under $cfHome." }

  $origin = Get-LanSiteName
  $configYml = Join-Path $script:RS.RemoteDir 'config.yml'
  @"
# generated by Campus remote-setup -- $(Get-Date -Format s)
tunnel: $tunnelName
credentials-file: $credFile
originRequest:
  originServerName: $origin
  noTLSVerify: true
ingress:
  - hostname: $($Opt.Hostname)
    service: https://localhost:443
  - service: http_status:404
"@ | Set-Content -Path $configYml -Encoding utf8
  Info 'wrote config.yml'

  & $cf --origincert $cert tunnel route dns $tunnelName $Opt.Hostname
  if ($LASTEXITCODE -ne 0) { Warn "route dns returned $LASTEXITCODE -- add the CNAME by hand if needed." }

  Register-RemoteService $cf "tunnel --config `"$configYml`" --origincert `"$cert`" run" $script:RS.RemoteDir

  Set-EnvValues @{
    REMOTE_ACCESS_ENABLED          = '1'
    REMOTE_ACCESS_HOSTS            = $Opt.Hostname
    REMOTE_ACCESS_CLIENT_IP_HEADER = 'CF-Connecting-IP'
  }
  Append-CsvEnv 'ALLOWED_HOSTS' $Opt.Hostname
  Append-CsvEnv 'CSRF_TRUSTED_ORIGINS' "https://$($Opt.Hostname)"
  Restart-CampusApp

  Step 'LAST STEP -- set up Cloudflare Access in the Cloudflare dashboard:'
  Info 'Zero Trust -> Access -> Applications -> Add -> Self-hosted'
  Info "  Application domain : $($Opt.Hostname)"
  if ($Opt.AccessEmails) { Info "  Policy -> Include -> Emails: $($Opt.AccessEmails)" }
  else { Info '  Policy -> Include -> Emails (list) OR your Google / Microsoft sign-in' }
  Info "Until Access is on, $($Opt.Hostname) is protected only by Campus's own login."
}

# ── WireGuard ────────────────────────────────────────────────────────────
function Get-WgTools([string]$wireguardExe) {
  @{
    WireGuard = Resolve-Tool $wireguardExe (Join-Path $script:RS.RemoteBin 'wireguard.exe') 'wireguard'
    Wg        = Resolve-Tool $null (Join-Path $script:RS.RemoteBin 'wg.exe') 'wg'
  }
}

function Enable-WireGuard {
  param([hashtable]$Opt)   # WgListenPort, WgSubnet, Hostname, WireGuardExe
  $t = Get-WgTools $Opt.WireGuardExe
  if (-not $t.WireGuard -or -not $t.Wg) { Die "wireguard.exe / wg.exe not found. Stage them at $($script:RS.RemoteBin)\." }
  $port = if ($Opt.WgListenPort) { [int]$Opt.WgListenPort } else { 51820 }
  $subnet = if ($Opt.WgSubnet) { $Opt.WgSubnet } else { '10.55.0.0/24' }
  $prefix = $subnet.Split('/')[0]; $prefix = $prefix.Substring(0, $prefix.LastIndexOf('.'))
  $wgDir = Join-Path $script:RS.RemoteDir 'wg'
  $srvConf = Join-Path $wgDir 'wg0.conf'
  New-Item -ItemType Directory -Force -Path $wgDir | Out-Null

  Step "WireGuard server (UDP $port, $subnet)"
  if (-not (Test-Path $srvConf)) {
    $priv = (& $t.Wg genkey).Trim()
    $pub = ($priv | & $t.Wg pubkey).Trim()
    @"
[Interface]
# PublicKey = $pub   (devices need this; kept here for reference)
PrivateKey = $priv
Address = $prefix.1/24
ListenPort = $port
"@ | Set-Content -Path $srvConf -Encoding utf8
    Info 'wrote wg0.conf'
  } else {
    Info 'wg0.conf already exists -- keeping it'
  }
  if (-not (Get-Service "WireGuardTunnel`$wg0" -ErrorAction SilentlyContinue)) {
    & $t.WireGuard /installtunnelservice $srvConf
  }
  Set-EnvValues @{ REMOTE_ACCESS_ENABLED = '1'; REMOTE_ACCESS_CLIENT_IP_HEADER = '' }
  if ($Opt.Hostname) {
    Append-CsvEnv 'ALLOWED_HOSTS' $Opt.Hostname
    Set-EnvValues @{ REMOTE_ACCESS_HOSTS = $Opt.Hostname }
  }
  Restart-CampusApp
  Step "Forward UDP $port on the school router to this box ($($env:COMPUTERNAME)), then add each device."
}

function Add-WireGuardPeer {
  param([hashtable]$Opt)   # Name (req), Endpoint (req), WgListenPort, WireGuardExe
  if (-not $Opt.Name) { Die 'a device name is required.' }
  if (-not $Opt.Endpoint) { Die "the school's public IP or DDNS name is required." }
  $t = Get-WgTools $Opt.WireGuardExe
  if (-not $t.Wg) { Die 'wg.exe not found.' }
  $port = if ($Opt.WgListenPort) { [int]$Opt.WgListenPort } else { 51820 }
  $wgDir = Join-Path $script:RS.RemoteDir 'wg'
  $srvConf = Join-Path $wgDir 'wg0.conf'
  if (-not (Test-Path $srvConf)) { Die 'set up the WireGuard server first.' }

  Step "adding device '$($Opt.Name)'"
  $used = [regex]::Matches((Get-Content $srvConf -Raw), '10\.\d+\.\d+\.(\d+)/32') | ForEach-Object { [int]$_.Groups[1].Value }
  $next = 2; while ($used -contains $next) { $next++ }
  $prefix = ((Get-Content $srvConf | Where-Object { $_ -match '^\s*Address\s*=' }) -replace '.*=\s*', '' -replace '\.\d+/.*', '').Trim()
  if (-not $prefix) { $prefix = '10.55.0' }
  $peerIp = "$prefix.$next"
  $peerPriv = (& $t.Wg genkey).Trim()
  $peerPub = ($peerPriv | & $t.Wg pubkey).Trim()
  $srvPub = ((Get-Content $srvConf | Where-Object { $_ -match '^\s*#\s*PublicKey\s*=' }) -replace '.*=\s*', '').Trim()
  Add-Content $srvConf "`r`n[Peer]`r`n# $($Opt.Name)`r`nPublicKey = $peerPub`r`nAllowedIPs = $peerIp/32"
  if (Get-Service "WireGuardTunnel`$wg0" -ErrorAction SilentlyContinue) { & $t.Wg syncconf wg0 $srvConf 2>$null }
  $campusIp = try { (Test-Connection -ComputerName $env:COMPUTERNAME -Count 1 -ErrorAction Stop).IPV4Address.IPAddressToString } catch { '' }
  $allowed = if ($campusIp) { "$campusIp/32" } else { "$prefix.1/32" }
  $safe = $Opt.Name -replace '[^\w.-]', '_'
  $clientConf = Join-Path $wgDir "$safe.conf"
  @"
[Interface]
PrivateKey = $peerPriv
Address = $peerIp/32

[Peer]
PublicKey = $srvPub
Endpoint = $($Opt.Endpoint):$port
# split tunnel: only Campus traffic goes through the VPN
AllowedIPs = $allowed
PersistentKeepalive = 25
"@ | Set-Content -Path $clientConf -Encoding utf8
  Info "wrote $clientConf"
  $qr = Get-Command qrencode -ErrorAction SilentlyContinue
  if ($qr) {
    $png = Join-Path $wgDir "$safe.png"
    & qrencode -o $png -r $clientConf 2>$null
    if (Test-Path $png) { Info "QR image: $png" }
  }
  return $clientConf
}

# ── plain gateway ────────────────────────────────────────────────────────
function Enable-Gateway {
  param([hashtable]$Opt)   # Hostname (req), AcmeEmail (req)
  if (-not $Opt.Hostname) { Die 'a public hostname is required.' }
  if (-not $Opt.AcmeEmail) { Die 'a Let''s Encrypt account email is required.' }
  $caddyfile = $script:RS.CaddyfileLan
  if (-not (Test-Path $caddyfile)) { Die "no Caddyfile at $caddyfile." }
  Step "Public gateway -> https://$($Opt.Hostname)"
  if (-not (Test-Path $script:RS.CaddyLanBak)) {
    Copy-Item $caddyfile $script:RS.CaddyLanBak -Force
    Info 'backed up the LAN Caddyfile'
  }
  $apiBind = '127.0.0.1:8001'
  $m = [regex]::Match((Get-Content $caddyfile -Raw), 'reverse_proxy\s+@?api?\s*([0-9.:]+)')
  if ($m.Success) { $apiBind = $m.Groups[1].Value }
  $block = @"

# --- added by Campus remote-setup (public gateway) $(Get-Date -Format s) ---
$($Opt.Hostname) {
	encode gzip
	@api path /api/* /admin/* /static/* /media/*
	reverse_proxy @api $apiBind {
		header_up X-Forwarded-Proto https
	}
	root * {`$CAMPUS_WEB_ROOT:./frontend_out}
	file_server
	tls $($Opt.AcmeEmail)
}
"@
  Add-Content -Path $caddyfile -Value $block -Encoding utf8
  Info "appended a public site block for $($Opt.Hostname)"
  Restart-CampusProxy
  Set-EnvValues @{
    REMOTE_ACCESS_ENABLED          = '1'
    REMOTE_ACCESS_HOSTS            = $Opt.Hostname
    REMOTE_ACCESS_CLIENT_IP_HEADER = 'X-Forwarded-For'
  }
  Append-CsvEnv 'ALLOWED_HOSTS' $Opt.Hostname
  Append-CsvEnv 'CSRF_TRUSTED_ORIGINS' "https://$($Opt.Hostname)"
  Restart-CampusApp
  Step "Forward ports 80 AND 443 to this box and point a public DNS A record at the school's IP:"
  Info "  $($Opt.Hostname)  ->  <school public IP>"
}

# ── off ──────────────────────────────────────────────────────────────────
function Disable-RemoteAccess {
  param([hashtable]$Opt = @{})
  Step 'Disabling remote access'
  Remove-RemoteService
  $wg = Resolve-Tool $Opt.WireGuardExe (Join-Path $script:RS.RemoteBin 'wireguard.exe') 'wireguard'
  if ($wg -and (Get-Service "WireGuardTunnel`$wg0" -ErrorAction SilentlyContinue)) {
    & $wg /uninstalltunnelservice wg0 | Out-Null
    Info 'removed the WireGuard tunnel service'
  }
  if (Test-Path $script:RS.CaddyLanBak) {
    Copy-Item $script:RS.CaddyLanBak $script:RS.CaddyfileLan -Force
    Remove-Item $script:RS.CaddyLanBak -Force
    Info 'restored the LAN-only Caddyfile'
    Restart-CampusProxy
  }
  Set-EnvValues @{
    REMOTE_ACCESS_ENABLED          = '0'
    REMOTE_ACCESS_HOSTS            = ''
    REMOTE_ACCESS_CLIENT_IP_HEADER = ''
  }
  Restart-CampusApp
  Info 'Campus is LAN-only again. Nothing was removed from the database.'
}
