<#
  remote-setup.ps1  --  command-line front end for the Campus off-premises
  access companion. Most technicians use the window instead:

      remote-setup-ui.ps1        (Start Menu: "Campus - Remote Access Setup")

  This script is the same thing without the UI, for scripted / unattended runs.
  Campus ships LAN-only; nothing here moves STORED data off the box in any mode
  (see docs/REMOTE_ACCESS_AND_YOUR_DATA.md). RUN AS ADMINISTRATOR.

  Cloudflare Tunnel  (easiest for parents -- nothing to install)
    -Mode Tunnel -Hostname <portal.school.edu.bs> [-TunnelName campus]
                 [-AccessEmails "head@school.edu.bs,office@school.edu.bs"]

  WireGuard VPN  (best for staff -- ciphertext-only in transit)
    -Mode WireGuard [-WgListenPort 51820]
    -Mode WireGuard -AddPeer "<device name>" -Endpoint <public-ip-or-ddns>

  Plain gateway  (own domain + Let's Encrypt cert, TLS ends on this box)
    -Mode Gateway -Hostname <portal.school.edu.bs> -AcmeEmail <admin@school.edu.bs>

  -Mode Status | Off       (Off always leaves a working LAN install)
#>
param(
  [Parameter(Mandatory)]
  [ValidateSet('Tunnel', 'WireGuard', 'Gateway', 'Status', 'Off', 'Login')]
  [string]$Mode,

  [string]$InstallRoot = "$env:ProgramData\Campus",

  [string]$Hostname,
  [string]$TunnelName = 'campus',
  [string]$AccessEmails,
  [string]$AcmeEmail,
  [string]$CloudflaredExe,

  [int]$WgListenPort = 51820,
  [string]$WgSubnet = '10.55.0.0/24',
  [string]$Endpoint,
  [string]$AddPeer,
  [string]$WireGuardExe
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'remote-setup.lib.ps1')

if (-not (Test-RSAdmin)) { Write-Host 'Run this from an elevated PowerShell.' -ForegroundColor Red; exit 1 }

try {
  Initialize-RemoteSetup -InstallRoot $InstallRoot

  switch ($Mode) {
    'Status' {
      $s = Get-RemoteStatus
      '{0,-22}{1}' -f 'Enabled', $s.Enabled
      '{0,-22}{1}' -f 'Mode', $s.Mode
      '{0,-22}{1}' -f 'Public address', ($s.Hosts | ForEach-Object { $_ })
      '{0,-22}{1}' -f 'Client-IP header', $s.Header
      '{0,-22}{1}' -f 'Campus Remote svc', $s.Service
      if ($s.Hotfixes) { '{0,-22}{1}' -f 'Hotfix overlay', ($s.Hotfixes -join ', ') }
    }
    'Login'    { Invoke-CloudflaredLogin $CloudflaredExe }
    'Off'      { Disable-RemoteAccess @{ WireGuardExe = $WireGuardExe } }
    'Tunnel'   { Enable-Tunnel @{ Hostname = $Hostname; TunnelName = $TunnelName; AccessEmails = $AccessEmails; CloudflaredExe = $CloudflaredExe } }
    'Gateway'  { Enable-Gateway @{ Hostname = $Hostname; AcmeEmail = $AcmeEmail } }
    'WireGuard' {
      if ($AddPeer) {
        $conf = Add-WireGuardPeer @{ Name = $AddPeer; Endpoint = $Endpoint; WgListenPort = $WgListenPort; WireGuardExe = $WireGuardExe }
        Write-Host "device config: $conf" -ForegroundColor Green
      } else {
        Enable-WireGuard @{ WgListenPort = $WgListenPort; WgSubnet = $WgSubnet; Hostname = $Hostname; WireGuardExe = $WireGuardExe }
      }
    }
  }
  Write-Host "`ndone ($Mode)." -ForegroundColor Green
} catch [RemoteSetupError] {
  Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
